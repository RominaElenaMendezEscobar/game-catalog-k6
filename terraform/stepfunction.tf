resource "aws_sfn_state_machine" "pipeline" {
  name     = "${var.name_prefix}-loadtest-pipeline"
  role_arn = aws_iam_role.pipeline.arn
  type     = "STANDARD"

  definition = jsonencode({
    Comment       = "Runs a k6 load test on ECS Fargate and generates the PDF report of that run"
    QueryLanguage = "JSONata"
    StartAt       = "PrepareRun"
    States = {
      PrepareRun = {
        Type    = "Pass"
        Comment = "Scenario and label come from the input; the run_id is the current UTC date"
        Output = {
          scenario = "{% $exists($states.input.scenario) ? $states.input.scenario : 'smoke' %}"
          label    = "{% $exists($states.input.label) ? $states.input.label : '' %}"
          run_id   = "{% $fromMillis($millis(), '[Y0001]-[M01]-[D01]--[H01]-[m01]-[s01]') %}"
        }
        Next = "RunLoadTest"
      }
      RunLoadTest = {
        Type     = "Task"
        Comment  = "Starts the k6 container and waits until it stops"
        Resource = "arn:aws:states:::ecs:runTask.sync"
        Arguments = {
          Cluster        = aws_ecs_cluster.loadtest.arn
          TaskDefinition = aws_ecs_task_definition.k6.family
          LaunchType     = "FARGATE"
          NetworkConfiguration = {
            AwsvpcConfiguration = {
              Subnets        = data.aws_subnets.default.ids
              SecurityGroups = [aws_security_group.k6.id]
              AssignPublicIp = "ENABLED"
            }
          }
          Overrides = {
            ContainerOverrides = [{
              Name = "k6"
              Environment = [
                { Name = "SCENARIO", Value = "{% $states.input.scenario %}" },
                { Name = "RUN_ID", Value = "{% $states.input.run_id %}" },
                { Name = "RUN_LABEL", Value = "{% $states.input.label %}" }
              ]
            }]
          }
        }
        Output         = "{% $states.input %}"
        TimeoutSeconds = 1800
        Next           = "GenerateReport"
      }
      GenerateReport = {
        Type     = "Task"
        Comment  = "Builds report.pdf, metrics.json and ai-analysis.json for the same run_id"
        Resource = "arn:aws:states:::lambda:invoke"
        Arguments = {
          FunctionName = aws_lambda_function.report.arn
          Payload = {
            bucket   = aws_s3_bucket.loadtest.id
            scenario = "{% $states.input.scenario %}"
            run_id   = "{% $states.input.run_id %}"
          }
        }
        Retry = [{
          ErrorEquals     = ["Lambda.ServiceException", "Lambda.TooManyRequestsException"]
          IntervalSeconds = 5
          MaxAttempts     = 3
          BackoffRate     = 2
        }]
        Output = "{% $states.result.Payload %}"
        End    = true
      }
    }
  })
}
