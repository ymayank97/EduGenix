# iac-pulumi

## Description

This repository contains the code for the infrastructure as code (IaC) project.


## Running the code

### Pulumi

Initialize the stack


```

pulumi stack init dev-vpc

```


#### How to select AWS profile before running pulumi up
``` 
pulumi config set aws:region us-west-2  
pulumi config set aws:profile dev  
pulumi up
``` 

## Commands

```
1. `pulumi up` - create or update the stack
2. `pulumi destroy` - destroy the stack
3. `pulumi stack rm stack_name` - remove the stack
4. `pulumi stack ls` - list the stacks
5. `pulumi stack select stack_name` - select the stack

```