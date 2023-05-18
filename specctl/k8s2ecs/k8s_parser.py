# // Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# // SPDX-License-Identifier: Apache-2.0
import base64
import json
from ..utils import dict_check, vcpu_k8s_to_ecs, mem_k8s_to_ecs, get_fargate_sku
from .ingress import k8s_ingress_handler, merge_ingress, create_ingress_target_groups
import logging

logger = logging.getLogger(__name__)

# For a particular resource, a Pod resource request/limit is the sum of 
# the resource requests/limits of that type for each container in the Pod.
# this function will generate the nearest fitting Fargate SKU
# based on the max of total for limit and total for reservation
def get_task_size(containers):
    task_cpu_rsrv = 0
    task_mem_rsrv = 0
    task_cpu_limit = 0
    task_mem_limit = 0
    for c in containers:
        task_cpu_rsrv += c.get("cpu",0)
        task_mem_rsrv += c.get("memory_reservation",0)
        task_cpu_limit += c.get("cpu_limit",0)
        # ECS doesn't have container level CPU limit
        if "cpu_limit" in c:
            c.pop("cpu_limit")
        task_mem_limit += c.get("memory",0)  
    return get_fargate_sku(max(task_cpu_limit, task_cpu_rsrv), max(task_mem_limit, task_mem_rsrv))

# this function parses the cpu and memory resource specifications
# converts them to ecs cpu and memory units 
# and assigns to the appropriate ECS container def attributes
def k8s_container_resource_handler(resources):
    output_dict = {}
    if not dict_check(resources): return output_dict

    requests = resources.get("requests")
    if requests is not None:
        cpu_reservation = requests.get("cpu")
        if cpu_reservation is not None:
            output_dict["cpu"] = vcpu_k8s_to_ecs(cpu_reservation)
        mem_reservation = requests.get("memory")
        if mem_reservation is not None:
            output_dict["memory_reservation"] = mem_k8s_to_ecs(mem_reservation)
    limits = resources.get("limits")
    if limits is not None:
        cpu_limit = limits.get("cpu")
        if cpu_limit is not None:
            output_dict["cpu_limit"] = vcpu_k8s_to_ecs(cpu_limit)
        mem_limit = limits.get("memory")
        if mem_limit is not None:
            output_dict["memory"] = mem_k8s_to_ecs(mem_limit)           
    return output_dict

def k8s_container_spec_handler(dep_container_spec_dict, dependencies=[]):
    output_dict = {}
    if not dict_check(dep_container_spec_dict): return output_dict
    output_dict["name"]=dep_container_spec_dict.get("name")
    output_dict["image"]=dep_container_spec_dict.get("image")
    resources = dep_container_spec_dict.get("resources",{})
    output_dict.update(k8s_container_resource_handler(resources))
    output_dict["port_mappings"]=dep_container_spec_dict.get("ports",[])
    env_vars = dep_container_spec_dict.get("env",[])
    output_dict["environment"]= []
    output_dict["secrets"] = []
    liveness_probe = dep_container_spec_dict.get("livenessProbe")
    if liveness_probe is not None:
        http_get = liveness_probe.get("httpGet")
        if http_get is not None:
            output_dict["http_get_liveness_probe"] = liveness_probe
    for ev in env_vars:
        name = ev.get("name")
        value = ev.get("value")
        valueFrom = ev.get("valueFrom")
        if name is not None and value is not None:
            output_dict["environment"].append({"name":name,"value":value})
        if name is not None and valueFrom is not None:
            cfgmap = None
            # either refers to value from ConfigMap or from Secret
            if "configMapKeyRef" in valueFrom.keys():
                cfgmap = valueFrom.get("configMapKeyRef")
            if "secretKeyRef" in valueFrom.keys():
                cfgmap = valueFrom.get("secretKeyRef")
            if cfgmap is not None:
                cfgmap_name = cfgmap.get("name")
                cfgmap_key = cfgmap.get("key")
                ssm_parameter = "/"+cfgmap_name+"/"+cfgmap_key
                output_dict["secrets"].append({"name":name,"valueFrom":ssm_parameter})
    output_dict["envFrom"] = dep_container_spec_dict.get("envFrom",[])
    output_dict["command"] = dep_container_spec_dict.get("command",[])
    output_dict["dependencies"] = dependencies

    return output_dict

