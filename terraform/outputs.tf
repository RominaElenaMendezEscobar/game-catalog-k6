output "bucket" {
  value = aws_s3_bucket.loadtest.id
}

output "api_url" {
  value = local.api_url
}

output "ecr_k6" {
  value = aws_ecr_repository.k6.repository_url
}

output "ecr_report" {
  value = aws_ecr_repository.report.repository_url
}

output "cluster" {
  value = aws_ecs_cluster.loadtest.name
}

output "security_group_id" {
  value = aws_security_group.k6.id
}

output "subnet_ids" {
  value = data.aws_subnets.default.ids
}

output "report_lambda" {
  value = aws_lambda_function.report.function_name
}

output "state_machine_arn" {
  value = aws_sfn_state_machine.pipeline.arn
}

output "start_execution_example" {
  value = "aws stepfunctions start-execution --state-machine-arn ${aws_sfn_state_machine.pipeline.arn} --input '{\"scenario\":\"smoke\",\"label\":\"baseline\"}'"
}
