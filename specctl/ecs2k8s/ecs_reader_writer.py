# // Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# // SPDX-License-Identifier: Apache-2.0
import boto3
import botocore
import botocore.exceptions
from botocore.config import Config
from pick import pick
from .ecs_parser import ecs_parser, ssm_secret_parser, ingress_parser, namespace_parser
import os
import yaml
import base64
import logging


logger = logging.getLogger(__name__)

# gets namespace id from svc id 
# returns namespace name
def get_cloudmap_namespace(region_name, svc_registry_arn):
    sd_client = boto3.client('servicediscovery')
    if len(region_name) >0:
        sd_client = boto3.client("servicediscovery", config=Config(region_name = region_name))
    svc_id = svc_registry_arn.split("/")[-1]
    response = sd_client.get_service(Id=svc_id)
    svc = response.get("Service",{})
    namespace_id = svc.get("NamespaceId")
    response = sd_client.get_namespace(Id=namespace_id)
    namespace = response.get("Namespace")
    namespace_name = namespace.get("Name")
    return namespace_name

def get_listeners_and_rules(region_name, lb_arn, target_group_arn):
    return_listeners = []
    listeners = []
    elbv2_client = boto3.client('elbv2')
    if len(region_name) >0:
        elbv2_client = boto3.client("elbv2", config=Config(region_name = region_name))
    paginator = elbv2_client.get_paginator("describe_listeners")
    response_iterator = paginator.paginate(LoadBalancerArn=lb_arn)
    for i in response_iterator:
        listeners += i["Listeners"]
    for listener in listeners:
        listener["rules"]=[]
        listener_arn = listener.get("ListenerArn")
        paginator = elbv2_client.get_paginator("describe_rules")
        response_iterator = paginator.paginate(ListenerArn=listener_arn)
        for i in response_iterator:
            for r in i["Rules"]:
                actions = r.get("Actions",[])
                for action in actions:
                    type = action.get("Type")
                    if type is None or type != "forward":
                        continue
                    action_tg_arn = action.get("TargetGroupArn")
                    if action_tg_arn is None or action_tg_arn != target_group_arn: continue
                    listener["rules"].append(r)
        if len(listener["rules"])>0: return_listeners.append(listener)
    return return_listeners

def get_tg_details(region_name, target_group_arn):
    # get target group details
    elbv2_client = boto3.client('elbv2')
    if len(region_name) >0:
        elbv2_client = boto3.client("elbv2", config=Config(region_name = region_name))

    # todo: add exception handling 
    response = elbv2_client.describe_target_groups(TargetGroupArns=[target_group_arn])
    tgs = response.get("TargetGroups")
    if tgs is None or len(tgs)<=0: 
        logger.error("%s target group not found")
        return {}
    # we should only get 1 response!
    tg = tgs[0] 
    # get load balancer associated with target group 
    lb_arns = tg.get("LoadBalancerArns")
    if lb_arns is None or len(lb_arns) <= 0: 
        logger.error("%s target group has no associated load balancer"%(tg.get("TargetGroupName","")))
        return {}
    describe_lb_response = elbv2_client.describe_load_balancers(LoadBalancerArns=lb_arns)
    lb_description_list = describe_lb_response.get("LoadBalancers")
    if lb_description_list is None or len(lb_description_list)<=0:
        logger.error("ELB associated with %s target group couldn't be found")
        return {}
    # 1 target group can only be associated to 1 elb 
    tg["load_balancer"] = lb_description_list[0]
    tg_associated_lb_arn = tg["load_balancer"]["LoadBalancerArn"]
    # get listener and rules associated with target group
    tg["listeners"]= get_listeners_and_rules(region_name, tg_associated_lb_arn, target_group_arn)
    return tg

# ecs svc description returns svc_lbs as 
# [{"targetGroupArn":"", containerName:"", containerPort:xx}]
# below function will fetch all tg details and 
# add to the svc_lbs dictionary
def get_lb_details(region_name, svc_lbs):
    for lb in svc_lbs:
        tg_arn = lb.get("targetGroupArn")
        if tg_arn is None or len(tg_arn) <=0: continue
        tg_details = get_tg_details(region_name, tg_arn)
        lb["details"]=tg_details

def get_ssm_and_secrets(region_name, task_definition):
    already_seen={}
    ssm_client = boto3.client("ssm")
    secret_mgr_client = boto3.client('secretsmanager')
    if len(region_name) >0:
        ssm_client = boto3.client("ssm", config=Config(region_name = region_name))
        secret_mgr_client = boto3.client('secretsmanager', config=Config(region_name = region_name))
    container_definitions = task_definition.get("containerDefinitions",[])
    for cd in container_definitions:
        secrets = cd.get("secrets",[])
        for item in secrets:
            valueFrom = item.get("valueFrom", None)
            if valueFrom is None or valueFrom in already_seen:
                continue
            if "arn:aws:secretsmanager" in valueFrom:
                try:
                    response = secret_mgr_client.get_secret_value(SecretId=valueFrom)
                except botocore.exceptions.ClientError as error:
                    logger.error("Unable to get secret %s %s"%(valueFrom, error))
                if response is None:
                    continue
                name = response.get("Name","")
                type = "SecureString"
                value = base64.b64encode(response.get("SecretString","").encode("ascii")).decode("ascii")
            else:
                try:
                    response = ssm_client.get_parameter(Name=valueFrom,WithDecryption=True)
                except botocore.exceptions.ClientError as error:
                    logger.error("Unable to get parameter %s %s"%(valueFrom, error))
                if response is None: 
                    continue
                parameter = response.get("Parameter",{})
                name = parameter.get("Name","")
                type = parameter.get("Type","String")
                value = base64.b64encode(parameter.get("Value","").encode("ascii")).decode("ascii")
            if len(name)<=0:
                continue
            already_seen[valueFrom] = {"name":name, "value":value, "type":type}
            if type == "String":
               already_seen[valueFrom]["value"] = base64.b64decode(value.encode("ascii")).decode("ascii")
    return(already_seen)

