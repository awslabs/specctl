# // Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# // SPDX-License-Identifier: Apache-2.0
import json
from ..utils import dict_check
import logging

logger = logging.getLogger(__name__)

def aws_alb_annotation_handler(annotations):
    output_dict = {}
    if not dict_check(annotations): return output_dict
    alb_anno_prefix = "alb.ingress.kubernetes.io/"
    alb_anno_and_default = {
        "scheme":"internet-facing",
        "group.name" : "",
        "listen-ports" : '[{"HTTP":80}]',
        "healthcheck-path" : "/",
        "healthcheck-protocol" : "HTTP",
        "healthcheck-interval-seconds": 45,
        "healthcheck-timeout-seconds": 10,
        "healthy-threshold-count":3,
        "unhealthy-threshold-count":3,
        "success-codes":"200-299",
        "certificate-arn":"",
        "ssl-policy": "ELBSecurityPolicy-TLS-1-1-2017-01"
    }
    # listen-ports is of JSON type rest are all string and integers
    for k,v in alb_anno_and_default.items():
        if k == "listen-ports": continue
        output_dict[k]=annotations.get(alb_anno_prefix+k,v)
    if len(output_dict.get("certificate-arn"))>0:
        alb_anno_and_default["listen-ports"] = '[{"HTTPS":443}]'
    output_dict["listen-ports"]=json.loads(annotations.get(alb_anno_prefix+"listen-ports",alb_anno_and_default["listen-ports"]))
    return output_dict

def get_alb_health_check(annotations):
    alb_health_check = {
        "healthy_threshold":3,
        "interval":30,
        "matcher":"200-299",
        "path":"/",
        "protocol": "HTTP",
        "timeout": 30,
        "unhealthy_threshold":3
    }
    if not dict_check(annotations): return alb_health_check
    alb_health_check["healthy_threshold"] = annotations.get("healthy-threshold-count")
    alb_health_check["interval"] = annotations.get("healthcheck-interval-seconds")
    alb_health_check["matcher"] = annotations.get("success-codes")
    alb_health_check["path"] = annotations.get("healthcheck-path")
    alb_health_check["protocol"] = annotations.get("healthcheck-protocol")
    alb_health_check["timeout"] = annotations.get("healthcheck-timeout-seconds")
    alb_health_check["unhealthy_threshold"] = annotations.get("unhealthy-threshold-count")
    return alb_health_check

def k8s_ingress_rules_handler(rules, listener_name, listener_protocol):
    output_dict = {}
    rule_count = 0 
    for r in rules:
        host_header = r.get("host","")
        http = r.get("http",{})
        paths = http.get("paths",[])
        if len(http)<=0 and len(paths)<=0:
            continue
        for p in paths:
            path_type = p.get("pathType")
            
            if path_type is None:
                logger.error("%s listener ignoring rule with no path type"%(listener_name))
                continue
            if path_type == "ImplementationSpecific":
                logger.warning("%s listener ignoring rule with path type = ImplementationSpecific"%(listener_name))
                continue
            path = p.get("path","/")
            path_pattern = ""
            if path_type == "Prefix":
                if path == "/":
                    path_pattern = "/*"
                else:
                    path_pattern = path+"/*"
            if path_pattern == "Exact":
                path_pattern = path
            
            target_group = p.get("backend")
            listener_rule_name = listener_name+"-rule-"+str(rule_count)
            output_dict[listener_rule_name] = {
                "listener_name": listener_name,
                "path_pattern": path_pattern,
                "host_header": host_header,
                "target_group" : target_group,
                "protocol": listener_protocol
            }
            rule_count+=1
    return output_dict


def k8s_ingress_handler(ingress_obj):
    output_dict = {} 
    if not dict_check(ingress_obj): return output_dict
    metadata = ingress_obj.get("metadata")
    spec = ingress_obj.get("spec")
    rules = spec.get("rules",[])
    if not dict_check(metadata) or not dict_check(spec): return output_dict
    output_dict["ingress_name"] = metadata.get("name")
    output_dict["ingress_namespace"] = metadata.get("namespace","")
    annotations = metadata.get("annotations",{})
    anno_dict = aws_alb_annotation_handler(annotations)
    output_dict["health_check"]=get_alb_health_check(anno_dict)
    shared_alb_name = output_dict["ingress_name"]+"-"+output_dict["ingress_namespace"]
    group_name = anno_dict.get("group.name")
    if len(group_name)>0: shared_alb_name = group_name
    listener_protocol_and_ports = anno_dict.get("listen-ports")
    listeners = {}
    listener_rules = {}
    listener_ports = []
    for lpp in listener_protocol_and_ports:
        for protocol,port in lpp.items():
            listener_name = shared_alb_name+"-"+protocol+"-"+str(port)
            listeners[listener_name]= {
                "alb_name":shared_alb_name, 
                "port":port, 
                "protocol":protocol 
            }
            if protocol == "HTTPS":
                listeners[listener_name]["certificate_arn"] = anno_dict.get("certificate-arn")
                listeners[listener_name]["ssl_policy"] = anno_dict.get("ssl-policy")

            listener_ports.append(port)
            listener_rules.update(k8s_ingress_rules_handler(rules, listener_name, protocol))

    output_dict["ingress_alb"]= { 
        shared_alb_name: {"listener_ports":listener_ports}
    }
    output_dict["listeners"]=listeners
    output_dict["listener_rules"]=listener_rules
    return output_dict


def merge_ingress_listeners(listeners_dict1, listeners_dict2):
    for listener_name, details in listeners_dict2.items():
        if listener_name not in listeners_dict1:
            listeners_dict1[listener_name]=details
    return listeners_dict1

