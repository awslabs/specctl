# // Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# // SPDX-License-Identifier: Apache-2.0
import json
import os
import shutil
import logging

logger = logging.getLogger(__name__)

# This will generate TFvars format output key = value
def hcl_fmt(value):
    if type(value) == int or type(value) == float:
        return str(value)
    return (json.dumps(value, indent=2, separators=[",", " = "]))

def write_hcl(key, value, tf_file):
    with open(tf_file, 'a') as tf:
        tf.write(key.strip()+" = "+hcl_fmt(value)+"\n")

def write_hcl_dict(dict_obj, tf_file, ignore_keys=[]):
    for key, value in dict_obj.items():
        if key in ignore_keys:
            continue
        write_hcl(key, value, tf_file)

def write_hcl_dict_list(dict_list_obj, tf_file, ignore_keys=[]):
    for dict_obj in dict_list_obj:
        write_hcl_dict(dict_obj, tf_file, ignore_keys)

def copy_tf_modules(src_dir, dest_dir, tf_files):
    for fn in tf_files:
        src_file = os.path.join(src_dir, fn)
        if not os.path.isfile(src_file): continue
        logger.info("Copying TF modules %s to %s"%(src_file, dest_dir))
        shutil.copy(src_file, dest_dir)
    return
def get_tf_modules_directory_map(tf_modules_directory, tf_modules_name_map):
    tf_modules_list = tf_modules_name_map.split(",")
    tf_modules_directory_map = {}
    for tf_module in tf_modules_list:
        key = tf_module.split(":")[0].strip()
        value = tf_module.split(":")[1].strip()
        value_with_path =os.path.join(tf_modules_directory,value)
        tf_modules_directory_map[key]=value_with_path
        if not os.path.exists(value_with_path):
            logger.error("Terraform module path %s for key %s doesn't exist"%(value_with_path,key))
    return tf_modules_directory_map

def terraform_print(output_dict, options):
    # where are the terraform modules
    tf_modules_directory = options.get("tf_modules_directory")
    tf_modules_name_map = options.get("tf_modules_name_map")
    tf_files = [f.strip() for f in options.get("tf_files").split(",")]
    tf_modules_directory_map = get_tf_modules_directory_map(tf_modules_directory, tf_modules_name_map)

    # ssm secrets, parameters, and namespaces are written in output/namespaces/terraform.tfvars
    output_dir = os.path.join(options.get("output_directory"),"namespaces")
    try:
        os.makedirs(output_dir)
    except FileExistsError:
        pass
    tfvars_file = os.path.join(output_dir, options.get("tfvars_file"))
    with open(tfvars_file, 'w') as tf:
        tf.write("# TFvars generated by parsing K8s ConfigMaps, Secrets, and Namespaces \n")
    ingress = output_dict.get("ingress",{})
    configmaps = output_dict.get("configmaps",[])
    secrets = output_dict.get("secrets",[])
    namespaces = output_dict.get("namespaces",[])
    namespaces.append("default")
    namespaces = [*set(namespaces)]
    total_params = configmaps+secrets
    logger.info("Writing %d configmaps %d secrets and %d namespaces in %s"%(len(configmaps), len(secrets), len(namespaces), tfvars_file))
    write_hcl_dict_list(total_params, tfvars_file, [])
    write_hcl("namespaces", namespaces, tfvars_file)
    write_hcl_dict(ingress, tfvars_file)
    copy_tf_modules(tf_modules_directory_map.get("namespaces"), output_dir, tf_files)
    # rest are written in output/namespace/service/terraform.tfvars
    services = output_dict.get("services",[])
    for svc in services:
        svc_namespace = svc.get("service_namespace")
        svc_name = svc.get("service_name","")
        if svc_namespace is None or len(svc_namespace)<=0:
            svc_namespace = "default"
            svc["service_namespace"]="default"
        output_dir = os.path.join(options.get("output_directory"),svc_namespace, svc_name)
        try:
            os.makedirs(output_dir)
        except FileExistsError:
            pass

        file_name = options.get("tfvars_file")
        tfvars_file = os.path.join(output_dir, file_name)
        logger.info("Writing service tfvars to %s"%(tfvars_file))
        with open(tfvars_file, 'w') as tf:
            tf.write("# TFvars generated by parsing K8s Service and Deployment\n")

        lb_ports = svc.get("lb_ports",[])
        lb_container_name = ""
        if len(lb_ports) > 0:
            write_hcl_dict(lb_ports[0], tfvars_file)
            lb_container_name = lb_ports[0].get("lb_container_name","")

        dep = svc.get("deployment", None)
        if dep is not None:
            containers = dep.get("containers",[])
            cont_dict = {}
            for c in containers:
                c_name = c.get("name")
                cont_dict[c_name] = c
            write_hcl_dict({"containers":cont_dict}, tfvars_file)

            if lb_container_name == "" and len(containers) >0:
                lb_container_name = containers[0].get("name")
                write_hcl("lb_container_name", lb_container_name, tfvars_file)

            write_hcl_dict(dep, tfvars_file, ["containers"])

        write_hcl_dict(svc, tfvars_file, ["deployment","lb_ports"])
        svc_type = svc.get("service_type","ClusterIP")
        if svc_type == "LoadBalancer":
            copy_tf_modules(tf_modules_directory_map["ecs-lb-service"], output_dir, tf_files)
        else:
            copy_tf_modules(tf_modules_directory_map["ecs-backend-service"], output_dir, tf_files)

    logger.log(100, "Please see %s directory for terraform tfvars" %(options.get("output_directory")))
