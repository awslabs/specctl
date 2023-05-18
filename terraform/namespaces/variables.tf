variable "region" {
  description = "The aws region for the service"
  type        = string
  default     = "us-west-2"
}

variable "ecs_cluster_name" {
  description = "The ECS cluster name in which the resources will be created"
  type        = string
  default     = "core-infra"
}

# Containers can have env variable values derived from SSM Parameter store
# To create and store such values provide a list containing
# {"name"="", value=""}
variable "ssm_parameters" {
  description = "To create SSM String Parameters used in container env variables"
  type        = list(any)
  default     = []
}

# values are expected to be base64encoded
variable "ssm_secrets" {
  description = "To create SSM SecureString Parameters used in container env variables"
  type        = list(any)
  default     = []
}

variable "namespaces" {
  description = "List of namespaces to create"
  type        = list(string)
  default     = ["default"]
}

variable "ingress_albs" {
  description = "List of shared albs"
  default = { 
    "foo-test" = {
      "listener_ports" = [80,8080,443,8443]
    },
    "bar-test" = {
      "listener_ports" = [80]
    }
  }
}

variable "ingress_listeners" {
  description = "List of listeners for all shared albs"
  default = {
    "foo-test-http-80" = {
      "alb_name" = "foo-test"
      "port" = 80
      "protocol" = "HTTP"
    }
  }
}

variable "ingress_target_groups" {
  description = "List of target groups for all shared albs"
  default = {
    "ui-ui-80" = {
      "port" = 80
      "protocol" = "HTTP"
    }
  }
}

variable "ingress_listener_rules" {
  description = "List of listener rules for all listeners"
  default = {
    "rule-0" : {
      "listener_name" = "foo-test-http-80"
      "target_group_name" = "ui-ui-80"
      "path_pattern" = "/"
      "host_header" = ""
    }
  }
}