provider "aws" {
  region = var.region
}

data "aws_caller_identity" "current" {}

locals {
  name     = var.service_name
  k8s_objs = { "k8s_deployment" : var.deployment_name, "k8s_service_type" : var.service_type, "k8s_deployment_namespace" : var.deployment_namespace }
  tags     = merge(var.service_tags, var.label_selector, var.deployment_tags, var.task_tags, local.k8s_objs)
}

resource "aws_service_discovery_service" "this" {
  name = local.name

  dns_config {
    namespace_id = data.aws_service_discovery_dns_namespace.this.id

    dns_records {
      ttl  = 10
      type = "A"
    }

    routing_policy = "MULTIVALUE"
  }

  health_check_custom_config {
    failure_threshold = 1
  }
}

module "ecs_service_definition" {
  source  = "terraform-aws-modules/ecs/aws//modules/service"
  version = "~> 5.0"
  name               = local.name
  desired_count      = var.desired_count
  cluster_arn        = data.aws_ecs_cluster.core_infra.arn
  enable_autoscaling = false
  task_exec_ssm_param_arns = ["*"]

  subnet_ids = data.aws_subnets.private.ids
  security_group_rules = {
    ingress_all = {
      type        = "ingress"
      from_port   = 0
      to_port     = 0
      protocol    = "-1"
      cidr_blocks = ["0.0.0.0/0"]
    }
    egress_all = {
      type        = "egress"
      from_port   = 0
      to_port     = 0
      protocol    = "-1"
      cidr_blocks = ["0.0.0.0/0"]
    }
  }

  load_balancer =[ 
    for ing_tg in toset(var.ingress_target_groups):
      {
        container_name = var.lb_container_name
        container_port = var.lb_container_port
        target_group_arn = data.aws_lb_target_group.ingress_tg[ing_tg].arn
      }
  ]
  
  service_registries = {
    registry_arn = aws_service_discovery_service.this.arn
  }

  deployment_controller              = "ECS"
  deployment_maximum_percent         = var.deployment_maximum_percent
  deployment_minimum_healthy_percent = var.deployment_minimum_healthy_percent

  # Task Definition
  cpu                    = var.cpu
  memory                 = var.memory
  create_iam_role        = false
  task_exec_iam_role_arn = one(data.aws_iam_roles.ecs_core_infra_exec_role.arns)
  enable_execute_command = true

  container_definitions          = var.containers
  container_definition_defaults  = { "readonly_root_filesystem" : false, "cpu" : null }
  ignore_task_definition_changes = false
  tags                           = local.tags
}

################################################################################
# Supporting Resources
################################################################################

data "aws_subnets" "private" {
  filter {
    name   = "tag:Name"
    values = ["${var.ecs_cluster_name}-private-*"]
  }
}

data "aws_ecs_cluster" "core_infra" {
  cluster_name = var.ecs_cluster_name
}

data "aws_iam_roles" "ecs_core_infra_exec_role" {
  name_regex = "${var.ecs_cluster_name}-*"
}

data "aws_service_discovery_dns_namespace" "this" {
  name = "${var.service_namespace}.svc.cluster.local"
  type = "DNS_PRIVATE"
}

data "aws_lb_target_group" "ingress_tg" {
  for_each = toset(var.ingress_target_groups)
  name = each.key
}

variable "create_tasks_iam_role" {
  description = "Determines whether the ECS tasks IAM role should be created"
  type        = bool
  default     = true
}

variable "tasks_iam_role_arn" {
  description = "Existing IAM role ARN"
  type        = string
  default     = null
}