import json
import os
import base64
import pulumi
from pulumi_aws import ec2, ssm, rds, sns, lambda_
import pulumi_aws as aws
import pulumi_gcp as gcp

# ====== Configuration Loading ======
config = pulumi.Config()

vpc_name = config.require("vpcName")
vpc_cidr_block = config.require("vpcCIDRBlock")
subnet_count = int(config.get("subnetCount") or 2)
cidr_base = config.require("cidrBase")
destination_cidr_block = config.require("destinationCIDRBlock")
stack_name = pulumi.get_stack()
key_pair_name = config.require("keyPairName")
aws_profile_name = config.require("profile")
gcp_project = config.require("gcp_project")

# configurations in your Pulumi config
domain_name = config.require("domainName")
hosted_zone_id = config.require("hostedZoneId")
application_port = config.require_int("applicationPort")

account_id = ssm.get_parameter(name="/dev/accountID")
zoho_mail = ssm.get_parameter(name="/dev/zohoMail")
zoho_password = pulumi.Output.secret(ssm.get_parameter(name="/dev/zohoPassword").value)

ami = aws.ec2.get_ami(
    most_recent=True,
    owners=[account_id.value],
    filters=[{"name": "name", "values": ["ami-debian-12*"]}],
)

db_username = pulumi.Output.secret(ssm.get_parameter(name="/db/username").value)
db_password = pulumi.Output.secret(ssm.get_parameter(name="/db/password").value)

# Derived configurations
vpc_name_full = f"{stack_name}-{vpc_name}"
cidr_base_start, cidr_base_subnet = (
    cidr_base.split("/")[0].rsplit(".", 2)[0],
    cidr_base.split("/")[1],
)

# ====== VPC & Subnet Creation ======
# Create VPC
vpc = ec2.Vpc(
    vpc_name_full,
    cidr_block=vpc_cidr_block,
    enable_dns_support=True,
    enable_dns_hostnames=True,
    tags={"Name": vpc_name_full},
)

# Determine available AZs
available_azs = aws.get_availability_zones(state="available")
az_count = min(len(available_azs.names), subnet_count)

# Create subnets across the available AZs
public_subnets = []
private_subnets = []


for i in range(az_count):
    try:
        subnet_pub_name = f"{vpc_name_full}-pub-subnet-{i}"
        subnet_pri_name = f"{vpc_name_full}-pri-subnet-{i}"

        pub_subnet = ec2.Subnet(
            subnet_pub_name,
            vpc_id=vpc.id,
            cidr_block=f"{cidr_base_start}.{2*i}.0/{cidr_base_subnet}",
            map_public_ip_on_launch=True,
            availability_zone=available_azs.names[i],
            tags={"Name": subnet_pub_name},
        )

        priv_subnet = ec2.Subnet(
            subnet_pri_name,
            vpc_id=vpc.id,
            cidr_block=f"{cidr_base_start}.{2*i+1}.0/{cidr_base_subnet}",
            availability_zone=available_azs.names[i],
            tags={"Name": subnet_pri_name},
        )

        public_subnets.append(pub_subnet)
        private_subnets.append(priv_subnet)

    except Exception as e:
        raise pulumi.RunError(f"Failed to create subnets: {str(e)}")

# Create an Internet Gateway
igw = ec2.InternetGateway(
    f"{vpc_name_full}-igw",
    vpc_id=vpc.id,
    opts=pulumi.ResourceOptions(depends_on=[vpc]),
    tags={"Name": f"{vpc_name}_igw"},
)

# Create a Route Table
public_route_table = ec2.RouteTable(
    f"{vpc_name_full}-public-route-table",
    vpc_id=vpc.id,
    opts=pulumi.ResourceOptions(depends_on=[vpc]),
    tags={"Name": f"{vpc_name}_public_route_table"},
)

# Associate our subnet with this Route Table
for i, subnet in enumerate(public_subnets):
    route_table_assoc = ec2.RouteTableAssociation(
        f"{vpc_name_full}-pub-rta-{i}",
        subnet_id=subnet.id,
        route_table_id=public_route_table.id,
        opts=pulumi.ResourceOptions(depends_on=[public_route_table, subnet]),
    )

# Add a route to the Route Table that points to the Internet Gateway
route_to_internet = ec2.Route(
    f"{vpc_name_full}-route-to-internet",
    route_table_id=public_route_table.id,
    destination_cidr_block="0.0.0.0/0",
    gateway_id=igw.id,
    opts=pulumi.ResourceOptions(depends_on=[public_route_table, igw]),
)

