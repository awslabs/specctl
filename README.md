# specctl 
The `specctl` is a command-line based tool to extract and transform Kubernetes objects to ECS and vice versa. It has two modes, `-m k2e` (default) convert Kubernetes to ECS and `-m e2k` for ECS to Kubernetes. Currently, only ECS Fargate is supported.

For Kubernetes to ECS conversion, `specctl` can read and convert Kubernetes objects either from Kubernetes YAML specification files or from Kubernetes clusters. The tool uses [Terraform](https://developer.hashicorp.com/terraform/tutorials/aws-get-started/install-cli) to create all the necessary AWS resources needed to run services and tasks on ECS. 

For ECS to Kubernetes, `specctl` can read and convert ECS and related AWS objects from an AWS account where the ECS cluster is running. Once the Kubernetes YAML specifications are generated, you can simply use `kubectl` on the generated spec.

**New** Check out initial version of [Docker Compose to Kubernetes YAML](./specctl/dc2k8s/README.md) support.

### Getting Started
* Install [Terraform](https://developer.hashicorp.com/terraform/tutorials/aws-get-started/install-cli)
* I would recommend to use `virtualenv` to avoid any conflicts with preinstalled Python libraries. All testing done on Mac OS 13.2.1.
* Fork the repo and clone

```bash
git clone https://github.com/awslabs/specctl.git
cd specctl
pip install virtualenv
virtualenv .venv
source .venv/bin/activate
pip install specctl
specctl --help
```
### Kubernetes to ECS
Let us first create an ECS cluster:
```bash
cd terraform/core-infra
terraform init
terraform apply --auto-approve
cd ../..
```
Above will create an ECS cluster named `core-infra`.
#### A simple example - NGINX deployment
The `./tests/nginx` has a simple NGINX Kubernetes deployment specification. `specctl` will convert this into an ECS Fargate task definition and service definition. 

```bash
specctl -s tests/nginx
cd output/namespaces
terraform init && terraform apply --auto-approve
cd ../default/nginx-svc
terraform init && terraform apply --auto-approve
...
...
Apply complete! Resources: 17 added, 0 changed, 0 destroyed.

Outputs:

application_url = "http://nginx-svc-alb-xxxxx.us-west-2.elb.amazonaws.com"
```
Click on the URL and you should see the NGINX home page! **Congrats, you have converted Kubernetes simple spec to ECS!**

#### OK, what did `specctl` do?
The `specctl` will generate following artifacts in `./output` directory.
* `namespaces` : contains (a) Kubernetes namespaces for creating CloudMap namespaces for service discovery, and (b) SSM parameters with both simple string obtained from ConfigMaps and secure strings obtained from Secrets. The Terraform code to create required AWS resources is also generated. The terraform init and apply commands created all the resources based on data extracted from Kubernetes namespaces, configmaps, and secrets.
* `<namespace>/<service>` : a set of folders one for each Kubernetes namespace and inside that a service folder one for each Kubernetes service in the namespace. The Terraform code to create the service, task definition, and if applicable ALB resources, is auto-generated and available in the service folder. The terraform init and apply commands created all resources based on data extracted from Kubernetes service and deployments.
To clean up, assuming you are in `specctl` directory
```bash
cd output/default/nginx-svc
terraform destroy --auto-approve
cd ../../namespaces
terraform destroy --auto-approve
cd ../..
rm -rf output
```
### Conversions at scale from a cluster
`specctl` is built with scalable migration in mind. For the Kubernetes to ECS migration, for example, every service has its Terraform code and extracted settings in a seprate folder. By adding a CI/CD pipeline and S3 bucket (for Terraform state), the deployment of ECS services can be completely automated for all the services. The Terraform infra-as-code approach makes it easy to extend and customize to meet customer's application needs. 

To test conversion at scale for Kubernetes to ECS, we can use the `tests/retail-store` example. Start by creating this application in Kubernetes. You can use `minikube`if you don't have a Kubernetes cluster handy. 

Assuming you are in `specctl` directory and you have cleaned up the previous example `./output` directory.
```bash
kubectl apply -f tests/retail-store
...
... (wait for apply to finish)
...
```
```bash
specctl 

* arn:aws:eks:us-west-2:xxxx:cluster/test-eks-managed (select your Kubernetes cluster)
...
...
cd output
cd namespaces
terraform init && terraform apply --auto-approve
...
...
```
The above will create all the shared resources in various namespaces that are extracted. Shared resources include SSM Parameters, ALBs, CloudMap namespaces. 

There is a convenience script `specctl/bin/migrate.sh` to recursively apply `terraform init` and `terraform apply --auto-approve` in each of the service directories. Below is assuming your are in `namespaces` folder from above step. 

```bash
cd ..
source ../bin/migrate.sh apply
```
You should see a lot of services created in ECS - `ui`,`carts`, `catalog` ... The `ui` service is load balanced and if you access the ALB URL you will see the same home page as when you access the `ui` service in Kubernetes. Play around with the app and make sure all the inter-service communication is working in both ECS and Kubernetes!
**Congrats, you have just migrated 7 services in matter of minutes!** And same approach can be adapted to do scalable migrations.

To clean up, assuming you are in `specctl` directory, follow below commands which will use `terraform destroy` to clean up:
```bash
cd output
mv namespaces ../
source ../bin/migrate.sh destroy 
...
... (wait for destroy to finish)
...
mv ../namespaces .
cd namespaces
terraform destroy --auto-approve
cd ../..
rm -rf output
```
#### What all K8s objects does specctl convert to ECS? 
- [X] Deployment and ReplicaSets
- [X] Service including ClusterIP, Load Balancer
- [X] Ingress with HTTP and HTTPS (AWS ALB only)
- [X] Pod IAM via Service Account
- [X] ConfigMaps
- [X] Secrets
- [X] Container specs along with init-containers, and named port handling
- [X] Fargate size determination based on cpu and mem reservation and limit
- [X] Pod Security Group
- [ ] DaemonSets
- [ ] Jobs
- [ ] Container volumes
- [ ] StatefulSets
- [ ] ?

**Note:** Kubernetes allows multiple variations for the service discovery, for example, `svc-name` or `svc-name.namespace` or `svc-name.namespace.svc.cluster.local`. But in ECS the service discovery name is `svc-name.namespace` (where namespace is in CloudMap). You may need to do some manual changes to the service endpoints configurations if they are not able to discover each other. This concern applies to both ECS to K8s and K8s to ECS conversions. 

### ECS to Kubernetes 
To do the reverse simply run the below command and it will generate the Kubernetes deployment, service, configmap, and secrets YAML specification files. Note to change the cluster name and/or region name if you created ECS cluster in a different region or are using your own ECS cluster in a different region. You can create Kubernetes namespace and deploy the generated artifacts to test. 

```bash
specctl -m e2k --ecs_region_name us-west-2 --ecs_cluster_name core-infra
ls output/core-infra
```
#### What all ECS objects does specctl convert to Kubernetes?
- [X] ECS Task to Pod
- [X] ECS Service to K8s Service & K8s Deployment  
- [X] ECS Load Balanced Service to K8s Ingress
- [X] SSM Parameter Simple Strings to K8s ConfigMap 
- [X] SSM Parameter SecureString to K8s Secrets
- [X] Secrets Manager to K8s Secrets
- [X] Task IAM to IAM annotations on Service Account
- [X] Task Security Group to EKS Security Group Policy 
- [X] First "." delimiter of CloudMap namespace to K8s namespace 

### Features of `specctl`
```bash
> specctl --help
Usage: specctl [OPTIONS]

Options:
  -m, --mode [k2e|e2k]            Transform mode - k2e K8s-to-ECS, e2k ECS-
                                  to-K8s
  -s, --source TEXT               Path to k8s spec file or dir
  -c, --context TEXT              Kubeconfig context name to load
  -l, --log_level [DEBUG|INFO|WARNING|ERROR|CRITICAL]
                                  Select log level
  -n, --namespaces TEXT           Only fetch namespaces specified here as
                                  comma separated string. Applies only when
                                  converting from K8s clusters and not from
                                  spec files
  --td_file TEXT                  File to write ECS task definition json
  --sd_file TEXT                  File to write ECS service definition json
  --input_file TEXT               File with additional input parameters for
                                  task, container, and/or services
  --tfvars_file TEXT              File to write the Terraform tfvars
  -d, --tf_modules_directory TEXT
                                  Path to Terraform modules directory
  --tf_modules_name_map TEXT      Change the value in this map to your
                                  terraform modules directory
  --tf_files TEXT                 List of files to use from Terraform modules
  -o, --output_directory TEXT     Path to output directory
  --ecs_cluster_name TEXT         ECS cluster to extract services and tasks
  --ecs_region_name TEXT          Region name for ECS cluster
  --sgp                           Create EKS Security Group Policy from task
                                  security groups
  --help                          Show this message and exit.
```
* `specctl` can read Kubernetes objects from a file/folder or directly from a Kubernetes cluster.
* If `-s` source path to the K8s YAML file or directory is provided, `specctl` will use those specification files to read and extract information to create `taskdefinition.json`, `servicedefinition.json`, and `terraform.tfvars` files.
* If `-c`, cluster kubeconfig context is provided, then `specctl` will read the deployments, services, configmaps, secrets directly from K8s cluster and generate the output files.
* If both `-s` and `-c` are provided then behavior is same as just `-s`, that is, to process file(s) at that source path.
* If neither `-s` and `-c` are provided then `specctl` will load all the contexts from kubeconfig and prompt the user to pick one.
* The `-l` option is to control logging. Default log level is `INFO`.
* The `--td_file` refers to JSON file for task definition and is set to `taskdefinition.json`. The actual output file is of the format `<output_directory>/<service_namespace>/<service_name>/taskdefinition.json`
* The `--sd_file` refers to JSON file for service definition and is set to `servicedefinition.json`. The actual output file is of the format `<output_directory>/<service_namespace>/<service_name>/taskdefinition.json`
* The `--input_file` is to provide additional input to add or update the parsed input in task definition and service definition JSON output. 
* The `--tfvars_file` is to provide the terraform tfvars output and set to `terraform.tfvars`. The actual output is of the form `<output_directory>/terraform.tfvars` and `<output_directory>/<service_namespace>/<service_name>/terraform.fvars`.
* The `-d` options is to provide the path to Terraform modules directory. Default is "./terraform" from where the specctl command is launched.
* The `--tf_modules_name_map` is to provide a map of what are the folder names for the `namespaces`, `ecs-lb-service`, and `ecs-backend-service` modules. Default is `"namespaces:namespaces,ecs-lb-service:ecs-lb-service,ecs-backend-service:ecs-backend-service"`. Keep the keys same and change module folder name as applicable. The module folders should be under the Terraform modules directory provided by `-d` option.
* The `--tf_files` is to provide a comma separated string of Terraform files to copy from the modules. Default is `"main.tf,versions.tf,variables.tf,outputs.tf"`
* The `-o` is the path to output directory. Default is `./output`.
* The `--ecs_cluster_name` is to provide name of ECS cluster to extract services and tasks to convert to Kubernetes specifications
* The `--ecs_region_name` is to provide region name for ECS cluster
* The `--sgp` flag is to control whether or not to create EKS security group policies based on ECS task security groups. By default specctl doesn't create the security group policies because pod networking can be quite different.
