# // Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# // SPDX-License-Identifier: Apache-2.0
from . import k8s_objects
import json
import copy
import re
from ..utils import dict_check
import logging

logger = logging.getLogger(__name__)

def k8s_conform(input_string):
    return(re.sub("[^a-zA-Z0-9]+","-", input_string).lower())

def get_pod_iam(task_def, k8s_svc_account):
    pod_iam = task_def.get("taskRoleArn")
    if pod_iam is not None and len(pod_iam) > 0 :
        k8s_svc_account["metadata"]["annotations"]["eks.amazonaws.com/role-arn"] = pod_iam
    return

def get_pod_sgp(svc_def, k8s_sgp):
     nc = svc_def.get("networkConfiguration")
     if nc is None: return
     awsvpcConfig = nc.get("awsvpcConfiguration")
     if awsvpcConfig is None: return
     sgps = awsvpcConfig.get("securityGroups")
     if sgps is None: return
     k8s_sgp["spec"]["securityGroups"]["groupIds"]=sgps

def get_pod_containers(task_def, k8s_secrets_and_configmaps):
    pod_containers = []
    task_def_containers = task_def.get("containerDefinitions",[])
    for task_container in task_def_containers:
        pod_container = copy.deepcopy(k8s_objects.K8S_POD_CONTAINER)
        ports = []
        pod_container["image"] = task_container.get("image")
        pod_container["name"]  = task_container.get("name")
        portMappings = task_container.get("portMappings",[])
        for pm in portMappings:
            ports.append({"containerPort":pm.get("containerPort"),"protocol":pm.get("protocol","TCP").upper()})
        pod_container["ports"]=ports 
        pod_container["env"] = task_container.get("environment",[])
        pod_containers.append(pod_container)
        secrets = task_container.get("secrets",[])
        for sec in secrets:
            valueFrom = sec.get("valueFrom","")
            name = sec.get("name","")
            if len(name) <=0 or len(valueFrom) <= 0:
                logger.warning("Potential key value error in secret %s:%s in task def %s:%s container %s "%(name, valueFrom, task_def.get("family"), task_def.get("revision"), task_container.get("name")))
                continue
            value = k8s_secrets_and_configmaps.get(valueFrom)
            if value is None:
                logger.error("Did not find value for %s used in %s:%s container %s"%(valueFrom, task_def.get("family"), task_def.get("revision"), task_container.get("name")))
            cfg_or_secret = "configMapKeyRef"

            type = value.get("type")
            if type is not None and type == "SecureString":
                cfg_or_secret = "secretKeyRef"
                
            env_obj = {
                "name" : sec.get("name"),
                "valueFrom": {
                    cfg_or_secret : {
                        "name" : k8s_conform(valueFrom.split("secret:")[-1]),
                        "key"  : k8s_conform(value.get("name"))
                    }
                }
            }
            pod_container["env"].append(env_obj)
    return pod_containers
        
# for each target group and listener port there is 1 ingress
# ingress name is <target-group-name>-<listener-port>

