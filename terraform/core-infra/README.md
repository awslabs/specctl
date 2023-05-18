# Core Infrastructure
This folder contains the Terraform code to deploy the core infratructure for an ECS Fargate workload. The AWS resources created by the script are:
* Networking
  * VPC
    * 3 public subnets, 1 per AZ. If a region has less than 3 AZs it will create same number of public subnets as AZs.
    * 3 private subnets, 1 per AZ. If a region has less than 3 AZs it will create same number of private subnets as AZs.
    * 1 NAT Gateway
    * 1 Internet Gateway
    * Associated Route Tables
* 1 ECS Cluster with AWS CloudWatch Container Insights enabled.
* Task execution IAM role
* CloudWatch log groups

## Getting Started
Make sure you have:

* [Terraform](https://learn.hashicorp.com/tutorials/terraform/install-cli) (tested version v1.2.5 on darwin_amd64)
* [Git](https://github.com/git-guides/install-git) (tested version 2.27.0)
* [AWS CLI](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html#getting-started-install-instructions)
## Usage
```bash
cd examples/core-infra/
```
* Run Terraform init to download the providers and install the modules
```shell
terraform init
```
* Review the terraform plan output, take a look at the changes that terraform will execute, and then apply them:
```shell
terraform plan
terraform apply --auto-approve
```
## Outputs
After the execution of the Terraform code you will get an output with needed IDs and values needed as input for the nexts Terraform applies. Most likely all you need is the `cluster_name`.

## Cleanup
Run the following command if you want to delete all the resources created before. If you have created other blueprints and they use these infrastructure then destroy those blueprint resources first.
```shell
terraform destroy
```