def k8s_pod_containers_handler(containers_list, init_containers_list=[]):
    dependencies = []
    return_container_spec_list = []
    for init_container in init_containers_list:
        condition = "SUCCESS"
        containerName = init_container.get("name")
        if containerName is None or len(containerName) <=0 :
            continue
        dependencies.append({"condition":condition, "containerName":containerName})
    for c in containers_list:
        return_container_spec_list.append(k8s_container_spec_handler(c, dependencies))
    for c in init_containers_list:
        init_container_spec = k8s_container_spec_handler(c)
        init_container_spec["essential"]=False
        return_container_spec_list.append(init_container_spec)
    return return_container_spec_list
    
# From deployment template get the containers and the tags
# The tags will go to the task tags
# see k8s_container_spec_handler
def k8s_deployment_template_handler(dep_temp_dict):
    output_dict = {}
    if not dict_check(dep_temp_dict): return output_dict
    metadata = dep_temp_dict.get("metadata")
    if dict_check(metadata):
        output_dict["task_tags"]=metadata.get("labels",{})
    spec = dep_temp_dict.get("spec")
    if dict_check(spec):
        output_dict["service_account_name"] = spec.get("serviceAccountName","")
        containers_list = spec.get("containers",[])
        init_containers_list = spec.get("initContainers",[])
        output_dict["containers"]=k8s_pod_containers_handler(containers_list, init_containers_list)
        output_dict.update(get_task_size(output_dict["containers"])) 
    return output_dict

# This is mainly converting the maxUnavailable and maxSurge
# to ECS minimum_healthy_percent and max_percent
# K8s maxUnavailable:25% == ECS minimum_healthy_percent:75% (100-25)
# K8s maxSurge:25% == ECS maximum_percent:125% (100+25)
# ECS doesn't support absolute and in that we use ECS default
def k8s_deployment_strategy_handler(dep_strategy_dict):
    output_dict = {}
    if not dict_check(dep_strategy_dict): return output_dict
    dep_strategy = dep_strategy_dict.get("rollingUpdate")
    if dep_strategy is None: return output_dict
    deployment_minimum_healthy_percent = 100
    deployment_maximum_percent = 200
    maxUnavailable = dep_strategy.get("maxUnavailable","25%")
    maxSurge = dep_strategy.get("maxSurge","25%")

    # ECS only supports percent values and not absolutes
    # ECS default for min healthy percent is 100%, K8s is 75% (100-25)
    # ECS default for max healthy percent is 200%, K8s default is 125 (100+25)

    if "%" in str(maxUnavailable):
        lower_limit= int(maxUnavailable.strip("%"))
        deployment_minimum_healthy_percent = max(0, deployment_minimum_healthy_percent-lower_limit)
    if "%" in str(maxSurge):
        upper_limit= int(maxSurge.strip("%"))
        deployment_maximum_percent = min(deployment_maximum_percent,100+upper_limit)
    output_dict["deployment_minimum_healthy_percent"]=deployment_minimum_healthy_percent
    output_dict["deployment_maximum_percent"]=deployment_maximum_percent
    return output_dict

def k8s_deployment_spec_handler(dep_spec_dict):
    output_dict = {}
    if not dict_check(dep_spec_dict): return output_dict
    output_dict["desired_count"]=dep_spec_dict.get("replicas",1)
    output_dict.update(k8s_deployment_template_handler(dep_spec_dict.get("template")))
    output_dict.update(k8s_deployment_strategy_handler(dep_spec_dict.get("strategy")))
    return output_dict

# K8s deployment name will become ECS service name
# if K8s service is also defined then K8s service name is picked for ECS service name
# K8s deployment labels will be added to ECS service tags
def k8s_deployment_metadata_handler(dep_meta_dict):
    output_dict = {}
    if not dict_check(dep_meta_dict): return output_dict
    output_dict["deployment_name"] = dep_meta_dict.get("name")
    output_dict["deployment_namespace"] = dep_meta_dict.get("namespace","")
    output_dict["deployment_tags"] = dep_meta_dict.get("labels",{})
    # ignore deployment namespace? we cud add this as a svc tag?
    return output_dict

def k8s_deployment_handler(dep_dict):
    output_dict = {}
    if not dict_check(dep_dict): return output_dict
    output_dict.update(k8s_deployment_metadata_handler(dep_dict.get("metadata")))
    output_dict.update(k8s_deployment_spec_handler(dep_dict.get("spec")))
    return output_dict

# This is currently only handling K8s service type ClusterIP and LoadBalancer

