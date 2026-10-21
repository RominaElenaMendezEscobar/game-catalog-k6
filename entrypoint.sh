#!/bin/bash
# Downloads the k6 scripts from S3, runs a scenario and uploads the results.
#
# Required environment variables:
#   BUCKET     S3 bucket with scripts/ and runs/ (e.g. game-catalog-loadtest)
#   API_URL    API base URL, without trailing slash
#   SCENARIO   scenario file name in scripts/scenarios/ (smoke, load, stress, spike)
#   RUN_NAME   folder for the results in runs/ (e.g. load-2026-10-21-1)

set -euo pipefail

: "${BUCKET:?BUCKET is required}"
: "${API_URL:?API_URL is required}"
: "${SCENARIO:?SCENARIO is required}"
: "${RUN_NAME:?RUN_NAME is required}"

echo "Downloading scripts from s3://${BUCKET}/scripts/"
aws s3 cp "s3://${BUCKET}/scripts/" /work/ --recursive --only-show-errors

echo "Running scenario '${SCENARIO}' against the API"
set +e
k6 run --quiet -e API_URL="${API_URL}" -e SCENARIO="${SCENARIO}" /work/search.js
K6_EXIT_CODE=$?
set -e

# k6 returns 99 when a threshold fails: the run is still valid and is analyzed later
echo "{\"run_name\": \"${RUN_NAME}\", \"scenario\": \"${SCENARIO}\", \"k6_exit_code\": ${K6_EXIT_CODE}}" > /work/run-info.json

if [ ! -f /work/k6-summary.json ]; then
  echo "k6-summary.json was not generated (k6 exit code ${K6_EXIT_CODE})"
  exit 1
fi

echo "Uploading results to s3://${BUCKET}/runs/${RUN_NAME}/"
aws s3 cp /work/k6-summary.json "s3://${BUCKET}/runs/${RUN_NAME}/k6-summary.json" --only-show-errors
aws s3 cp /work/run-info.json    "s3://${BUCKET}/runs/${RUN_NAME}/run-info.json"    --only-show-errors

echo "Done (k6 exit code ${K6_EXIT_CODE})"
