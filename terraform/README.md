* [core-infra/](./core-infra/) : to create ECS cluster, VPC and subnets
* [namespaces/](./namespaces/) : to create CloudMap namespaces by the same name as Kubernetes namespaces, and SSM Parameter Store for both ConfigMap and Secrets data obtained from Kubernetes.
* [ecs-lb-service](./ecs-lb-service/) : to create ECS service, and ALB along with appropriate security groups, target groups and CloudMap registry based on service namespace.
* [ecs-backend-service](./ecs-backend-service/) : to create ECS service and associate to appropriate CloudMap registry based on service namespace.