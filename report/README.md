# 📄 Load test report generator

AWS Lambda (container image) that reads the results of a k6 run from S3 and generates a PDF report:
cover, test setup, results at a glance, analysis charts, conclusions with Amazon Bedrock and annexes.

## Input

```json
{ "bucket": "game-catalog-loadtest", "scenario": "smoke", "run_id": null }
```

| Field | Default | Description |
|---|---|---|
| `scenario` | required | Folder in `runs/` (smoke, load, stress, spike) |
| `run_id` | latest run | Run folder to report, e.g. `2026-10-22--18-06-30` |
| `use_ai` | `true` | Set to `false` to skip Amazon Bedrock |

## Output (same folder as the run)

```
runs/<scenario>/<run_id>/
├── report.pdf
├── metrics.json        → metrics computed by code (KPIs, timeline, data quality)
└── ai-analysis.json    → Bedrock interpretation + validation of the figures it quotes
```

## Customization (no code changes)

| File | Content |
|---|---|
| `config/style.yaml` | Colors (purple / salmon), font, page and chart size |
| `config/metrics.yaml` | Metric glossary and chart explanations (annex, captions and Bedrock context) |
| `config/report.yaml` | Bedrock model, minimum sample size, timeline window |

## How metrics and AI are separated

1. **Code** computes every number (KPIs, percentiles, timeline).
2. **Amazon Bedrock** only interprets those numbers (with the scenario as context) and returns structured JSON.
3. **Code** validates the answer: structure, allowed values, and that every figure quoted by the
   model matches a computed metric. Untraceable figures are listed in the report.

## Run locally

```bash
pip install -r requirements.txt boto3
python main.py --local-dir ./data --scenario smoke --no-ai          # folder with runs/<scenario>/<run_id>/
python main.py --bucket game-catalog-loadtest --scenario smoke        # read from S3, with Bedrock
```

## Deploy

```bash
cd report
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
REPO=$ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com/game-catalog-report
aws ecr create-repository --repository-name game-catalog-report
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin $ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com
docker build --platform linux/amd64 --provenance=false -t game-catalog-report .
docker tag game-catalog-report:latest $REPO:latest && docker push $REPO:latest
```

Then create the Lambda function from the image (1024 MB, 120 s timeout) with a role that has
`AWSLambdaBasicExecutionRole` and the inline policy in `policy-role.json`.
