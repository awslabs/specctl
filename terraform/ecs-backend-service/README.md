# ECS backend service
The solution is based on the [backend service](https://github.com/aws-ia/ecs-blueprints/tree/main/examples/backend-service)) ECS Solution Blueprint.

* Deploy the [core-infra](../core-infra/README.md). Note if you have already deployed the infra then you can reuse it as well.
* In this folder, copy the `terraform.tfvars.example` file to `terraform.tfvars` and update the variables.
* Now you can deploy this blueprint
```shell
terraform init
terraform plan
terraform apply -auto-approve
```
## Cleanup
Run the following command if you want to delete all the resources created before.
```shell
terraform destroy
```

Please see [backend service](https://github.com/aws-ia/ecs-blueprints/blob/main/examples/backend-service/README.md) for more details.