def ingress_parser(svc_def, svc_lbs):
    k8s_ingress_list = []
    svc_name = k8s_conform(svc_def.get("serviceName"))
    alb_anno_prefix = "alb.ingress.kubernetes.io/"
    for lb in svc_lbs:
        annotations = {}
        tg_arn = lb.get("targetGroupArn")
        container_port = lb.get("containerPort")
        backend = { 
            "service": {
                "name": svc_name,
                "port" : {
                    "number": container_port
                }
            }
        }
        tg_details = lb.get("details")
        tg_name = tg_details.get("TargetGroupName")
        annotations[alb_anno_prefix+"healthcheck-path"] = tg_details.get("HealthCheckPath","/")
        annotations[alb_anno_prefix+"healthcheck-protocol"] = tg_details.get("HealthCheckProtocol","HTTP")
        annotations[alb_anno_prefix+"healthcheck-interval-seconds"]=json.dumps(tg_details.get("HealthCheckIntervalSeconds", 30))
        annotations[alb_anno_prefix+"healthcheck-timeout-seconds"] = json.dumps(tg_details.get("HealthCheckTimeoutSeconds", 5))
        annotations[alb_anno_prefix+"healthy-threshold-count"] = json.dumps(tg_details.get("HealthyThresholdCount", 3))
        annotations[alb_anno_prefix+"unhealthy-threshold-count"] = json.dumps(tg_details.get("UnhealthyThresholdCount", 3))
        annotations[alb_anno_prefix+"target-type"] = "ip"
        annotations[alb_anno_prefix+"ip-address-type"] = "dualstack"
        matcher = tg_details.get("Matcher")
        if matcher is not None:
            annotations[alb_anno_prefix+"success-codes"] = matcher.get("HttpCode", "200-299")
        lb_details = tg_details.get("load_balancer")
        annotations[alb_anno_prefix+"group.name"] = lb_details.get("LoadBalancerName")
        annotations[alb_anno_prefix+"scheme"] = lb_details.get("Scheme","internet-facing")
        listeners = tg_details.get("listeners")
        for l in listeners:
            l_arn = l.get("ListenerArn")
            l_port = l.get("Port")
            l_protocol = l.get("Protocol")
            if l_protocol == "HTTPS":
                certs = l.get("Certificates")
                if certs is None or len(certs) <=0:
                    logger.error("%s listener has HTTPS listener without certificate"%(l_arn))
                else:
                    annotations[alb_anno_prefix+"certificate-arn"]=json.dumps(certs[0].get("CertificateArn",""))
                    annotations[alb_anno_prefix+"ssl-policy"]=json.dumps(l.get("SslPolicy","ELBSecurityPolicy-TLS-1-1-2017-01"))
            annotations[alb_anno_prefix+"listen-ports"]=json.dumps([{l_protocol:l_port}])
            l_rules = l.get("rules")
            ingress_rules = []
            for rule in l_rules:
                host_header = []
                paths = []
                conditions = rule.get("Conditions",[])
                for condition in conditions:
                    path_pattern_config = condition.get("PathPatternConfig")
                    if not dict_check(path_pattern_config): continue
                    paths += path_pattern_config.get("Values",[])
                if len(paths)<=0:
                    paths = ["/"]
                for path in paths:
                    k8s_ingress_rule = copy.deepcopy(k8s_objects.K8S_INGRESS_RULE_PATH)
                    k8s_ingress_rule["path"] = path[:-2] if path.endswith("/*") else path
                    k8s_ingress_rule["pathType"] = "Prefix"
                    k8s_ingress_rule["backend"] = backend
                    ingress_rules.append(k8s_ingress_rule)
                
            k8s_ingress = copy.deepcopy(k8s_objects.K8S_INGRESS)
            k8s_ingress["metadata"]["name"] = k8s_conform(tg_name+"-"+l_protocol+"-"+str(l_port))
            k8s_ingress["metadata"]["annotations"]=copy.deepcopy(annotations)
            k8s_ingress["spec"]["rules"].append({"http":{"paths":ingress_rules}})
            k8s_ingress_list.append(k8s_ingress)   
    return {"ingress":k8s_ingress_list}

def ssm_secret_parser(k8s_secrets_and_configmaps):
    k8s_configmaps = []
    k8s_secrets = []
    for key, value in k8s_secrets_and_configmaps.items():
        type = value.get("type","")
        obj = copy.deepcopy(k8s_objects.K8S_CONFIGMAP)
        if type is not None and type == "SecureString":
            obj = copy.deepcopy(k8s_objects.K8S_SECRETS)
        obj["metadata"]["name"] = k8s_conform(key.split("secret:")[-1])
        obj["data"]= {k8s_conform(value["name"]) : value["value"]}
        if type is not None and type == "SecureString":
            k8s_secrets.append(obj)
        else:
            k8s_configmaps.append(obj)       
    return({"secrets":k8s_secrets, "configmaps":k8s_configmaps})

