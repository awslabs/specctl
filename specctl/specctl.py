# // Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# // SPDX-License-Identifier: Apache-2.0
import click
import json
import yaml 
from os import listdir, makedirs
from os.path import isdir, isfile, join

# ecs to k8s 
from .ecs2k8s.ecs_reader_writer import ecs_reader_writer

# k8s to ecs
from .k8s2ecs.k8s_reader import k8s_cluster_extract
from .k8s2ecs.k8s_parser import k8s_parser
from .k8s2ecs.ecs_output import ecs_print
from .k8s2ecs.tf_output import terraform_print

# docker compose to k8s
from .dc2k8s.dc_reader_writer import dc_reader_writer

import logging
import logging.config
LOGGING_CONFIG = { 
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': { 
        'standard': { 
            'format': '%(asctime)s [%(levelname)s] %(name)s: %(message)s'
        },
    },
    'handlers': { 
        'default': { 
            'level': 'INFO',
            'formatter': 'standard',
            'class': 'logging.StreamHandler',
            'stream': 'ext://sys.stdout',  # Default is stderr
        },
    },
    'loggers': { 
        '': {  # root logger
            'handlers': ['default'],
            'level': 'WARNING',
            'propagate': False
        }
    } 
}
logging.config.dictConfig(LOGGING_CONFIG)
logger = logging.getLogger()

# reads yaml file(s) from source and returns dictionary list
def yaml_reader(source):
    yaml_files = []
    dict_list = []
    if isfile(source) and source.lower().endswith(('.yaml','yml')): yaml_files.append(source)
    if isdir(source):
        yaml_files = [join(source,f) for f in listdir(source) if isfile(join(source, f)) and f.lower().endswith(('.yaml','yml'))]   
   
    for yf in yaml_files:
        logger.info("Reading YAML from %s file"%(yf))
        with open(yf, 'r') as input_stream:
            try:
                for schema in yaml.safe_load_all(input_stream):
                    dict_list.append(schema)
            except:
                logger.error("Error reading %s YAML file %s"%(yf, yaml.YAMLError))
    return (dict_list)

def e2k_cli_handler(options):
    ecs_reader_writer(options)
    return

def k2e_cli_handler(source, context, options):
    spec_list = []
    if len(source)<=0:
        spec_list=k8s_cluster_extract(options.get("namespaces"), context)    
    else:
        spec_list=yaml_reader(source)
    
    if len(spec_list) <= 0:
        logger.warning("Found no K8s specification object")
        return
    output_dict=k8s_parser(spec_list)
    ecs_print(output_dict, options)
    terraform_print(output_dict, options)
    return

def d2k_cli_handler(source, options):
    spec_list=yaml_reader(source)
    if len(spec_list) <= 0:
        logger.warning("Found no docker compose specification object")
        return
    dc_reader_writer(spec_list, options)
    return 


# Click cli entry point function
@click.command()
@click.option("-m","--mode", default="k2e", type=click.Choice(["k2e","e2k","d2k"], case_sensitive=False), help="Transform mode - k2e K8s-to-ECS, e2k ECS-to-K8s, d2k Docker Compose-to-K8s")
@click.option("-s", "--source", default="", type=str, help="Path to YAML specification file or directory")
@click.option("-c", "--context", default="", type=str, help="Kubeconfig context name to load")
@click.option("-l", "--log_level", default="WARNING", type=click.Choice(["DEBUG","INFO","WARNING","ERROR","CRITICAL"], case_sensitive=False), help="Select log level")
@click.option("-n", "--namespaces", default="", type=str, help="Only fetch namespaces specified here as comma separated string. Applies only when converting from K8s clusters and not from spec files")
@click.option("--td_file",default="taskdefinition.json", help="File to write ECS task definition json")
@click.option("--sd_file",default="servicedefinition.json", help="File to write ECS service definition json")
@click.option("--input_file", default="", help="File with additional input parameters for task, container, and/or services")
@click.option("--tfvars_file", default="terraform.tfvars", help="File to write the Terraform tfvars")
@click.option("-d", "--tf_modules_directory", default="./terraform", help="Path to Terraform modules directory")
@click.option("--tf_modules_name_map", default="namespaces:namespaces,ecs-lb-service:ecs-lb-service,ecs-backend-service:ecs-backend-service", help="Change the value in this map to your terraform modules directory")
@click.option("--tf_files", default="main.tf,versions.tf,variables.tf,outputs.tf", help="List of files to use from Terraform modules")
@click.option("-o", "--output_directory", default="./output", help="Path to output directory")
@click.option("--ecs_cluster_name", default="", type=str, help="ECS cluster to extract services and tasks")
@click.option("--ecs_region_name", default="", type=str, help="Region name for ECS cluster")
@click.option("--sgp", is_flag="True", help="Create EKS Security Group Policy from task security groups")
def transform(mode, source, context, log_level, namespaces, td_file, sd_file, input_file, tfvars_file, tf_modules_directory, tf_modules_name_map, tf_files, output_directory, ecs_cluster_name, ecs_region_name, sgp):
    logger.setLevel(getattr(logging,log_level.upper()))
    for handler in logger.handlers:
        handler.setLevel(getattr(logging,log_level.upper()))
    try:
        makedirs(output_directory)
    except FileExistsError:
        pass
    namespace_list = []
    if len(namespaces)>0:
        namespace_list=namespaces.split(",")
    options = {
        "namespaces":namespace_list,
        "td_file": td_file,
        "sd_file": sd_file,
        "input_file": input_file,
        "tfvars_file": tfvars_file,
        "tf_modules_directory": tf_modules_directory,
        "tf_modules_name_map": tf_modules_name_map,
        "tf_files": tf_files,
        "output_directory" : output_directory,
        "cluster_name" : ecs_cluster_name,
        "region_name" : ecs_region_name,
        "sgp": sgp
        }
    if mode == "k2e":
        k2e_cli_handler(source, context, options)
        return
    if mode == "e2k":
        e2k_cli_handler(options)
        return
    if mode == "d2k":
        d2k_cli_handler(source, options)
        return
    if mode == "e2f":
        logger.info("ECS EC2 to ECS FG is coming soon!")
        return
