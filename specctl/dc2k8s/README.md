# Docker Compose to Kubernetes YAML conversion

The `specctl -m d2k`, that is, mode `Docker Compose to Kubernetes` will convert Compose files to Kubernetes YAMLs. The services section in Docker Compose is used to create - Kubernetes Service, Kubernetes Deployment, and the pod specification within the deployment. 

Simple example of `nginx`

```bash
specctl -m d2k -s tests/docker_compose/nginx/docker_compose.yml
```
**Note:** It is better to provide and convert one docker_compose file at a time. Why? Read on. 

Docker Compose relies heavily on files. For example, Compose can have `build` construct to build and use the container image. Or, `environment` can have values that are provided in `env` files. To handle these scenarios `-e, --env_file` option is added. In this `env_file` you can have all the values you want to assign to the environment variables and you can also set the build images. To avoid a mess of wrong value assignment and headaches of multiple env files and docker compose files, I recommend doing conversions one docker compose file at a time. You can always create a shell loop if you have many docker compose files to convert. 

An example with the environment file. The docker compose sample courtesy of open source project - [plane](https://github.com/makeplane/plane)

```bash
specctl -m d2k -s tests/docker_compose/plane/docker_compose.yml -e tests/docker_compose/plane/env
2023-06-08 22:56:48,110 [WARNING] specctl.dc2k8s.dc_parser: plane-web service has no container image. looking up ${BUILD_plane-web} in env file
2023-06-08 22:56:48,110 [WARNING] specctl.dc2k8s.dc_parser: BUILD_plane-web key is not found in env file
2023-06-08 22:56:48,111 [WARNING] specctl.dc2k8s.dc_parser: NEXT_PUBLIC_API_BASE_URL key is not found in env file
...
...
...
...
2023-06-08 22:56:48,149 [WARNING] specctl.dc2k8s.dc_parser: plane-proxy service has no container image. looking up ${BUILD_plane-proxy} in env file
2023-06-08 22:56:48,153 [Level 100] specctl.dc2k8s.dc_reader_writer: Please see ./output directory for kubernetes artifacts
```
**Note:** `plane-web-service` is using build construct. So we look for `${BUILD_plane-web}` in the passed `env_file` (the `-e` option). Naturally, first you run this you will not know what all build constructs are there. That is okay note the log messages, add the variables to the env file and re-run the command. The `specctl` will pick up the values from env file. Similarly, if there are environment variables with missing values, such as `NEXT_PUBLIC_API_BASE_URL` in above example, those are highlighted in the logger messages as well. 

We will update the below list as the support for Docker Compose evolves, in particular the service attributes:
- [X] Handle service, image, and ports
- [X] Build construct to build and use an image instead of image url
- [X] Handling replacement of environment variables  
- [ ] Command and entry point 
- [ ] Deploy 
- [ ] Config 
- [ ] Volumes 
- [ ] Side car via network mode matching
- [ ] Daemons / global deploy attribute
- [ ] ?