def k8s_service_handler(svc_dict):
    output_dict = {}
    if not dict_check(svc_dict): return output_dict
    metadata = svc_dict.get("metadata")
    if metadata is not None:
        output_dict["service_name"]=metadata.get("name")
        output_dict["service_tags"]=metadata.get("labels",{})
        output_dict["service_namespace"]=metadata.get("namespace","")
    spec = svc_dict.get("spec")
    if dict_check(spec):
        output_dict["label_selector"] = spec.get("selector",{})
    output_dict["service_type"] = spec.get("type", "ClusterIP")
    ports = spec.get("ports")
    if ports is not None:
        output_dict["lb_ports"]=[]
        for p in ports:
            listener_port = p.get("port")
            service_port = listener_port
            output_dict["service_tags"]["k8s_service"]=str("%s:%s"%(output_dict["service_name"],\
                                                                       str(listener_port)))
            #k8s default is port == targetPort
            target_port = p.get("targetPort")
            if target_port is None:
                target_port = listener_port
            else:
                listener_port = target_port
           # protocol = p.get("protocol", "TCP")
           # for now skip the NLB just focus on ALB
            protocol = "HTTP"
            output_dict["lb_ports"].append({
                "listener_port": listener_port,
                "listener_protocol": protocol,
                "lb_container_port": target_port,
                "service_port_name": p.get("name",""),
                "service_port": service_port 
            })
    return output_dict

def k8s_pod_handler(pod_dict):
    output_dict = {}
    if not dict_check(pod_dict): return output_dict
    metadata = pod_dict.get("metadata")
    if dict_check(metadata):
        output_dict["task_name"]=metadata.get("name")
        output_dict["task_tags"]=metadata.get("labels",{})

    spec = pod_dict.get("spec")
    if dict_check(spec):
        output_dict["service_account_name"] = spec.get("serviceAccountName","")
        containers_list = spec.get("containers",[])
        init_containers_list = spec.get("initContainers",[])
        output_dict["containers"]=k8s_pod_containers_handler(containers_list, init_containers_list)   
    return output_dict

# The K8s ConfigMap is transformed as follows so that it can be created
# and stored in SSM Parameter Store
# apiVersion: v1
#   kind: ConfigMap
#   metadata:
#     name: special-config
#     namespace: default
#   data:
#     special.how: very
# ==>
# ssm_parameters = [
#   {
#     "name" = "/special-config/special.how",
#     "value" = "very"
#   }
# ]
#

def k8s_config_handler(config_dict):
    ssm_parameter_list = []
    if not dict_check(config_dict): return ssm_parameter_list
    metadata = config_dict.get("metadata")
    if not dict_check(metadata):
        return ssm_parameter_list
    
    data = config_dict.get("data",{})
    if data is None:
        return ssm_parameter_list
   
    name = metadata.get("name","")
    ssm_parameter_prefix = "/"+name+"/"
    for k,v in data.items():
        ssm_parameter = ssm_parameter_prefix+k
        ssm_parameter_list.append({"name":ssm_parameter, "value":v})
    return ssm_parameter_list

# The K8s Secret is transformed as follows so that it can be created
# and stored in AWS Secrets Manager or SSM Parameter Store
# apiVersion: v1
# data:
#   username: YWRtaW4=
#   password: MWYyZDFlMmU2N2Rm
# kind: Secret
# metadata:
#   name: mysecret
#   namespace: default
# type: Opaque
# ==>
# ssm_secrets = [
#   {
#     "name" = "/mysecret/username",
#     "value" = "YWRtaW4="
#   },
#   {
#     "name" = "/mysecret/password",
#     "value" = "MWYyZDFlMmU2N2Rm"
#   }
# when creating the secret in Secrets Manager or SSM Parameter Store
# decode the base64 encoded secret_value string
#
# Any plain stringData type secret is also base64 encoded

def k8s_secret_handler(secret_dict):
    secret_parameter_list = []
    if not dict_check(secret_dict): return secret_parameter_list
    metadata = secret_dict.get("metadata")
    if not dict_check(metadata):
        return secret_parameter_list
    data = secret_dict.get("data",{})
    stringData = secret_dict.get("stringData",{})

    name = metadata.get("name","")
    secret_parameter_prefix = "/"+name+"/"

    if dict_check(data):
        for k,v in data.items():
            secret_parameter = secret_parameter_prefix + k
            secret_parameter_list.append({"name":secret_parameter, "value":v})
    
    if dict_check(stringData):
        for k,v in stringData.items():
            secret_parameter = secret_parameter_prefix + k
            valueb64 = base64.b64encode(v.encode("ascii")).decode("ascii")
            secret_parameter_list.append({"name":secret_parameter, "value":valueb64})

    return secret_parameter_list