# create a private route table
private_route_table = ec2.RouteTable(
    f"{vpc_name_full}-private-route-table",
    vpc_id=vpc.id,
    opts=pulumi.ResourceOptions(depends_on=[vpc]),
    tags={"Name": f"{vpc_name}_private_route_table"},
)

# Associate our subnet with this Route Table
for i, subnet in enumerate(private_subnets):
    route_table_assoc = ec2.RouteTableAssociation(
        f"{vpc_name_full}-pri-rta-{i}",
        subnet_id=subnet.id,
        route_table_id=private_route_table.id,
        opts=pulumi.ResourceOptions(depends_on=[private_route_table, subnet]),
    )


# SNS Topic
sns_topic = sns.Topic("AssignmentSubmittedTopic", display_name="My Notification Topic")

email_subscription = sns.TopicSubscription(
    "AssignmentSubmittedTopic",
    topic=sns_topic.arn,
    protocol="email",
    endpoint="admin@mayankcodes.me",
)

# ====== Lambda Function Deployment ======
# Step 0: Create a Google Cloud Provider
gcp_provider = gcp.Provider("gcp", project=gcp_project)

# Step 1: Create a Google Cloud Storage Bucket
bucket = gcp.storage.Bucket("bucket", location="us", force_destroy=True)

# Step 2: Create a Google Service Account and its keys
account = gcp.serviceaccount.Account("account", account_id="my-service-account")

# Wait for the service account to be created before creating IAM role
pulumi.Output.all(account.email, gcp_project).apply(
    lambda outputs: create_iam_member(*outputs)
)

# Step 3: Assign a role to the service account for GCS access
def create_iam_member(email, project):
    # Assign a role to the service account for GCS access
    service_account_gcs_role = gcp.projects.IAMMember(
        "service-account-gcs-role",
        project=project,
        role="roles/storage.objectCreator",
        member=pulumi.Output.concat("serviceAccount:", email),
    )

# Step 4: Generate a key for the service account
account_key = gcp.serviceaccount.Key("account-key", service_account_id=account.id)

# 5. Create a DynamoDB Table for tracking emails sent
table = aws.dynamodb.Table(
    "table",
    attributes=[{"name": "Id", "type": "S"}],
    hash_key="Id",
    write_capacity=1,
    read_capacity=1,
)

# 6. Create an SES Domain Identity
email = aws.ses.DomainIdentity("email", domain=domain_name)


# Create an IAM Role for the Lambda function
lambdarole = aws.iam.Role(
    "lambdaRole",
    assume_role_policy=json.dumps(
        {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Action": "sts:AssumeRole",
                    "Principal": {"Service": "lambda.amazonaws.com"},
                    "Effect": "Allow",
                }
            ],
        }
    ),
)

# Attach the relevant policies to the IAM Role
policy = aws.iam.RolePolicy(
    "lambdaPolicy",
    role=lambdarole.id,
    policy=json.dumps(
        {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Action": [
                        "dynamodb:*",  # Permissions for DynamoDB
                        "ses:SendEmail",  # Permissions for SES
                        "logs:*",  # Permissions for CloudWatch Logs
                    ],
                    "Resource": "*",
                }
            ],
        }
    ),
)

# Path to the Lambda function code
artifact_path = os.path.join(
    "C:\\Users\\Mayank\\OneDrive\\Desktop\Workspace\\CourseWork\\cloud\\serverless\\",
    "serverless.zip",
)

# Decode the private key
decoded_key = account_key.private_key.apply(
    lambda k: base64.b64decode(k).decode("utf-8") if k else None
)
# Create the Lambda Function
func = lambda_.Function(
    "myLambdaFunction",
    role=lambdarole.arn,
    runtime="python3.8",
    handler="lambda_function.lambda_handler",
    code=pulumi.FileArchive(artifact_path),
    environment={
        "variables": {
            "GCP_PROJECT": gcp_project,
            "GCP_SERVICE_ACCOUNT_KEY": decoded_key,
            "BUCKET_NAME": bucket.name,
            "DYNAMODB_TABLE": table.name,
            "SES_DOMAIN": config.require("sesDomain"),
            "ZOHO_MAIL": zoho_mail.value,
            "ZOHO_PASSWORD": zoho_password,
        }
    },
)

