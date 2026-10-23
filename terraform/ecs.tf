resource "aws_ecs_cluster" "loadtest" {
  name = "${var.name_prefix}-loadtest-cluster"
}

# Created by Terraform so the execution role does not need logs:CreateLogGroup
resource "aws_cloudwatch_log_group" "k6" {
  name              = "/ecs/${var.name_prefix}-k6-task"
  retention_in_days = var.log_retention_days
}

resource "aws_ecs_task_definition" "k6" {
  family                   = "${var.name_prefix}-k6-task"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.k6_cpu
  memory                   = var.k6_memory
  execution_role_arn       = aws_iam_role.k6_execution.arn
  task_role_arn            = aws_iam_role.k6_task.arn

  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = "X86_64"
  }

  container_definitions = jsonencode([{
    name = "k6"
    # referenced by tag (not digest), so every new push is used by the next run
    image     = "${aws_ecr_repository.k6.repository_url}:${var.image_tag}"
    essential = true
    # default values; the Step Function overrides SCENARIO, RUN_ID and RUN_LABEL on each run
    environment = [
      { name = "BUCKET", value = aws_s3_bucket.loadtest.id },
      { name = "API_URL", value = local.api_url },
      { name = "SCENARIO", value = "smoke" }
    ]
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        awslogs-group         = aws_cloudwatch_log_group.k6.name
        awslogs-region        = var.aws_region
        awslogs-stream-prefix = "ecs"
      }
    }
  }])
}
