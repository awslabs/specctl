# // Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# // SPDX-License-Identifier: Apache-2.0
from .quantity import parse_quantity
import math

FARGATE_AVAILABLE_SKUS = {
    256   : {"min":1024, "max":2048,    "incr":1024},
    512   : {"min":1024, "max":4096,    "incr":1024},
    1024  : {"min":2048, "max":8192,    "incr":1024},
    2048  : {"min":4096, "max":16384,   "incr":1024},
    4096  : {"min":8192, "max":30720,   "incr":1024},
    8192  : {"min":16384, "max":61440,  "incr":4096},
    16384 : {"min":32768, "max":122880, "incr":8192}
}

# In Kubernetes, 
# 1 CPU unit is equivalent to 1 physical CPU core, 
# or 1 virtual core
# ECS 1024 units = 1 vcpu
def vcpu_k8s_to_ecs(vcpu):
    return int(parse_quantity(vcpu)*1024)

# ECS mem numerical input is in MiB
def mem_k8s_to_ecs(mem):
    return int(parse_quantity(mem)/(1024*1024))

# pass the cpu and mem in ECS units
def get_fargate_sku(cpu, mem):
    if cpu <=256 and mem <=512:
        return {"cpu":256, "memory":512}
    fg_sku = {}
    fg_cpus = list(FARGATE_AVAILABLE_SKUS.keys())
    fg_cpus.sort()
    for c in fg_cpus:
        if c >= cpu:
            fg_mem = FARGATE_AVAILABLE_SKUS.get(c)
            fg_mem_min = fg_mem.get("min")
            fg_mem_max = fg_mem.get("max")
            fg_mem_incr = fg_mem.get("incr")
            diff = mem - fg_mem_min
            if diff <= 0: 
                diff = 0
            diff = math.ceil(diff/fg_mem_incr)
            m = fg_mem_min+diff*fg_mem_incr 
            if m <= fg_mem_max:
                fg_sku = {"cpu":c, "memory":m}
                break
    return(fg_sku)

# simple util functions
def dict_check(dict):
    if dict is None or len(dict)==0: return False
    return True



            


    

    