def ecs_get_task_definition(client, task_definition):
    response = client.describe_task_definition(
        taskDefinition= task_definition,
        include=['TAGS']
    )
    return(response.get("taskDefinition", None))


def ecs_get_service_details(client, cluster_name, services):
    response = client.describe_services(
        cluster=cluster_name,
        services=services,
        include=['TAGS']
    )
    return(response.get("services",[]))


def pick_ecs_cluster(client):
    cluster_list = []
    paginator = client.get_paginator('list_clusters')
    response_iterator = paginator.paginate(
        PaginationConfig={
            'MaxItems': 5000,
            'PageSize': 100,
        }
    )
    for i in response_iterator:
        cluster_list = cluster_list+i["clusterArns"]
    if len(cluster_list)<=0:
        logger.critical("No ECS clusters found. Check AWS_REGION setting or pass --region_name")
        exit()
    option, _ = pick(cluster_list, title="Pick the ECS cluster to use",
                     default_index=0)
    logger.info("Selected ECS cluster is %s"%(option))
    return(option.split("cluster/")[1])

def write_yaml(filename, spec_list):
    logging.info("Writing K8s spec to %s"%(filename))
    yaml.Dumper.ignore_aliases = lambda self, data: True
    with open(filename, 'w') as kf:
      for spec in spec_list:
          kf.write(yaml.dump(spec, Dumper=yaml.Dumper))
          kf.write("---\n")


def ecs_reader_writer(options):
    client = boto3.client("ecs")
    region_name = options.get("region_name","")
    if len(region_name)>0:
        client = boto3.client("ecs", config=Config(region_name = region_name))

    cluster_name = options.get("cluster_name", "")
    if len(cluster_name)<=0:
        cluster_name = pick_ecs_cluster(client)

    cluster_output_dir = os.path.join(options.get("output_directory"), cluster_name)
    try:
        os.makedirs(cluster_output_dir)
    except FileExistsError:
        pass
    paginator = client.get_paginator('list_services')
    response_iterator = paginator.paginate(
        cluster = cluster_name,
        launchType = "FARGATE",
        schedulingStrategy = "REPLICA",
        PaginationConfig={
            'MaxItems': 5000,
            'PageSize': 10,
        }
    )
    for i in response_iterator:
        svc_details = ecs_get_service_details(client, cluster_name, i['serviceArns'])
        for svc_def in svc_details:
            svc_name = svc_def.get("serviceName","")
            if len(svc_name) <=0:
                logger.error("Skipping ECS service without name")
                continue

            task_def_arn = svc_def.get("taskDefinition")
            if task_def_arn is None:
                logger.error("Skipping service %s that has no task definition"%(svc_name))
                continue
            task_def = ecs_get_task_definition(client, task_def_arn) 
            k8s_secrets_and_configmaps = get_ssm_and_secrets(region_name, task_def)
            svc_lbs = svc_def.get("loadBalancers")
            if svc_lbs is not None and len(svc_lbs)>0:
                get_lb_details(region_name, svc_lbs)
            
            svc_namespace = ""
            svc_registries = svc_def.get("serviceRegistries")
            if svc_registries is not None and len(svc_registries) > 0:
                svc_registry_arn = svc_registries[0].get("registryArn")
                if svc_registry_arn is not None and len(svc_registry_arn)>0:
                    svc_namespace = get_cloudmap_namespace(region_name, svc_registry_arn)
                
            output_dir = os.path.join(cluster_output_dir, svc_name)
            try:
                os.makedirs(output_dir)
            except FileExistsError:
                pass
            k8s_yamls = ecs_parser(svc_def, task_def, k8s_secrets_and_configmaps)
            for k,v in k8s_yamls.items():
                if k == "security_group_policy" and not options.get("sgp"): continue
                k8s_file = os.path.join(output_dir, svc_name+"_"+k+".yaml")
                write_yaml(k8s_file,[v])

            k8s_yamls = ssm_secret_parser(k8s_secrets_and_configmaps)
            for k,v in k8s_yamls.items():
                k8s_file = os.path.join(output_dir, k+".yaml")
                write_yaml(k8s_file, v)
    
            k8s_yamls = ingress_parser(svc_def, svc_lbs)
            for k,v in k8s_yamls.items():
                k8s_file = os.path.join(output_dir, k+".yaml")
                write_yaml(k8s_file, v)

            if len(svc_namespace) > 0:
                k8s_ns = namespace_parser(svc_namespace)
                for k,v in k8s_ns.items():
                    k8s_file = os.path.join(output_dir, k+".yaml")
                    write_yaml(k8s_file, [v])
                
                

    logger.log(100, "Please see %s directory for kubernetes artifacts" %(options.get("output_directory")))



