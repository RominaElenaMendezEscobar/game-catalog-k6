resource "aws_cloudwatch_log_group" "report" {
  name              = "/aws/lambda/${var.name_prefix}-loadtest-report"
  retention_in_days = var.log_retention_days
}

# The image must exist in ECR before this function is created (see README: first deployment)
resource "aws_lambda_function" "report" {
  function_name = "${var.name_prefix}-loadtest-report"
  role          = aws_iam_role.report.arn
  package_type  = "Image"
  image_uri     = "${aws_ecr_repository.report.repository_url}:${var.image_tag}"
  architectures = ["x86_64"]
  memory_size   = var.report_memory
  timeout       = var.report_timeout

  environment {
    variables = {
      BUCKET = aws_s3_bucket.loadtest.id
    }
  }

  depends_on = [aws_cloudwatch_log_group.report, aws_iam_role_policy_attachment.report_logs]
}
