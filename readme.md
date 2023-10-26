# EduGenix

> Assignment Generator Flask Application Deployment with Pulumi


## Overview

This project involves the deployment of a Flask-based assignment generator application using the infrastructure as code (IaC) tool, Pulumi, for AWS resources provisioning. The entire setup includes resources such as EC2 instances, RDS databases, VPCs, subnets, AMIs, and more. The deployment process involves multiple stages, from code checks on pull requests to actual infrastructure provisioning using Pulumi.

## Project Structure

- `webapp`: This folder contains the Flask application code.
- `iac-pulumi`: This folder contains the infrastructure as code scripts written in Python for Pulumi.

## Workflow

### Pull Request Creation:

- When a pull request is created, a workflow checks and validates the packer format.
- Only if the checks pass, the PR is allowed to merge with the organization's main repository.

### Push to Main Repository:

- On pushing to the organization's main branch, two GitHub workflows are triggered:
  - Integration Test: This test uses PostgreSQL to ensure that the application interacts correctly with the database.
  - AMI Creation with Packer: This workflow creates an Amazon Machine Image (AMI) containing all the provisions and shell commands necessary for the application to run.

### Infrastructure Setup using Pulumi:

Within the `iac-pulumi` folder, the infrastructure for the application is set up in the following order:

- VPC Creation: A Virtual Private Cloud (VPC) is set up for the application.
- Subnet Creation: Public and private subnets are provisioned.
- Internet Gateway and Route Table: Internet gateways are set up and associated with the route tables.
- RDS Instance: An Amazon RDS instance is created with the necessary security groups.
- EC2 Instance: An EC2 instance is provisioned. This instance uses the AMI created earlier. Post-provisioning, the application is deployed on this instance with the necessary environment configurations.

## Application Deployment

The Flask application is served using Gunicorn. On the EC2 instance, `systemd` services are used to ensure that the application is always running, even after system reboots or failures.

## Database and Deployment Configurations

The application uses environment variables for various configurations, including database connections. Ensure that these variables are set correctly in the environment where the application runs.

## Conclusion

This project showcases a robust and automated deployment process for a Flask application on AWS using Pulumi. It emphasizes best practices such as code checks on pull requests, integration testing, and infrastructure as code.

## Future Enhancements

- Consider adding monitoring and logging services to keep track of the application's health and performance.
- Implement a CI/CD pipeline for more streamlined deployments and updates.
- Remember to always keep your README updated as your project evolves. It serves as the first point of reference for anyone looking to understand or contribute to your project.