# checks if d1 subset of d2
def check_subset(d1, d2):
    return(set(d1.items()).issubset(set(d2.items())))


# In K8s deployments (/pods) and services are independent objects
# services associate to pods via label selectors
# the below function will find and associate right deployments and service together
# it will make deployment object part of the service dictionary
# the service label selector should be subset of the pod labels
def associate_svc_to_dep(services, deployments):
    return_services = []
    remaining_deployments = deployments
    for svc in services:
        label_selector = svc.get("label_selector",{})
        svc_namespace = svc.get("service_namespace","")
        for dep in deployments:
            dep_namespace = dep.get("deployment_namespace","")
            if svc_namespace != dep_namespace: continue 
            # in the deployment get the pod labels
            task_tags = dep.get("task_tags",{})
            # check if label_selector is subset of task_tags
            if check_subset(label_selector, task_tags):
                svc["deployment"]=dep
                remaining_deployments.remove(dep)
                break
        return_services.append(svc)

    # for remaining deployments put them under simple service
    # where service name == deployment name
    for dep in remaining_deployments:
        new_svc = {}
        new_svc["deployment"]=dep
        new_svc["service_name"]=dep.get("deployment_name")
        new_svc["service_namespace"]=dep.get("deployment_namespace","")
        return_services.append(new_svc)
    return(return_services)

def get_data_from_config_and_secrets(name, configs_and_secrets):
    for cfg in configs_and_secrets:
        metadata = cfg.get("metadata")
        if metadata is not None:
            cfg_name = metadata.get("name")
            if cfg_name is not None and cfg_name == name:
                cfg_data = cfg.get("data")
                if cfg_data is None:
                    cfg_data = {}
                return(cfg_data)
    return({})

# K8s has envFrom concept where you can load
# entire key value pairs from ConfigMap or Secret
# this is done as a post processing step

def fill_envfrom(svcs, configs_and_secrets):
    for svc in svcs:
        dep = svc.get("deployment",{})
        containers = dep.get("containers","")
        for c in containers:
            envFrom = c.get("envFrom", [])
            if envFrom is None:
                continue
            for ref in envFrom:
                for k, v in ref.items():
                    name = v.get("name")
                    if name is None:
                        continue
                    env_data = get_data_from_config_and_secrets(name, configs_and_secrets)
                    for env_key, env_value in env_data.items():
                        c["environment"].append({"name":env_key, "value":env_value})
            c.pop("envFrom")
    return            

# In k8s multiple services can reference same deployment/pods
# but in ECS there is only one service, so this function merges services
# if svc1 == svc2 then the first service name is picked 
# all service names are added as labels
# if any of them is of type LoadBalancer then service type is set to that
def merge_services(services):
    services_without_deployments = []
    for svc in services:
        dep = svc.get("deployment")
        if dep is None:
            logger.warning("Found %s either headless or redundant service"%(svc.get("service_name","")))
            services_without_deployments.append(svc)
            services.remove(svc)
    for svc1 in services_without_deployments:
        label_selector1 = svc1.get("label_selector",{})
        n1 = svc1.get("service_namespace","")
        name1 = svc1.get("service_name", "")
        type1 = svc1.get("service_type", "ClusterIP")
        if not dict_check(label_selector1) or \
            name1 is None or len(name1) <=0 or \
            n1 is None or len(n1) <= 0 :
            logger.warning("Skipping headless service %s"%(str(name1)))
            continue
        for svc2 in services:
            label_selector2 = svc2.get("label_selector",{})
            n2 = svc2.get("service_namespace","")
            name2 = svc2.get("service_name", "")
            type2 = svc2.get("service_type","ClusterIP")
            if not dict_check(label_selector2) or \
                name2 is None or len(name2) <=0 or \
                n2 is None or len(n2) <= 0 : 
                continue
            if not n1 == n2: continue
            if name1 == name2: continue
            if len(label_selector1.keys()) != len(label_selector2.keys()): continue
            if label_selector1 == label_selector2:
                if type1 == "LoadBalancer" or type2 == "LoadBalancer":
                    svc2["service_type"] = "LoadBalancer"
    return

