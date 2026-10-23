# The k6 task runs in the default VPC, in public subnets with a public IP, so it can reach
# ECR, S3, CloudWatch Logs and the API without a NAT Gateway.
data "aws_vpc" "default" {
  default = true
}

data "aws_subnets" "default" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }
  filter {
    name   = "default-for-az"
    values = ["true"]
  }
}

# No inbound rules: nobody can open a connection to the task.
# Outbound only over HTTPS: everything the task needs (ECR, S3, logs, API) uses port 443.
resource "aws_security_group" "k6" {
  name        = "${var.name_prefix}-k6-sg"
  description = "k6 load test task: no inbound, HTTPS outbound only"
  vpc_id      = data.aws_vpc.default.id

  egress {
    description = "ECR, S3, CloudWatch Logs and API Gateway"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
}