sns_topic_subscription = aws.sns.TopicSubscription(
    "MySNSTopicSubscription", topic=sns_topic.arn, protocol="lambda", endpoint=func.arn
)

# IAM policy attachment for Lambda invocation from SNS
lambda_permission = aws.lambda_.Permission(
    "lambdaPermission",
    action="lambda:InvokeFunction",
    function=func.name,
    principal="sns.amazonaws.com",
    source_arn=sns_topic.arn,
)


# ====== EC2 Instance Deployment ======

lb_sg = ec2.SecurityGroup(
    "lb-sg",
    vpc_id=vpc.id,
    description="Load Balancer Security Group",
    ingress=[
        {
            "protocol": "tcp",
            "from_port": 80,
            "to_port": 80,
            "cidr_blocks": ["0.0.0.0/0"],
        },
        {
            "protocol": "tcp",
            "from_port": 443,
            "to_port": 443,
            "cidr_blocks": ["0.0.0.0/0"],
        },
    ],
    egress=[  # Explicitly allowing all outbound traffic, including to the RDS on port 5432
        {"protocol": "-1", "from_port": 0, "to_port": 0, "cidr_blocks": ["0.0.0.0/0"]}
    ],
)

app_sg_ingress = [
    {"protocol": "tcp", "from_port": 22, "to_port": 22, "cidr_blocks": ["0.0.0.0/0"]},
    {
        "protocol": "tcp",
        "from_port": application_port,
        "to_port": application_port,
        "security_groups": [lb_sg.id],
    },
]

app_sg = ec2.SecurityGroup(
    "app-sg",
    vpc_id=vpc.id,
    description="Application Security Group",
    opts=pulumi.ResourceOptions(depends_on=[vpc, *public_subnets]),
    ingress=app_sg_ingress,
    egress=[  # Explicitly allowing all outbound traffic, including to the RDS on port 5432
        {"protocol": "-1", "from_port": 0, "to_port": 0, "cidr_blocks": ["0.0.0.0/0"]}
    ],
)


db_security_group = ec2.SecurityGroup(
    "db-security-group",
    vpc_id=vpc.id,
    description="RDS Security Group",
    ingress=[
        {
            "protocol": "tcp",
            "from_port": 5432,
            "to_port": 5432,
            "security_groups": [app_sg.id],
        }
    ],
)


parameter_group = rds.ParameterGroup(
    "db-parameter-group",
    family="postgres15",
    description="Custom parameter group for my PostgreSQL database",
    parameters=[
        {"name": "client_min_messages", "value": "notice"},
        {"name": "default_transaction_isolation", "value": "read committed"},
        {"name": "lc_messages", "value": "en_US.UTF-8"},
    ],
)

db_subnet_group = rds.SubnetGroup(
    "db-subnet-group",
    subnet_ids=[subnet.id for subnet in private_subnets],
    tags={"Name": "db-subnet-group"},
)

rds_instance = rds.Instance(
    "csye6225-db-instance",
    engine="postgres",
    engine_version="15.3",
    instance_class="db.t3.micro",
    storage_type="gp2",
    allocated_storage=20,
    db_name="healthcheck",
    username=db_username,
    password=db_password,
    skip_final_snapshot=True,
    parameter_group_name=parameter_group.name,
    vpc_security_group_ids=[db_security_group.id],
    db_subnet_group_name=db_subnet_group.name,
    multi_az=False,
    publicly_accessible=False,
    tags={"Name": "csye6225-db-instance"},
)

# IAM Role for EC2 Instances
ec2_role = aws.iam.Role(
    "ec2Role",
    assume_role_policy=json.dumps(
        {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Action": "sts:AssumeRole",
                    "Effect": "Allow",
                    "Principal": {"Service": "ec2.amazonaws.com"},
                }
            ],
        }
    ),
)

# IAM Policy for CloudWatch
cloudwatch_policy = aws.iam.Policy(
    "cloudwatchPolicy",
    policy=json.dumps(
        {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Action": [
                        "cloudwatch:PutMetricData",
                        "logs:CreateLogGroup",
                        "logs:CreateLogStream",
                        "logs:PutLogEvents",
                        "logs:DescribeLogStreams",
                        "sns:Publish",
                    ],
                    "Resource": "*",
                }
            ],
        }
    ),
)

