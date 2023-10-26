import pulumi
from pulumi_aws import ec2, ssm, rds
import pulumi_aws as aws

# ====== Configuration Loading ======
config = pulumi.Config()

vpc_name = config.require("vpcName")
vpc_cidr_block = config.require("vpcCIDRBlock")
subnet_count = int(config.get("subnetCount") or 2)  
cidr_base = config.require("cidrBase")
destination_cidr_block = config.require("destinationCIDRBlock")
stack_name = pulumi.get_stack()
key_pair_name = config.require('keyPairName')

ami_id = ssm.get_parameter(name="/webapp/ami-id").value
db_username = pulumi.Output.secret(ssm.get_parameter(name="/db/username").value)
db_password = pulumi.Output.secret(ssm.get_parameter(name="/db/password").value)

# Derived configurations
vpc_name_full = f"{stack_name}-{vpc_name}"
cidr_base_start, cidr_base_subnet = cidr_base.split('/')[0].rsplit('.', 2)[0], cidr_base.split('/')[1]

# ====== VPC & Subnet Creation ======
# Create VPC
vpc = ec2.Vpc(vpc_name_full, 
              cidr_block=vpc_cidr_block, 
              enable_dns_support=True,
              enable_dns_hostnames=True,
              tags={"Name": vpc_name_full})

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

        pub_subnet = ec2.Subnet(subnet_pub_name, 
                            vpc_id=vpc.id, 
                            cidr_block=f"{cidr_base_start}.{2*i}.0/{cidr_base_subnet}",
                            map_public_ip_on_launch=True,
                            availability_zone=available_azs.names[i],
                            tags={"Name": subnet_pub_name})
        
        priv_subnet = ec2.Subnet(subnet_pri_name, 
                                vpc_id=vpc.id, 
                                cidr_block=f"{cidr_base_start}.{2*i+1}.0/{cidr_base_subnet}", 
                                availability_zone=available_azs.names[i],
                                tags={"Name": subnet_pri_name})
        
        public_subnets.append(pub_subnet)
        private_subnets.append(priv_subnet)

    except Exception as e:
        raise pulumi.RunError(f"Failed to create subnets: {str(e)}")

# Create an Internet Gateway
igw = ec2.InternetGateway(f"{vpc_name_full}-igw",
    vpc_id=vpc.id,
    opts=pulumi.ResourceOptions(depends_on=[vpc]),
    tags={"Name": f"{vpc_name}_igw"}
)

# Create a Route Table
public_route_table = ec2.RouteTable(f"{vpc_name_full}-public-route-table",
    vpc_id=vpc.id,
    opts=pulumi.ResourceOptions(depends_on=[vpc]),
    tags={"Name": f"{vpc_name}_public_route_table"}
)

# Associate our subnet with this Route Table
for i, subnet in enumerate(public_subnets):
    route_table_assoc = ec2.RouteTableAssociation(f"{vpc_name_full}-pub-rta-{i}",
        subnet_id=subnet.id,
        route_table_id=public_route_table.id,
        opts=pulumi.ResourceOptions(depends_on=[public_route_table, subnet])
    )

# Add a route to the Route Table that points to the Internet Gateway
route_to_internet = ec2.Route(f"{vpc_name_full}-route-to-internet",
    route_table_id=public_route_table.id,
    destination_cidr_block="0.0.0.0/0",
    gateway_id=igw.id,
    opts=pulumi.ResourceOptions(depends_on=[public_route_table, igw])
)

#create a private route table
private_route_table = ec2.RouteTable(f"{vpc_name_full}-private-route-table",
    vpc_id=vpc.id,
    opts=pulumi.ResourceOptions(depends_on=[vpc]),
    tags={"Name": f"{vpc_name}_private_route_table"}
)

# Associate our subnet with this Route Table
for i, subnet in enumerate(private_subnets):
    route_table_assoc = ec2.RouteTableAssociation(f"{vpc_name_full}-pri-rta-{i}",
        subnet_id=subnet.id,
        route_table_id=private_route_table.id,
        opts=pulumi.ResourceOptions(depends_on=[private_route_table, subnet])
    )


# ====== EC2 Instance Deployment ======
app_sg = ec2.SecurityGroup('app-sg',
    vpc_id=vpc.id,
    description='Application Security Group',
    opts=pulumi.ResourceOptions(depends_on=[vpc, *public_subnets]),
    ingress=[
        {'protocol': 'tcp', 'from_port': port, 'to_port': port, 'cidr_blocks': ['0.0.0.0/0']}
        for port in [22, 80, 443, 8000]
    ],
    egress=[  # Explicitly allowing all outbound traffic, including to the RDS on port 5432
        {'protocol': '-1', 'from_port': 0, 'to_port': 0, 'cidr_blocks': ['0.0.0.0/0']}
    ]
)

