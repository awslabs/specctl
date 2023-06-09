import copy
from .. import k8s_objects
from ..utils import dict_check
import re
import logging

logger = logging.getLogger(__name__)

def k8s_conform(input_string):
    return(re.sub("[^a-zA-Z0-9]+","-", input_string).lower().rstrip("-"))

def get_ext_value(key, ext_values):
    # check if key is of form ${xyz}
    expr = re.compile(r'\$\{[\:a-zA-Z0-9_-]+\}')
    mo = expr.search(str(key))
    value = key
    if mo is None: return value
    # strip the ${} to get the var
    key_var = mo.group()[2:-1]
    # see if default value is there var:-value or var-value
    split1 = key_var.split(":-")
    key_var=split1[0]
    if len(split1)>1: 
        value = split1[1]
    lookup_value = ext_values.get(key_var)

    if lookup_value is None:
        logger.warning("%s key is not found in env file"%(key_var))
        # just replace back to the original key
    else:
        value = lookup_value
    if value.isdigit():
        value = int(value)
    return value

# ports are of the generic form [HOST:]CONTAINER[/PROTOCOL]
# port ranges are not supported though in K8s 
# mapped host port will be assigned to service port
def dc_port_parser(dc_ports, ext_values):
    ports = []
    for p in dc_ports:
        p_split = p.split(":")
        p_container_port_protocol  = p_split[-1]
        port_protocol_list = p_container_port_protocol.split("/")
        p_container_port = port_protocol_list[0]
        if p_container_port.isdigit():
            p_container_port = int(p_container_port)
        else:
            p_container_port = get_ext_value(p_container_port, ext_values)
        service_port = p_container_port
        if len(p_split)>1:
            service_port=p_split[-2]
            if service_port.isdigit():
                service_port = int(service_port)
            else:
                service_port = get_ext_value(service_port, ext_values)
        p_container_protocol = "TCP"
        if len(port_protocol_list)>1:
            p_container_protocol = port_protocol_list[1].upper()
        ports.append({"service_port":service_port, "container_port":p_container_port, "protocol":p_container_protocol})
    return ports

def dc_container_parser(dc_svc, k8s_dep, ext_values):
    dc_svc_name = dc_svc.get("service_name")
    pod_container = copy.deepcopy(k8s_objects.K8S_POD_CONTAINER)
    ports = []
    dc_image = dc_svc.get("image")
    if dc_image is None:
        # Then likely "build" is being used
        img_key="${BUILD_"+dc_svc_name+"}"
        logger.warning("%s service has no container image. looking up %s in env file"%(dc_svc_name, img_key))
        dc_image=get_ext_value(img_key,ext_values)

    pod_container["image"]=dc_image
    pod_container["name"]  = k8s_dep["metadata"]["name"]
    dc_ports_raw = dc_svc.get("ports",[])
    dc_ports = dc_port_parser(dc_ports_raw, ext_values)
    ports = []

    for p in dc_ports:
        ports.append({"containerPort":p["container_port"],"protocol":p["protocol"]})
    
    pod_container["ports"]=ports
    dc_env = dc_svc.get("environment")
    #environment can be a list or map
    if dc_env is not None:
        if isinstance(dc_env, dict):
            for k,v in dc_env.items():
                pod_container["env"].append({"name":k,"value":get_ext_value(v, ext_values)})
        if isinstance(dc_env, list):
            for env_item in dc_env:
                for k,v in env_item.items():
                    pod_container["env"].append({"name":k,"value":get_ext_value(v, ext_values)})
    k8s_dep["spec"]["template"]["spec"]["containers"].append(pod_container)    
    return

def dc_service_parser(dc_svc, ext_values):
    k8s_obj_list = []
    dc_svc_name = dc_svc.get("service_name")
    k8s_dep = copy.deepcopy(k8s_objects.K8S_DEPLOYMENT)
    k8s_svc = copy.deepcopy(k8s_objects.K8S_SERVICE)
    k8s_svc_account = copy.deepcopy(k8s_objects.K8S_SERVICE_ACCOUNT)

    svc_name = k8s_conform(dc_svc_name)
    k8s_dep["metadata"]["name"] = svc_name
    k8s_svc["metadata"]["name"] = svc_name
    k8s_svc_account["metadata"]["name"] = svc_name
    dc_container_parser(dc_svc, k8s_dep, ext_values)

    dc_ports_raw = dc_svc.get("ports",[])
    dc_ports = dc_port_parser(dc_ports_raw, ext_values)
    dc_expose = dc_svc.get("expose",[])
    ports = []
    for p in dc_ports:
        container_port = p["container_port"]
        if len(dc_expose) > 0:
            if str(container_port) in dc_expose:
                ports.append({"port":p["service_port"],"targetPort":container_port, "protocol":p["protocol"]})
        else:
            ports.append({"port":p["service_port"],"targetPort":container_port, "protocol":p["protocol"]})
    k8s_svc["spec"]["ports"] = ports
    # if labels are present we will use these as selector 
    selector_label = {"app":svc_name}
    dc_labels = dc_svc.get("labels")
    if dict_check(dc_labels):
        if isinstance(dc_labels, list):
            for label_item in dc_labels:
                for k,v in label_item:
                    selector_label[k]=v
        if isinstance(dc_labels, dict):
            for k,v in dc_labels.items():
                selector_label[k]=v
    
    k8s_svc["metadata"]["labels"] = selector_label
    k8s_dep["spec"]["template"]["metadata"]["labels"] = selector_label
    k8s_svc["spec"]["selector"] = selector_label
    k8s_dep["spec"]["selector"]["matchLabels"] = selector_label
    k8s_dep["spec"]["template"]["spec"]["serviceAccount"] = svc_name

    return({ "service" : k8s_svc,
            "deployment" : k8s_dep, 
            "service_account" : k8s_svc_account })