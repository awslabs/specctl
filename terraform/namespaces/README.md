This terraform module creates
* CloudMap namespaces where the ECS services will be registered. One of the roles of Kubernetes namespaces is that they serve as the domain qualified for a Kubernetes service. Similarly, in ECS, the CloudMap namespace serves as the domain qualifier and CloudMap serves as the registry.
* SSM Parameter simple string parameters are created based on the Kubernetes ConfigMap objects parsed by `specctl`
* SSM Parameter SecureString parameters are create based on the Kubernetes Secrets objects parsed by `specctl`. Note that the `ssm_secrets` object should have base64encoded value.