db_security_group = ec2.SecurityGroup('db-security-group',
    vpc_id=vpc.id,
    description='RDS Security Group',
    ingress=[
        {'protocol': 'tcp', 'from_port': 5432, 'to_port': 5432, 'security_groups': [app_sg.id]}
    ]
)


parameter_group = rds.ParameterGroup('db-parameter-group',
    family='postgres15',  
    description='Custom parameter group for my PostgreSQL database',
    parameters=[
        {'name': 'client_min_messages', 'value': 'notice'},
        {'name': 'default_transaction_isolation', 'value': 'read committed'},
        {'name': 'lc_messages', 'value': 'en_US.UTF-8'}
    ]
)

db_subnet_group = rds.SubnetGroup('db-subnet-group',
    subnet_ids=[subnet.id for subnet in private_subnets],
    tags={"Name": "db-subnet-group"}
)

rds_instance = rds.Instance('csye6225-db-instance',
    engine='postgres',
    engine_version='15.3',
    instance_class='db.t3.micro', 
    storage_type='gp2',
    allocated_storage=20, 
    db_name='healthcheck',
    username=db_username,
    password=db_password,
    skip_final_snapshot=True,
    parameter_group_name=parameter_group.name,
    vpc_security_group_ids=[db_security_group.id],
    db_subnet_group_name=db_subnet_group.name,  
    multi_az=False,  
    publicly_accessible=False,  
    tags={"Name": "csye6225-db-instance"}
)


# This is a cloud-init configuration in YAML format.
user_data_script = """
#cloud-config
bootcmd:
  - "touch /var/log/user_data.log && chmod 666 /var/log/user_data.log"
  - "echo 'Executing boot commands...' >> /var/log/user_data.log"
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

runcmd:
  - "echo 'Executing run commands...' >> /var/log/user_data.log"
  - "chown -R webapp_user:webapp_user /opt/webapp/.env"
  - "chown -R webapp_user:webapp_user /opt/webapp && echo 'Permissions set for /opt/webapp.' >> /var/log/user_data.log || echo 'Failed to set permissions for /opt/webapp.' >> /var/log/user_data.log"
  - "chmod -R 775 /opt/webapp && echo 'Changed mode for /opt/webapp.' >> /var/log/user_data.log || echo 'Failed to change mode for /opt/webapp.' >> /var/log/user_data.log"
  - "sudo systemctl daemon-reload && echo 'Systemd reloaded.' >> /var/log/user_data.log || echo 'Failed to reload systemd.' >> /var/log/user_data.log"
  - "sudo systemctl start app.service && echo 'Restarted webapp service.' >> /var/log/user_data.log || echo 'Failed to restart webapp service.' >> /var/log/user_data.log"
  - "sudo systemctl enable app.service && echo 'Enabled webapp service.' >> /var/log/user_data.log || echo 'Failed to enable webapp service.' >> /var/log/user_data.log"
  - "sudo cloud-init status --wait --long >> /var/log/user_data.log && echo 'Cloud-init finished.' >> /var/log/user_data.log"

"""


def format_user_data(args):
    # Split endpoint into host and port
    host, port = args[0].split(':')
    return user_data_script.format(
        database_host=host,
        database_user=args[1],
        database_password=args[2],
        database_name="healthcheck"
    )

formatted_user_data = pulumi.Output.all(rds_instance.endpoint, db_username, db_password).apply(format_user_data)

# If you want to print the formatted user_data, use the following:
formatted_user_data.apply(lambda x: print(x))
# Launch EC2 instance
instance = ec2.Instance('app-instance',
    instance_type="t2.micro",
    ami=ami_id,
    key_name=key_pair_name,
    user_data=formatted_user_data,
    vpc_security_group_ids=[app_sg.id],
    subnet_id=public_subnets[0].id,  # Deploying in the first subnet as an example
    associate_public_ip_address=True,
    root_block_device={
        'volumeSize': 25,
        'volumeType': 'gp2',
        'delete_on_termination': True
    },
    opts=pulumi.ResourceOptions(depends_on=[app_sg]),
    disable_api_termination=False
)

# Export necessary details
pulumi.export("vpcId", vpc.id)
pulumi.export("subnetIds", [subnet.id for subnet in public_subnets])
pulumi.export("privateSubnetIds", [subnet.id for subnet in private_subnets])

pulumi.export("amiId", ami_id)