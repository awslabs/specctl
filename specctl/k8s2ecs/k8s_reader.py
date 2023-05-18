# // Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# // SPDX-License-Identifier: Apache-2.0
from kubernetes import client, config
from pprint import pprint
import json
import yaml
from pick import pick
import logging

logger = logging.getLogger(__name__)

def empty_sa_object():
    return ({
        "apiVersion" : "v1",
        "kind":"ServiceAccount",
        "metadata":{"annotations":{}, "name":"", "labels":{}}})

def pick_k8s_context():
    contexts, active_context = config.list_kube_config_contexts()
    if not contexts:
        logger.critical("Cannot find any context in kube-config file.")
        exit()
    contexts = [context['name'] for context in contexts]
    active_index = contexts.index(active_context['name'])
    option, _ = pick(contexts, title="Pick the context to load",
                     default_index=active_index)
    logger.info("Selected kubeconfig context is %s"%(option))
    return(option)

def k8s_cluster_extract(namespace_list, contextname=""):
    if len(contextname)<=0:
        contextname = pick_k8s_context()

    config.load_kube_config(context=contextname)

    #config.load_kube_config()
    coreApiV1 = client.CoreV1Api()
    appsApiV1 = client.AppsV1Api()
    netApiV1  = client.NetworkingV1Api()
    coApiV1   = client.CustomObjectsApi()
    ns_objs = coreApiV1.list_namespace()
    namespaces = []
    all_namespaces = []
    for ns in ns_objs.items:
        all_namespaces.append(ns.metadata.name)

    if len(namespace_list) > 0:
        for n1 in namespace_list:
            if n1 in all_namespaces:
                namespaces.append(n1)
            else:
                logger.warning("%s namespace not found in %s cluster context"%(n1, contextname))
    else:
        namespaces = all_namespaces
    services = []
    deployments = []
    configmaps = []
    secrets = []
    ingress = []
    service_accounts = []
    security_groups = []
    for ns in namespaces:
        if ns.startswith("kube-"):
            continue
        svc_objs = coreApiV1.list_namespaced_service(ns)
        logger.info("%s namespace has %d services"%(ns,len(svc_objs.items)))
        for svc in svc_objs.items:
            annt = svc.metadata.annotations
            if annt is not None:
                last_cfg = annt.get("kubectl.kubernetes.io/last-applied-configuration")
                if last_cfg is not None:
                    services.append(json.loads(last_cfg))
        dep_objs = appsApiV1.list_namespaced_deployment(ns)
        logger.info("%s namespace has %d deployments"%(ns,len(dep_objs.items)))
        for dep in dep_objs.items:
            annt = dep.metadata.annotations
            if annt is not None:
                last_cfg = annt.get("kubectl.kubernetes.io/last-applied-configuration")
                if last_cfg is not None:
                    deployments.append(json.loads(last_cfg))
        cfgmap_objs = coreApiV1.list_namespaced_config_map(ns)
        logger.info("%s namespace has %d configmaps"%(ns,len(cfgmap_objs.items)))
        for cfgmap in cfgmap_objs.items:
            annt = cfgmap.metadata.annotations
            if annt is not None:
                last_cfg = annt.get("kubectl.kubernetes.io/last-applied-configuration")
                if last_cfg is not None:
                    configmaps.append(json.loads(last_cfg))

        secret_objs = coreApiV1.list_namespaced_secret(ns)
        logger.info("%s namespace has %d secrets"%(ns,len(secret_objs.items)))
        for secret in secret_objs.items:
            annt = secret.metadata.annotations
            if annt is not None:
                last_cfg = annt.get("kubectl.kubernetes.io/last-applied-configuration")
                if last_cfg is not None:
                    secrets.append(json.loads(last_cfg))
        
        ingress_objs = netApiV1.list_namespaced_ingress(ns)
        logger.info("%s namespace has %d ingress objects"%(ns,len(ingress_objs.items)))
        for ig in ingress_objs.items:
            annt = ig.metadata.annotations
            if annt is not None:
                last_cfg = annt.get("kubectl.kubernetes.io/last-applied-configuration")
                if last_cfg is not None:
                    ingress.append(json.loads(last_cfg))
        
        sa_objects = coreApiV1.list_namespaced_service_account(ns)
        logger.info("%s namespace has %d service_account objects"%(ns,len(sa_objects.items)))
        for sa in sa_objects.items:
            annt = sa.metadata.annotations
            if annt is not None:
                last_cfg = annt.get("kubectl.kubernetes.io/last-applied-configuration")
                if last_cfg is not None:
                    service_accounts.append(json.loads(last_cfg))
                else:
                    sa_obj = empty_sa_object()
                    sa_obj["metadata"]["name"] = sa.metadata.name
                    sa_obj["metadata"]["namespace"] = sa.metadata.namespace
                    sa_obj["metadata"]["annotations"] = sa.metadata.annotations
                    sa_obj["metadata"]["labels"] = sa.metadata.labels
                    service_accounts.append(sa_obj)
        sgp_objects = coApiV1.list_namespaced_custom_object("vpcresources.k8s.aws", "v1beta1", ns, "securitygrouppolicies")
        logger.info("%s namespace has %d pod security group objects"%(ns,len(sgp_objects["items"])))
        for sgp in sgp_objects["items"]:
            annt = sgp["metadata"]["annotations"]
            if annt is not None:
                last_cfg = annt.get("kubectl.kubernetes.io/last-applied-configuration")
                if last_cfg is not None:
                    security_groups.append(json.loads(last_cfg))
    return(services+deployments+secrets+configmaps+ingress+service_accounts+security_groups)


# This function will parse the K8s yaml files. It will convert the YAML to dictionary objects
def k8s_yaml_to_dict(yaml_files):
    dict_list = []
    # read all the K8s spec YAML files as dictionaries
    for yf in yaml_files:
        logger.info("Reading YAML from %s file"%(yf))
        with open(yf, 'r') as input_stream:
            try:
                for schema in yaml.safe_load_all(input_stream):
                    dict_list.append(schema)
            except:
                logger.error("Error reading %s YAML file %s"%(yf, yaml.YAMLError))
    # this will be the output dictionary which will have
    # list of deployments, services, pods, secrets, and configmaps
    return (dict_list)