def handle_named_ports(services):
    for svc in services:
        service_tags = svc.get("service_tags",{})
        service_name = svc.get("service_name")
        if service_name is None: continue
        ports = svc.get("lb_ports",{})
        if not dict_check(ports):
            logger.warning("%s service has no ports"%(service_name))
            continue
        for p in ports:
            targetPort = p.get("lb_container_port")
            if targetPort is None: 
                logger.warning("%s service doesn't have target port"%(str(svc.get("service_name",""))))
                continue 
            dep = svc.get("deployment")
            if dep is None: 
                logger.warning("%s service has no deployment"%(str(svc.get("service_name",""))))
                continue
            containers = dep.get("containers",[])
            if containers is None: continue
            for c in containers:
                port_mappings = c.get("port_mappings",[])
                for pm in port_mappings:
                    port_name = pm.get("name","")
                    port_number = pm.get("containerPort")
                    if port_number is None: continue
                    if (type(targetPort) is int and targetPort == port_number) or (targetPort == port_name):
                        p["lb_container_port"] = port_number
                        p["listener_port"] = port_number
                        p["lb_container_name"] = c.get("name","")
                        service_tags["ecs_service"]=str("%s:%s"%(service_name, str(port_number)))
                        break
    return

def configure_lb_health_check(services):
    special_case = "/actuator/health"
    for svc in services:
        dep = svc.get("deployment")
        if dep is None: 
            continue
        containers = dep.get("containers",[])
        if containers is None: continue
        for c in containers:
            http_get_liveness_probe = c.get("http_get_liveness_probe")
            if http_get_liveness_probe is None:
                continue
            http_get = http_get_liveness_probe.get("httpGet")
            svc["lb_health_check_path"]=http_get.get("path","/")
            svc["health_check_grace_period_seconds"]= http_get.get("initialDelaySeconds", 45)
            if svc["lb_health_check_path"].startswith(special_case):
                svc["lb_health_check_path"]=special_case
            c.pop("http_get_liveness_probe")
    return


def k8s_sa_handler(sa_dict):
    output_dict = {}
    if not dict_check(sa_dict): return output_dict
    metadata = sa_dict.get("metadata")
    if metadata is None: return output_dict
    output_dict["sa_name"]=metadata.get("name","")
    output_dict["sa_namespace"]=metadata.get("namespace","")
    output_dict["sa_labels"]= metadata.get("labels",{})
    annotations = metadata.get("annotations",{})
    output_dict["pod_iam_role_arn"] = annotations.get("eks.amazonaws.com/role-arn","")
    return output_dict

def associate_task_iam_role(services, service_accounts):
    for svc in services:
        dep = svc.get("deployment")
        if dep is None: continue
        dep_svc_account = dep.get("service_account_name","")
        dep_namespace = dep.get("deployment_namespace","")
        if dep_svc_account is None or len(dep_svc_account)<=0: continue
        for sa in service_accounts:
            sa_name = sa.get("sa_name")
            sa_namespace = sa.get("sa_namespace","")
            if sa_name is None or sa_name != dep_svc_account: continue 
            if sa_namespace != dep_namespace: continue 
            pod_iam_role_arn = sa.get("pod_iam_role_arn","")
            if pod_iam_role_arn is None or len(pod_iam_role_arn) <=0: continue
            dep["create_tasks_iam_role"]=False
            dep["tasks_iam_role_arn"]=pod_iam_role_arn

# the matchLabels in pod or service account selector
# when {} it means all pods in that namespaces 
# and all SAs in that namespaces
def k8s_sgp_handler(sgp_dict):
    output_dict = {}
    if not dict_check(sgp_dict): return output_dict
    metadata = sgp_dict.get("metadata")
    if metadata is None: return output_dict
    output_dict["sgp_name"]=metadata.get("name","")
    output_dict["sgp_namespace"]=metadata.get("namespace","")
    spec = sgp_dict.get("spec",{})
    output_dict["pod_selector"] = None 
    output_dict["sa_selector"] = None
    pod_selector = spec.get("podSelector")
    if pod_selector is not None: 
        output_dict["pod_selector"]=pod_selector.get("matchLabels")
    sa_selector = spec.get("serviceAccountSelector")
    if sa_selector is not None:
        output_dict["sa_selector"]=pod_selector.get("matchLabels")
    sgps = spec.get("securityGroups",{})
    output_dict["sgp_ids"]=[]
    if dict_check(sgps):
        output_dict["sgp_ids"]=sgps.get("groupIds",[])
    return output_dict

