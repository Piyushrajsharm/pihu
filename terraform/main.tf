terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

variable "aws_region" {
  default = "us-east-1"
}

variable "project_name" {
  default = "pihu-saas"
}

variable "db_username" {
  default = "pihu_admin"
}

variable "db_password" {
  type      = string
  sensitive = true
}

variable "container_image" {
  type        = string
  description = "ECR image URI for the Pihu backend container"
}