def get_service_ports(task_def):
    ports = []
    task_def_containers = task_def.get("containerDefinitions",[])
    for task_container in task_def_containers:
        portMappings = task_container.get("portMappings",[])
        for pm in portMappings:
            ports.append({"port":pm.get("containerPort"),"targetPort":pm.get("containerPort"),"protocol":pm.get("protocol","TCP").upper()})
    return ports 

def namespace_parser(name):
    k8s_namespace = copy.deepcopy(k8s_objects.K8S_NAMESPACE)
    k8s_namespace["metadata"]["name"] = k8s_conform(name.split(".")[0])
    k8s_namespace["metadata"]["labels"] = { "cloudmap_namespace": name }
    return {"namespace": k8s_namespace}

def ecs_parser(svc_def, task_def, k8s_secrets_and_configmaps):
    
    k8s_dep = copy.deepcopy(k8s_objects.K8S_DEPLOYMENT)
    k8s_svc = copy.deepcopy(k8s_objects.K8S_SERVICE)
    k8s_svc_account = copy.deepcopy(k8s_objects.K8S_SERVICE_ACCOUNT)
    k8s_sgp = copy.deepcopy(k8s_objects.K8S_POD_SECURITY_GROUP)

    svc_name = k8s_conform(svc_def.get("serviceName"))
    k8s_dep["metadata"]["name"] = svc_name
    k8s_svc["metadata"]["name"] = svc_name
    k8s_svc_account["metadata"]["name"] = svc_name
    k8s_sgp["metadata"]["name"] = svc_name

    get_pod_iam(task_def, k8s_svc_account)
    get_pod_sgp(svc_def, k8s_sgp)
    dep_config = svc_def.get("deploymentConfiguration",{})
    if dict_check(dep_config):
        maximumPercent = dep_config.get("maximumPercent",200)
        minimumHealthyPercent = dep_config.get("minimumHealthyPercent",100)
        maxSurge = max(0, maximumPercent - 100)
        maxUnavailable = max(0, 100 - minimumHealthyPercent)
        k8s_dep["spec"]["strategy"]["rollingUpdate"]["maxSurge"]=str(maxSurge)+"%"
        k8s_dep["spec"]["strategy"]["rollingUpdate"]["maxUnavailable"]=str(maxUnavailable)+"%"
    
    k8s_dep["spec"]["replicas"] = svc_def.get("desiredCount",1)
    
    k8s_svc["spec"]["ports"]= get_service_ports(task_def)
    lbs = svc_def.get("loadBalancers",[])
    if len(lbs) > 0:
        k8s_svc["spec"]["type"]="LoadBalancer"
        
    labels = {}
    tags = svc_def.get("tags",[])
    for t in tags:
        labels[k8s_conform(t["key"])]=k8s_conform(t["value"])

    k8s_svc["metadata"]["labels"] = labels
    
    task_def_arn = svc_def.get("taskDefinition")
    td_label = k8s_conform(task_def_arn.split("task-definition/")[1])
    cluster_arn = svc_def.get("clusterArn")
    cluster_label = k8s_conform(cluster_arn.split("cluster/")[1])
    selector_label = {
        "ecs-task-definition":td_label,
        "ecs-cluster":cluster_label
    }

    k8s_dep["spec"]["template"]["metadata"]["labels"] = selector_label
    k8s_sgp["spec"]["podSelector"]["matchLabels"] = selector_label
    k8s_svc["spec"]["selector"] = selector_label
    k8s_dep["spec"]["selector"]["matchLabels"] = selector_label
    k8s_dep["spec"]["template"]["spec"]["containers"] = get_pod_containers(task_def, k8s_secrets_and_configmaps)
    k8s_dep["spec"]["template"]["spec"]["serviceAccount"] = svc_name
    return({ "service" : k8s_svc,
            "deployment" : k8s_dep, 
            "service_account" : k8s_svc_account,
            "security_group_policy" : k8s_sgp })