def associate_sgp_to_pod(sgps, sas, svcs):
    #first associate any service account with sgp
    for sgp in sgps:
        sgp["sa_names"] = []
        sgp_namespace = sgp.get("sgp_namespace")
        if sgp_namespace is None: continue
        sa_selector = sgp.get("sa_selector")
        if sa_selector is None: continue 
        for sa in sas:
            sa_namespace = sa.get("sa_namespace")
            if sa_namespace is None or sa_namespace != sgp_namespace: continue
            sa_labels = sa.get("labels")
            if not check_subset(sa_selector,sa_labels): continue
            sgp["sa_names"].append(sa.get("sa_name"))
    for sgp in sgps:
        sgp_namespace = sgp.get("sgp_namespace")
        if sgp_namespace is None: continue
        sa_selector = sgp.get("sa_selector")
        pod_selector = sgp.get("pod_selector")
        if sa_selector is None and pod_selector is None: continue
        for svc in svcs:
            svc_namespace = svc.get("service_namespace")
            if svc_namespace is None: continue
            if svc_namespace != sgp_namespace: continue
            dep = svc.get("deployment")
            dep_sa = dep.get("service_account_name")
            if sa_selector is not None and dep_sa is not None:
                if dep_sa in sgp["sa_names"]:
                    if len(sgp["sgp_ids"])>0:
                        dep["security_group_ids"]=sgp["sgp_ids"]
                        dep["create_security_group"]=False
            task_labels = dep.get("task_tags",{})
            if pod_selector is not None and check_subset(pod_selector, task_labels):
                if len(sgp["sgp_ids"])>0:
                    dep["security_group_ids"]=sgp["sgp_ids"]
                    dep["create_security_group"]=False

# The dictionary objects for input are K8s specifications.
# These spec are then further parsed to extract relevant informtation from K8s objects
# such as deployments, secrets, configmap, service, pod, and container
# if you want to parse any new object just expand the "if" section below
# and create a corresponding object handler function
# Service Account, HPA and Ingress are couple of extension opportunities
def k8s_parser(dict_list):
    output_dict = {}
    for k in ["deployments", "services", "pods", "configmaps", "ingress"]:
        output_dict[k]=[]

    ingress_list = []
    ssm_parameter_list=[]
    secret_parameter_list=[]
    configs_and_secrets = []
    service_accounts = []
    security_groups = []
    for k8s_obj in dict_list:
        if k8s_obj is None:
            continue
        kind = k8s_obj.get("kind","")
        if kind == "Deployment":
            output_dict["deployments"].append(k8s_deployment_handler(k8s_obj))
        if kind == "Service":
            output_dict["services"].append(k8s_service_handler(k8s_obj))
        if kind == "Pod":
            output_dict["pods"].append(k8s_pod_handler(k8s_obj))
        if kind == "ConfigMap":
            ssm_parameter_list+=k8s_config_handler(k8s_obj)
            configs_and_secrets.append(k8s_obj)
        if kind == "Secret":
            secret_parameter_list+=k8s_secret_handler(k8s_obj)
            configs_and_secrets.append(k8s_obj)
        if kind == "Ingress":
            ingress_list.append(k8s_ingress_handler(k8s_obj))
        if kind == "ServiceAccount":
            service_accounts.append(k8s_sa_handler(k8s_obj))
        if kind == "SecurityGroupPolicy":
            security_groups.append(k8s_sgp_handler(k8s_obj))

    output_dict["configmaps"]=[{"ssm_parameters":ssm_parameter_list}]
    output_dict["secrets"]=[{"ssm_secrets":secret_parameter_list}]

    # associate services to deployments
    associated_services = associate_svc_to_dep(output_dict["services"],output_dict["deployments"])
    merge_services(associated_services)
    associate_task_iam_role(associated_services, service_accounts)
    associate_sgp_to_pod(security_groups, service_accounts, associated_services)
    fill_envfrom(associated_services, configs_and_secrets)
    handle_named_ports(associated_services)
    configure_lb_health_check(associated_services)
    create_ingress_target_groups(ingress_list, associated_services)
    output_dict["ingress"]=merge_ingress(ingress_list)
    output_dict["services"]=associated_services
    namespaces=[]
    for svc in associated_services:
        svc_namespace = svc.get("service_namespace")
        if svc_namespace is not None and len(svc_namespace)>0:
            namespaces.append(svc_namespace)
    output_dict["namespaces"]=[*set(namespaces)]

    # print(output_dict)
    return(output_dict)
