# // Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# // SPDX-License-Identifier: Apache-2.0
K8S_NAMESPACE = {
    "apiVersion" : "v1",
    "kind" : "Namespace",
    "metadata" : {
        "name" : ""
    }
}

K8S_SERVICE = {
    "apiVersion":"v1",
    "kind":"Service",
    "metadata": {
        "name": "",
        "labels" : {}
    },
    "spec": {
        "selector": {},
        "type":"ClusterIP",
        "ports":[]
    }
}
K8S_DEPLOYMENT = {
    "apiVersion": "apps/v1",
    "kind": "Deployment",
    "metadata": {
        "name": ""
    },
    "spec": {
        "replicas": 1,
        "selector": {
            "matchLabels": {}
        },
        "strategy": {
            "rollingUpdate": {
                "maxSurge": "25%",
                "maxUnavailable": "25%"
            },
            "type": "RollingUpdate"
        },
        "template" : {
            "metadata": {
                "labels":{}
            },
            "spec":{
                "containers":[]
            }
        }
    }
}
K8S_POD_CONTAINER = {
    "image": "",
    "name": "",
    "ports": [],
    "env": []
}

K8S_CONFIGMAP = {
    "apiVersion" : "v1",
    "kind" : "ConfigMap",
    "metadata": {
        "name": ""
    },
    "data" : {}
}

K8S_SECRETS = {
    "apiVersion" : "v1",
    "kind" : "Secret",
    "metadata" : {
        "name" : ""
    },
    "data" : {},
    "type" : "Opaque"
}

K8S_SERVICE_ACCOUNT = {
    "apiVersion" : "v1",
    "kind" : "ServiceAccount",
    "metadata" : {
        "annotations" : {},
        "name" : ""
    }
}

K8S_INGRESS = {
    "apiVersion" : "networking.k8s.io/v1",
    "kind" : "Ingress",
    "metadata" : {
        "name" : "",
    },
    "spec" : {
        "ingressClassName": "alb",
        "rules": [],
    }
}
K8S_INGRESS_RULE = {
    "http" : {
        "paths" : [] 
    }
}

K8S_INGRESS_RULE_PATH = {
  "path" : "",
  "pathType" : "Prefix",
  "backend" : {
    "service" : {
        "name" : "",
        "port" : {
            "number" : ""
        }
    }
  }
}


K8S_POD_SECURITY_GROUP = {
    "apiVersion" : "vpcresources.k8s.aws/v1beta1",
    "kind" : "SecurityGroupPolicy",
    "metadata" : {
        "name" : "",
    },
    "spec" : {
        "podSelector" : {
            "matchLabels" : {},
        },
        "securityGroups" : {
            "groupIds" : [] 
        }
    }
}