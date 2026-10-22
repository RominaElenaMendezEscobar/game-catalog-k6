#!/bin/bash
# Downloads the k6 scripts from S3, runs a scenario and uploads the results to a
# new folder per run, so previous runs are never overwritten:
#
#   s3://<BUCKET>/runs/<SCENARIO>/<RUN_ID>/
#     k6-summary.json      aggregated metrics (with breakdown by language and decision)
#     k6-results.csv.gz    one row per request and metric, used for charts over time
#     run-info.json        run metadata (scenario, label, dates, exit code, task)
#
# Required environment variables:
#   BUCKET     S3 bucket with scripts/ and runs/ (e.g. game-catalog-loadtest)
#   API_URL    API base URL, without trailing slash
#   SCENARIO   scenario file name in scripts/scenarios/ (smoke, load, stress, spike)
#
# Optional:
#   RUN_ID     run folder name; default: current UTC date (YYYY-MM-DD--HH-MM-SS)
#   RUN_LABEL  free text describing what changed in this run (e.g. "lambda-1024mb")
#   AUTH_MODE  iam (default) signs requests with the task role credentials; none disables signing

set -euo pipefail

: "${BUCKET:?BUCKET is required}"
: "${API_URL:?API_URL is required}"
: "${SCENARIO:?SCENARIO is required}"

RUN_ID="${RUN_ID:-$(date -u +%Y-%m-%d--%H-%M-%S)}"
RUN_LABEL="${RUN_LABEL:-}"
RUN_PREFIX="s3://${BUCKET}/runs/${SCENARIO}/${RUN_ID}"

echo "Run: ${SCENARIO}/${RUN_ID} ${RUN_LABEL:+(${RUN_LABEL})}"

echo "Downloading scripts from s3://${BUCKET}/scripts/"
aws s3 cp "s3://${BUCKET}/scripts/" /work/ --recursive --only-show-errors

# k6 signs the requests with these credentials. On Fargate they come from the task role
# and are temporary, so they are exported right before the test.
if [ "${AUTH_MODE:-iam}" = "iam" ]; then
  eval "$(aws configure export-credentials --format env)"
  export AWS_REGION="${AWS_REGION:-${AWS_DEFAULT_REGION:-us-east-1}}"
fi

STARTED_AT=$(date -u +%Y-%m-%dT%H:%M:%SZ)
echo "Running scenario '${SCENARIO}' against the API"
set +e
k6 run --quiet \
  --out csv=/work/k6-results.csv.gz \
  -e API_URL="${API_URL}" -e SCENARIO="${SCENARIO}" \
  /work/search.js
K6_EXIT_CODE=$?
set -e
FINISHED_AT=$(date -u +%Y-%m-%dT%H:%M:%SZ)

# ECS task metadata (task ARN, revision, image digest) for traceability, when running on ECS
TASK_METADATA="null"
if [ -n "${ECS_CONTAINER_METADATA_URI_V4:-}" ]; then
  TASK_METADATA=$(wget -qO- "${ECS_CONTAINER_METADATA_URI_V4}/task" 2>/dev/null || echo "null")
fi

# k6 returns 99 when a threshold fails: the run is still valid and is analyzed later
cat > /work/run-info.json <<JSON
{
  "run_id": "${RUN_ID}",
  "scenario": "${SCENARIO}",
  "label": "${RUN_LABEL}",
  "started_at": "${STARTED_AT}",
  "finished_at": "${FINISHED_AT}",
  "k6_exit_code": ${K6_EXIT_CODE},
  "thresholds_passed": $([ "${K6_EXIT_CODE}" -eq 0 ] && echo true || echo false),
  "ecs_task": ${TASK_METADATA}
}
JSON

if [ ! -f /work/k6-summary.json ]; then
  echo "k6-summary.json was not generated (k6 exit code ${K6_EXIT_CODE})"
  exit 1
fi

echo "Uploading results to ${RUN_PREFIX}/"
aws s3 cp /work/k6-summary.json   "${RUN_PREFIX}/k6-summary.json"   --only-show-errors
aws s3 cp /work/run-info.json     "${RUN_PREFIX}/run-info.json"     --only-show-errors
if [ -f /work/k6-results.csv ]; then
  aws s3 cp /work/k6-results.csv "${RUN_PREFIX}/k6-results.csv" --only-show-errors
fi

echo "Done (k6 exit code ${K6_EXIT_CODE})"