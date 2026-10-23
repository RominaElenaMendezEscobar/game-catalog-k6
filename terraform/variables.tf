variable "aws_region" {
  description = "AWS region for all resources"
  type        = string
  default     = "us-east-1"
}

variable "api_id" {
  description = "ID of the existing HTTP API to test (the part before .execute-api in its URL)"
  type        = string
}

variable "api_route" {
  description = "Route the k6 task is allowed to invoke, as METHOD/path"
  type        = string
  default     = "POST/search"
}

variable "bucket_name" {
  description = "Bucket for k6 scripts (scripts/) and results (runs/)"
  type        = string
  default     = "game-catalog-loadtest"
}

variable "name_prefix" {
  description = "Prefix for resource names"
  type        = string
  default     = "game-catalog"
}

variable "image_tag" {
  description = "Tag of the container images in ECR"
  type        = string
  default     = "latest"
}

variable "k6_cpu" {
  description = "Fargate CPU units for the k6 task (1024 = 1 vCPU)"
  type        = number
  default     = 1024
}

variable "k6_memory" {
  description = "Fargate memory (MB) for the k6 task"
  type        = number
  default     = 2048
}

variable "report_memory" {
  description = "Memory (MB) of the report Lambda"
  type        = number
  default     = 1024
}

variable "report_timeout" {
  description = "Timeout (seconds) of the report Lambda"
  type        = number
  default     = 120
}

variable "report_model_id" {
  description = "Bedrock inference profile used by the report Lambda (must match config/report.yaml)"
  type        = string
  default     = "us.amazon.nova-pro-v1:0"
}

variable "log_retention_days" {
  description = "Retention of the CloudWatch log groups"
  type        = number
  default     = 14
}

variable "force_destroy" {
  description = "Allow terraform destroy to delete the bucket and ECR repositories even if they are not empty"
  type        = bool
  default     = false
}
