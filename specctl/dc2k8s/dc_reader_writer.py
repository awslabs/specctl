import os
import json
import yaml
from ..utils import dict_check
from .dc_parser import dc_service_parser

import logging

logger = logging.getLogger(__name__)

def write_yaml(filename, spec_list):
    logging.info("Writing K8s spec to %s"%(filename))
    yaml.Dumper.ignore_aliases = lambda self, data: True
    with open(filename, 'w') as kf:
      for spec in spec_list:
          kf.write(yaml.dump(spec, Dumper=yaml.Dumper))
          kf.write("---\n")

def dc_reader_writer(spec_list, options):
    for spec in spec_list:
        services = spec.get("services")
        if not dict_check(services): continue
        for svc_name,dc_svc in services.items():
            dc_svc["service_name"]=svc_name
            k8s_yamls = dc_service_parser(dc_svc)
        
            output_dir = os.path.join(options.get("output_directory"), svc_name)
            try:
                os.makedirs(output_dir)
            except FileExistsError:
                pass
            for k,v in k8s_yamls.items():
                k8s_file = os.path.join(output_dir, svc_name+"_"+k+".yaml")
                write_yaml(k8s_file,[v])
    
    logger.log(100, "Please see %s directory for kubernetes artifacts" %(options.get("output_directory")))
    return