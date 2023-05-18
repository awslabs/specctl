provider "aws" {
  region = var.region
}

################################################################################
# SSM Parameters
################################################################################

resource "aws_ssm_parameter" "task_container_env_parameters" {
  for_each = { for idx, parameter in var.ssm_parameters: idx => parameter }
  name  = each.value.name
  type  = "String"
  value = each.value.value
}

resource "aws_ssm_parameter" "task_container_env_secrets" {
  for_each = { for idx, secret in var.ssm_secrets: idx => secret }
  name  = each.value.name
  type  = "SecureString"
  value = base64decode(each.value.value)
}

resource "aws_service_discovery_private_dns_namespace" "this" {
  for_each    = toset(var.namespaces)
  name        = "${each.key}.svc.cluster.local"
  description = "Service discovery namespace.svc.cluster.local"
  vpc         = data.aws_vpc.vpc.id
}


################################################################################
# Shared Load Balancers 
################################################################################

resource "aws_lb_listener_rule" "all_listener_rules" {
  for_each = var.ingress_listener_rules
  listener_arn = aws_lb_listener.all_listeners[each.value.listener_name].arn

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.all_target_groups[each.value.target_group_key].arn
  }

  dynamic "condition" {
    for_each = each.value.path_pattern != "" ? [each.value.path_pattern] : []
    content {
      path_pattern {
        values = [condition.value]
      }
    }
  }
  dynamic "condition" {
    for_each = each.value.host_header != "" ? [each.value.host_header] : []
    content {
      host_header {
        values = [condition.value]
      }
    }
  }
}

resource "aws_lb_target_group" "all_target_groups" {
  for_each = var.ingress_target_groups
  name        = each.value.name
  port        = each.value.port
  protocol    = each.value.protocol
  target_type = "ip"
  vpc_id      = data.aws_vpc.vpc.id
  tags        = try(each.value.tags,{})
  dynamic "health_check" {
    for_each = try(each.value.health_check,{})!= {} ? [each.value.health_check] : []
    content {
      healthy_threshold = try(health_check.value.healthy_threshold, 3)
      interval = try(health_check.value.interval, 30)
      matcher = try(health_check.value.matcher, "200-299")
      path = try(health_check.value.path,"/")
      protocol = try(health_check.value.protocol,"HTTP")
      timeout = try(health_check.value.timeout, 30)
      unhealthy_threshold = try(health_check.value.unhealthy_threshold, 3)
    }
  }  
}

resource "aws_lb_listener" "all_listeners" {
  for_each = var.ingress_listeners 
  load_balancer_arn = module.service_alb[each.value.alb_name].lb_arn
  port = each.value.port
  protocol = each.value.protocol
  certificate_arn = each.value.protocol == "HTTPS" ? each.value.certificate_arn : null
  ssl_policy = each.value.protocol == "HTTPS" ? each.value.ssl_policy : null 
  default_action {
    type = "fixed-response"
    fixed_response {
      content_type = "text/plain"
      status_code = 404
    }
  }
}

module "service_alb" {
  source  = "terraform-aws-modules/alb/aws"
  version = "~> 8.3"

  for_each = var.ingress_albs

  name = each.key
  load_balancer_type = "application"

  vpc_id  = data.aws_vpc.vpc.id
  subnets = data.aws_subnets.public.ids
  security_group_rules = merge(
      {
        for k, v in toset(try(each.value.listener_ports,[])):
        "ingress_${k}" => {
          type        = "ingress"
          from_port   = v
          to_port     = v
          protocol    = "tcp"
          cidr_blocks = ["0.0.0.0/0"]
          }
      }, 
      {
        egress_all = {
        type        = "egress"
        from_port   = 0
        to_port     = 0
        protocol    = "-1"
        cidr_blocks = [for s in data.aws_subnet.private_cidr : s.cidr_block]
        }
      }
  )
}


################################################################################
# Supporting Resources
################################################################################

data "aws_vpc" "vpc" {
  filter {
    name   = "tag:Name"
    values = [var.ecs_cluster_name]
  }
}

data "aws_subnets" "public" {
  filter {
    name   = "tag:Name"
    values = ["${var.ecs_cluster_name}-public-*"]
  }
}

data "aws_subnets" "private" {
  filter {
    name   = "tag:Name"
    values = ["${var.ecs_cluster_name}-private-*"]
  }
} 

data "aws_subnet" "private_cidr" {
  for_each = toset(data.aws_subnets.private.ids)
  id       = each.value
}
