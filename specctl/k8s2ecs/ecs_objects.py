# // Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# // SPDX-License-Identifier: Apache-2.0
TASK_DEF = {
    "containerDefinitions": [
    ],
    "family": "",
    "networkMode": "awsvpc",
    "requiresCompatibilities": [
        "FARGATE"
    ],
    "tags":[]
}
TASK_DEF_REQUIRED_INPUT = {
    "taskRoleArn": "",
    "executionRoleArn":"",
    "cpu":"",
    "memory":""
}

CONTAINER_DEF = {
    "name": "",
    "image": "",
    "portMappings": [
        {
            "containerPort": "",
            "hostPort": "",
            "protocol": "tcp"
        }
    ]
}

CONTAINER_DEF_REQUIRED_INPUT = {
    "name":"",
    "image":"",
    "logConfiguration": {
        "logDriver": "awslogs",
        "options": {
            "awslogs-group": "",
            "awslogs-region": "",
            "awslogs-stream-prefix": "ecs"
        }
    }
}

SERVICE_DEF = {
    "serviceName": "",
    "desiredCount": 1,
    "tags":[],
    "launchType": "FARGATE",
    "platformVersion": "LATEST",
    "taskDefinition": "",
    "deploymentConfiguration": {
        "maximumPercent": 200,
        "minimumHealthyPercent": 100
    },
    "schedulingStrategy": "REPLICA",
    "enableECSManagedTags": True,
    "propagateTags": "SERVICE",
    "enableExecuteCommand": True
}

SERVICE_DEF_REQUIRED_INPUT = {
    "networkConfiguration": {
        "awsvpcConfiguration": {
            "subnets": [],
            "securityGroups": [],
            "assignPublicIp": ""
        }
    },
    "loadBalancers": [
        {
            "targetGroupArn": "",
            "containerName": "",
            "containerPort": "",
        }
    ]
}