# Attach the policy to the role
role_policy_attachment = aws.iam.RolePolicyAttachment(
    "rolePolicyAttachment", role=ec2_role.name, policy_arn=cloudwatch_policy.arn
)

# This is a cloud-init configuration in YAML format.
user_data_script = """
#cloud-config
bootcmd:
  - "touch /var/log/user_data.log && chmod 666 /var/log/user_data.log"
  - "echo 'Executing boot commands...' >> /var/log/user_data.log"
  - "date >> /var/log/user_data.log"
  - "test -d $(dirname /opt/webapp/.env) || (mkdir -p $(dirname /opt/webapp/.env) && echo 'Created directory /opt/webapp' >> /var/log/user_data.log) || echo 'Failed to create directory /opt/webapp' >> /var/log/user_data.log"
  - "touch /opt/webapp/.env && chown $(whoami):$(whoami) /opt/webapp/.env && echo 'Created and changed ownership of /opt/webapp/.env' >> /var/log/user_data.log || echo 'Failed operations on /opt/webapp/.env' >> /var/log/user_data.log"

write_files:
  - path: /opt/webapp/.env
    owner: webapp_user:webapp_user
    permissions: '0666'
    content: |
      DATABASE_HOST={database_host}
      DATABASE_USER={database_user}
      DATABASE_PASSWORD={database_password}
      DATABASE_NAME={database_name}
      SNS_TOPIC_ARN={sns_topic_arn}
      AWS_PROFILE_NAME={aws_profile_name}

runcmd:
  - "echo 'Executing run commands...' >> /var/log/user_data.log"
  - "chown -R webapp_user:webapp_user /opt/webapp/.env"
  - "chown -R webapp_user:webapp_user /opt/webapp && echo 'Permissions set for /opt/webapp.' >> /var/log/user_data.log || echo 'Failed to set permissions for /opt/webapp.' >> /var/log/user_data.log"
  - "chmod -R 775 /opt/webapp && echo 'Changed mode for /opt/webapp.' >> /var/log/user_data.log || echo 'Failed to change mode for /opt/webapp.' >> /var/log/user_data.log"
  - "sudo systemctl daemon-reload && echo 'Systemd reloaded.' >> /var/log/user_data.log || echo 'Failed to reload systemd.' >> /var/log/user_data.log"
  - "sudo systemctl start app.service && echo 'Restarted webapp service.' >> /var/log/user_data.log || echo 'Failed to restart webapp service.' >> /var/log/user_data.log"
  - "sudo systemctl enable app.service && echo 'Enabled webapp service.' >> /var/log/user_data.log || echo 'Failed to enable webapp service.' >> /var/log/user_data.log"
  - "sudo cloud-init status --wait --long >> /var/log/user_data.log && echo 'Cloud-init finished.' >> /var/log/user_data.log"
  - "sudo amazon-cloudwatch-agent-ctl -a fetch-config -m ec2 -c file:/opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.json -s"
  - "sudo systemctl restart amazon-cloudwatch-agent"

"""


def format_user_data(args):
    # Split endpoint into host and port
    host, port = args[0].split(":")
    return user_data_script.format(
        database_host=host,
        database_user=args[1],
        database_password=args[2],
        database_name="healthcheck",
        sns_topic_arn=args[3],
        aws_profile_name=args[4],
    )


def encode_user_data(user_data):
    return base64.b64encode(user_data.encode()).decode()


formatted_user_data = pulumi.Output.all(
    rds_instance.endpoint, db_username, db_password, sns_topic.arn, aws_profile_name
).apply(format_user_data)
encoded_user_data = formatted_user_data.apply(encode_user_data)

# Create an IAM Instance Profile
instance_profile = aws.iam.InstanceProfile("instanceProfile", role=ec2_role.name)

# Launch Template Modification
launch_template = ec2.LaunchTemplate(
    "asg-launch-template",
    name_prefix="lt-",
    image_id=pulumi.Output.from_input(ami).apply(lambda ami: ami.id),
    instance_type="t2.micro",
    key_name=key_pair_name,
    user_data=encoded_user_data,
    iam_instance_profile={
        "arn": instance_profile.arn  # Use the ARN of the instance profile
    },
    block_device_mappings=[
        aws.ec2.LaunchTemplateBlockDeviceMappingArgs(
            device_name="/dev/sdf",
            ebs=aws.ec2.LaunchTemplateBlockDeviceMappingEbsArgs(
                volume_size=20,
                volume_type="gp2",
                delete_on_termination=True,
            ),
        )
    ],
    disable_api_termination=False,
    network_interfaces=[
        aws.ec2.LaunchTemplateNetworkInterfaceArgs(
            associate_public_ip_address=True,
            security_groups=[app_sg.id],  # Include security group IDs here
        )
    ],
    opts=pulumi.ResourceOptions(depends_on=[app_sg]),
)