def merge_ingress_albs(alb1, alb2):
    for name2,details2 in alb2.items():
        if name2 in alb1:
            details1 = alb1[name2]
            listener_ports1 = details1.get("listener_ports",[])
            listener_ports2 = details2.get("listener_ports",[])
            alb1[name2]["listener_ports"]=[*set(listener_ports1+listener_ports2)]
        else:
            alb1[name2]=details2
    return alb1

def merge_ingress_rules(rules1, rules2):
    listener_dict = {}
    for rule_name, rule in rules1.items():
        listener_name = rule.get("listener_name")
        if listener_name is None: continue
        if listener_name not in listener_dict:
            listener_dict[listener_name]=[]
        listener_dict[listener_name].append(rule)
    for rule_name, rule in rules2.items():
        listener_name = rule.get("listener_name")
        if listener_name is None: continue
        if listener_name not in listener_dict:
            listener_dict[listener_name]=[]
        listener_dict[listener_name].append(rule)
    
    return_rules_dict = {}
    for listener_name, rules in listener_dict.items():
        rule_count = 0
        for r in rules:
            rule_name = listener_name+"-"+"rule"+"-"+str(rule_count)
            return_rules_dict[rule_name]=r
            rule_count += 1
    return return_rules_dict

def merge_ingress_target_groups(tg1, tg2):
    for tg_name, tg_details in tg2.items():
        if tg_name in tg1:
            continue
        tg1[tg_name]=tg_details
    return tg1

def merge_ingress(ingress_list):
    ingress_albs = {}
    ingress_listeners = {}
    ingress_listener_rules = {}
    ingress_target_groups = {}

    for ingress in ingress_list:
        alb = ingress.get("ingress_alb")
        ingress_albs = merge_ingress_albs(ingress_albs, alb)
        listeners = ingress.get("listeners",{})
        ingress_listeners = merge_ingress_listeners(ingress_listeners, listeners)
        listener_rules = ingress.get("listener_rules",{})
        ingress_listener_rules = merge_ingress_rules(ingress_listener_rules, listener_rules)
        target_groups = ingress.get("target_groups",{})
        ingress_target_groups = merge_ingress_target_groups(ingress_target_groups, target_groups)

    return {"ingress_albs":ingress_albs,
            "ingress_listeners":ingress_listeners,
            "ingress_listener_rules":ingress_listener_rules,
            "ingress_target_groups":ingress_target_groups}

 
def create_ingress_target_groups(ingress_list, svc_list):
    for ingress in ingress_list:
        ingress["target_groups"]={}
        ingress_namespace = ingress.get("ingress_namespace")
        ingress_name = ingress.get("ingress_name")
        if ingress_namespace is None or ingress_name is None:
            logger.error("Found ingress without name or namespace") 
            continue
        ingress_alb = ingress.get("ingress_alb")
        if not dict_check(ingress_alb): continue
        ingress_alb_name = list(ingress_alb.keys())[0]
        listener_rules = ingress.get("listener_rules",{})
        if not dict_check(listener_rules): continue
        for listener_rule_name, listener_rule in listener_rules.items():
            target_group = listener_rule.get("target_group")
            if not dict_check(target_group): continue
            backend_service = target_group.get("service")
            if not dict_check(backend_service): continue
            backend_service_name = backend_service.get("name")
            if backend_service_name is None: continue
            backend_service_port = backend_service.get("port")
            if not dict_check(backend_service_port): continue
            backend_service_port_number = backend_service_port.get("number")
            backend_service_port_name = backend_service_port.get("name")
            if backend_service_port_name is None and backend_service_port_number is None: continue

            for svc in svc_list:
                svc_namespace = svc.get("service_namespace")
                svc_name = svc.get("service_name")
                if svc_namespace is None or svc_name is None:
                    logger.error("Found service without name or namespace, skipping ingress association")
                    continue
                if svc_namespace != ingress_namespace:
                    continue
                if svc_name != backend_service_name:
                    continue
                svc_lb_ports_list = svc.get("lb_ports",{})
                for svc_lb_ports in svc_lb_ports_list:
                    if dict_check(svc_lb_ports) is None: continue
                    svc_port_number = svc_lb_ports.get("service_port")
                    svc_port_name = svc_lb_ports.get("service_port_name")
                    if svc_port_number is None: continue
                    if (backend_service_port_number is not None \
                        and svc_port_number == backend_service_port_number) or \
                        (backend_service_port_name is not None and svc_port_name is not None\
                        and backend_service_port_name == svc_port_name):
                        target_port = svc_lb_ports.get("listener_port")
                        target_group_key = ingress_alb_name+"-"+svc_name+"-"+svc_namespace+"-"+str(target_port)
                        target_group_name = svc_name+"-"+svc_namespace+"-"+str(target_port)
                        svc_lb_health_check = svc.get("lb_health_check_path")
                        if svc_lb_health_check is not None: ingress["health_check"]["path"]=svc_lb_health_check 
                        ingress["target_groups"][target_group_key] = {
                            "name": target_group_name,
                            "port": target_port,
                            "protocol": listener_rule.get("protocol","HTTP"),
                            "tags":{"key":target_group_key},
                            "health_check":ingress.get("health_check",{})
                        }
                        listener_rule["target_group_key"]=target_group_key
                        svc_target_groups = svc.get("ingress_target_groups")
                        if svc_target_groups is None:
                            svc["ingress_target_groups"] = []
                        svc["ingress_target_groups"].append(target_group_name)
    return
