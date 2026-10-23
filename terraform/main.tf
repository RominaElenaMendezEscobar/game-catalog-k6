terraform {
  required_version = ">= 1.6"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.70"
    }
  }

  # Local state by default. To share it, use an S3 backend, for example:
  # backend "s3" {
  #   bucket = "<your-terraform-state-bucket>"
  #   key    = "game-catalog-k6/terraform.tfstate"
  #   region = "us-east-1"
  # }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project   = "game-catalog-k6"
      ManagedBy = "terraform"
    }
  }
}

data "aws_caller_identity" "current" {}

locals {
  account_id = data.aws_caller_identity.current.account_id
  api_url    = "https://${var.api_id}.execute-api.${var.aws_region}.amazonaws.com"

  # files from the repository root that k6 downloads from s3://<bucket>/scripts/
  repo_root = "${path.module}/.."
  script_files = setunion(
    fileset(local.repo_root, "search.js"),
    fileset(local.repo_root, "sigv4.js"),
    fileset(local.repo_root, "queries.json"),
    fileset(local.repo_root, "scenarios/*.json"),
  )
}
