# ---------- ECS: execution role (pull the image, send logs) ----------

resource "aws_iam_role" "k6_execution" {
  name = "${var.name_prefix}-k6-execution-role"
  assume_role_policy = jsonencode({
    Version   = "2012-10-17"
    Statement = [{ Effect = "Allow", Principal = { Service = "ecs-tasks.amazonaws.com" }, Action = "sts:AssumeRole" }]
  })
}

resource "aws_iam_role_policy_attachment" "k6_execution" {
  role       = aws_iam_role.k6_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

# ---------- ECS: task role (what the k6 container can do) ----------

resource "aws_iam_role" "k6_task" {
  name = "${var.name_prefix}-k6-task-role"
  assume_role_policy = jsonencode({
    Version   = "2012-10-17"
    Statement = [{ Effect = "Allow", Principal = { Service = "ecs-tasks.amazonaws.com" }, Action = "sts:AssumeRole" }]
  })
}

resource "aws_iam_role_policy" "k6_task" {
  name = "${var.name_prefix}-k6-access"
  role = aws_iam_role.k6_task.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "ListScripts"
        Effect    = "Allow"
        Action    = "s3:ListBucket"
        Resource  = aws_s3_bucket.loadtest.arn
        Condition = { StringLike = { "s3:prefix" = "scripts/*" } }
      },
      {
        Sid      = "ReadScripts"
        Effect   = "Allow"
        Action   = "s3:GetObject"
        Resource = "${aws_s3_bucket.loadtest.arn}/scripts/*"
      },
      {
        Sid      = "WriteResults"
        Effect   = "Allow"
        Action   = "s3:PutObject"
        Resource = "${aws_s3_bucket.loadtest.arn}/runs/*"
      },
      {
        Sid      = "InvokeSearchApi"
        Effect   = "Allow"
        Action   = "execute-api:Invoke"
        Resource = "arn:aws:execute-api:${var.aws_region}:${local.account_id}:${var.api_id}/*/${var.api_route}"
      }
    ]
  })
}

# ---------- Lambda: report ----------

resource "aws_iam_role" "report" {
  name = "${var.name_prefix}-loadtest-report-role"
  assume_role_policy = jsonencode({
    Version   = "2012-10-17"
    Statement = [{ Effect = "Allow", Principal = { Service = "lambda.amazonaws.com" }, Action = "sts:AssumeRole" }]
  })
}

resource "aws_iam_role_policy_attachment" "report_logs" {
  role       = aws_iam_role.report.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy" "report" {
  name = "${var.name_prefix}-loadtest-report-access"
  role = aws_iam_role.report.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "ListRuns"
        Effect    = "Allow"
        Action    = "s3:ListBucket"
        Resource  = aws_s3_bucket.loadtest.arn
        Condition = { StringLike = { "s3:prefix" = "runs/*" } }
      },
      {
        Sid      = "ReadAndWriteRuns"
        Effect   = "Allow"
        Action   = ["s3:GetObject", "s3:PutObject"]
        Resource = "${aws_s3_bucket.loadtest.arn}/runs/*"
      },
      {
        Sid    = "InvokeReportModel"
        Effect = "Allow"
        Action = "bedrock:InvokeModel"
        Resource = [
          "arn:aws:bedrock:${var.aws_region}:${local.account_id}:inference-profile/${var.report_model_id}",
          # a cross-region inference profile (us.*) can route to the model in several regions
          "arn:aws:bedrock:*::foundation-model/${replace(var.report_model_id, "/^[a-z]{2}\\./", "")}"
        ]
      }
    ]
  })
}

# ---------- Step Functions ----------

resource "aws_iam_role" "pipeline" {
  name = "${var.name_prefix}-loadtest-pipeline-role"
  assume_role_policy = jsonencode({
    Version   = "2012-10-17"
    Statement = [{ Effect = "Allow", Principal = { Service = "states.amazonaws.com" }, Action = "sts:AssumeRole" }]
  })
}

resource "aws_iam_role_policy" "pipeline" {
  name = "${var.name_prefix}-loadtest-pipeline-access"
  role = aws_iam_role.pipeline.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "RunK6Task"
        Effect   = "Allow"
        Action   = "ecs:RunTask"
        Resource = "arn:aws:ecs:${var.aws_region}:${local.account_id}:task-definition/${aws_ecs_task_definition.k6.family}:*"
      },
      {
        Sid      = "WaitForK6Task"
        Effect   = "Allow"
        Action   = ["ecs:DescribeTasks", "ecs:StopTask"]
        Resource = "arn:aws:ecs:${var.aws_region}:${local.account_id}:task/${aws_ecs_cluster.loadtest.name}/*"
      },
      {
        Sid      = "PassTaskRoles"
        Effect   = "Allow"
        Action   = "iam:PassRole"
        Resource = [aws_iam_role.k6_task.arn, aws_iam_role.k6_execution.arn]
      },
      {
        Sid      = "SyncIntegrationEvents"
        Effect   = "Allow"
        Action   = ["events:PutTargets", "events:PutRule", "events:DescribeRule"]
        Resource = "arn:aws:events:${var.aws_region}:${local.account_id}:rule/StepFunctionsGetEventsForECSTaskRule"
      },
      {
        Sid      = "InvokeReportLambda"
        Effect   = "Allow"
        Action   = "lambda:InvokeFunction"
        Resource = [aws_lambda_function.report.arn, "${aws_lambda_function.report.arn}:*"]
      }
    ]
  })
}
