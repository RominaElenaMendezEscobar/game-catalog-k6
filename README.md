# game-catalog-k6
Load testing a GenAI API on AWS with k6: scenarios defined in JSON (smoke, load, stress, spike) run on ECS Fargate and orchestrated by Step Functions. Metrics from k6 and CloudWatch are collected by Lambda, and Amazon Bedrock generates an analysis of the results. Tests an API Gateway endpoint backed by Lambda, Amazon Bedrock and S3 Vectors.
