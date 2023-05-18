# // Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# // SPDX-License-Identifier: Apache-2.0
import json
from . import ecs_objects
import os
import copy
import logging

logger = logging.getLogger(__name__)

# print the task definition and service definition
# json that can be used in create commands

# the parser already merges service and deployment objects appropriately
# just need to create ECS service definition and populate it
def get_svc_def(svc, additional_input):
    svc_def = copy.deepcopy(ecs_objects.SERVICE_DEF)
    dep = svc.get("deployment",{})
    dep_name = dep.get("deployment_name","")
    svc_def["desiredCount"] = dep.get("desired_count",1)
    svc_def["deploymentConfiguration"]["maximumPercent"]=dep.get("deployment_maximum_percent",200)
    svc_def["deploymentConfiguration"]["minimumHealthyPercent"]=dep.get("deployment_minimum_healthy_percent",100)
    dep_tags = dep.get("deployment_tags",{})
    seen = set()
    for k,v in dep_tags.items():
        if k in seen:
            continue
        seen.add(k)
        tag = {"key":k,"value":str(v)}
        svc_def["tags"].append(tag)

    svc_name = svc.get("service_name","")
    svc_tags = svc.get("label_selector",{})
    for k,v in svc_tags.items():
        if k in seen:
            continue
        seen.add(k)
        tag = {"key":k,"value":str(v)}
        svc_def["tags"].append(tag)

    if len(svc_name) > 0:
        svc_def["serviceName"] = svc_name
    else:
        if len(dep_name) > 0:
            svc_def["serviceName"] = dep_name

    for item in additional_input:
        service_def_input = item.get("service_def_input", None)
        if service_def_input is not None:
            if service_def_input["serviceName"]==svc_def["serviceName"]:
                svc_def.update(service_def_input)
                break

    return svc_def


def get_task_def(svc, additional_input):
    dep = svc.get("deployment",{})
    task_def = copy.deepcopy(ecs_objects.TASK_DEF)
    task_def["family"] = dep.get("deployment_name","")
    task_tags = dep.get("task_tags",{})
    for k,v in task_tags.items():
        tag = {"key":k,"value":str(v)}
        task_def["tags"].append(tag)
    containers = dep.get("containers","")
    for c in containers:
        task_container = copy.deepcopy(ecs_objects.CONTAINER_DEF)
        task_container["name"]=c.get("name","")
        task_container["image"]=c.get("image","")
        task_container["portMappings"]=c.get("port_mappings")
        task_def["containerDefinitions"].append(task_container)

    for item in additional_input:
        task_def_input = item.get("task_def_input", None)
        container_def_input = item.get("container_def_input", None)
        if task_def_input is not None:
            if task_def_input["family"]==task_def["family"]:
                task_def.update(task_def_input)
        if container_def_input is not None:
            for c in task_def["containerDefinitions"]:
                for c_input in container_def_input:
                    if c["name"] == c_input["name"]:
                        c.update(c_input)
                        break
    return task_def




# options needs task definition file td_file ;
# service definition file sd_file ;
# additiona input file input_file
# The first two are to write the json output
# The last input_file is to read additional json parameters for task/container/service
def ecs_print(output_dict, options):
    input_file = options.get("input_file")
    additional_input = []
    if len(input_file) > 0:
        with open(input_file,'r') as ipf:
            additional_input = json.loads(ipf.read())
    for key, obj_list in output_dict.items():
        if key == "services":
            for svc in obj_list:
                task_def = get_task_def(svc, additional_input)
                svc_def = get_svc_def(svc, additional_input)
                svc_namespace = svc.get("service_namespace")
                svc_name = svc_def.get("serviceName","")
                if svc_namespace is None or len(svc_namespace)<=0:
                    svc_namespace = "default"

                output_dir = os.path.join(options.get("output_directory"),svc_namespace, svc_name)

                try:
                    os.makedirs(output_dir)
                except FileExistsError:
                    pass

                file_name = options.get("td_file")
                td_file = os.path.join(output_dir, file_name)
                logger.info("Writing task definition in %s"%(td_file))
                with open(td_file,'w') as tdf:
                    tdf.write(json.dumps(task_def,sort_keys=True, indent=2, separators=(',', ': ')))
                    tdf.write("\n")
                file_name = options.get("sd_file")
                sd_file = os.path.join(output_dir, file_name)
                logger.info("Writing service definition in %s"%(sd_file))
                with open(sd_file,'w') as sdf:
                    sdf.write(json.dumps(svc_def,sort_keys=True, indent=2, separators=(',', ': ')))
                    sdf.write("\n")

    logger.info("Please see %s directory for service and task definitions"%(options.get("output_directory")))