alb = aws.lb.LoadBalancer(
    "app-lb",
    internal=False,
    load_balancer_type="application",
    security_groups=[lb_sg.id],
    subnets=[subnet.id for subnet in public_subnets],
    enable_deletion_protection=False,
    tags={"Name": "app-lb"},
    opts=pulumi.ResourceOptions(
        depends_on=[vpc, *public_subnets, launch_template, lb_sg]
    ),
)

target_group = aws.lb.TargetGroup(
    "app-tg",
    port=application_port,
    protocol="HTTP",
    vpc_id=vpc.id,
    health_check={"path": "/healthz", "protocol": "HTTP", "port": "traffic-port"},
    target_type="instance",
    tags={"Name": "app-tg"},
    opts=pulumi.ResourceOptions(
        depends_on=[vpc, *public_subnets, launch_template, alb]
    ),
)


listener = aws.lb.Listener(
    "app-listener",
    load_balancer_arn=alb.arn,
    port=80,
    default_actions=[{"type": "forward", "target_group_arn": target_group.arn}],
    opts=pulumi.ResourceOptions(
        depends_on=[vpc, *public_subnets, launch_template, alb, target_group]
    ),
)


autoscaling_group = aws.autoscaling.Group(
    "asg",
    launch_template={"id": launch_template.id, "version": "$Latest"},
    min_size=1,
    max_size=3,
    desired_capacity=1,
    vpc_zone_identifiers=[subnet.id for subnet in public_subnets],
    target_group_arns=[target_group.arn],
    tags=[
        {"key": "Name", "value": "my-autoscaling-group", "propagate_at_launch": True}
    ],
)


# Scale Up Policy
scale_up_policy = aws.autoscaling.Policy(
    "scaleUpPolicy",
    scaling_adjustment=1,
    adjustment_type="ChangeInCapacity",
    cooldown=120,
    autoscaling_group_name=autoscaling_group.name,
)

scale_up_alarm = aws.cloudwatch.MetricAlarm(
    "scaleUpAlarm",
    comparison_operator="GreaterThanOrEqualToThreshold",
    evaluation_periods=2,
    metric_name="CPUUtilization",
    namespace="AWS/EC2",
    period=60,
    statistic="Average",
    threshold=5.0,
    alarm_actions=[scale_up_policy.arn],
    dimensions={"AutoScalingGroupName": autoscaling_group.name},
)

# Scale Down Policy
scale_down_policy = aws.autoscaling.Policy(
    "scaleDownPolicy",
    scaling_adjustment=-1,
    adjustment_type="ChangeInCapacity",
    cooldown=120,
    autoscaling_group_name=autoscaling_group.name,
)

scale_down_alarm = aws.cloudwatch.MetricAlarm(
    "scaleDownAlarm",
    comparison_operator="LessThanOrEqualToThreshold",
    evaluation_periods=2,
    metric_name="CPUUtilization",
    namespace="AWS/EC2",
    period=60,
    statistic="Average",
    threshold=3.0,
    alarm_actions=[scale_down_policy.arn],
    dimensions={"AutoScalingGroupName": autoscaling_group.name},
)

dns_record = aws.route53.Record(
    "app-dns-record",
    zone_id=hosted_zone_id,
    name=domain_name,
    type="A",
    aliases=[
        {"name": alb.dns_name, "zone_id": alb.zone_id, "evaluate_target_health": True}
    ],
)

# Export necessary details
pulumi.export("vpcId", vpc.id)
pulumi.export("subnetIds", [subnet.id for subnet in public_subnets])
pulumi.export("privateSubnetIds", [subnet.id for subnet in private_subnets])
pulumi.export("amiId", pulumi.Output.from_input(ami).apply(lambda ami: ami.id))
# Export the name and ARN of the topic
pulumi.export("snsTopicName", sns_topic.name)
pulumi.export("snsTopicArn", sns_topic.arn)