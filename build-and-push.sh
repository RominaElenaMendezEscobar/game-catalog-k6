#!/bin/bash
# Builds the two container images and pushes them to ECR.
#   ./build-and-push.sh            -> both images
#   ./build-and-push.sh k6         -> only the k6 image
#   ./build-and-push.sh report     -> only the report image
#
# The k6 task always uses the latest image on its next run. The report Lambda does not
# reload the image by itself, so this script updates it when the function exists.

set -euo pipefail

REGION="${AWS_REGION:-us-east-1}"
PREFIX="${NAME_PREFIX:-game-catalog}"
TAG="${IMAGE_TAG:-latest}"
WHAT="${1:-all}"

ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
REGISTRY="${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com"
ROOT="$(cd "$(dirname "$0")" && pwd)"

aws ecr get-login-password --region "$REGION" | docker login --username AWS --password-stdin "$REGISTRY"

build() {   # build <repository> <context folder>
  local repo="$1" context="$2"
  echo "==> Building ${repo} from ${context}"
  docker build --platform linux/amd64 --provenance=false -t "${repo}:${TAG}" "$context"
  docker tag "${repo}:${TAG}" "${REGISTRY}/${repo}:${TAG}"
  docker push "${REGISTRY}/${repo}:${TAG}"
  docker image prune -f > /dev/null   # CloudShell has little disk space
}

if [ "$WHAT" = "all" ] || [ "$WHAT" = "k6" ]; then
  build "${PREFIX}-k6" "$ROOT"
fi

if [ "$WHAT" = "all" ] || [ "$WHAT" = "report" ]; then
  build "${PREFIX}-report" "$ROOT/report"
  FUNCTION="${PREFIX}-loadtest-report"
  if aws lambda get-function --function-name "$FUNCTION" > /dev/null 2>&1; then
    echo "==> Updating Lambda ${FUNCTION} with the new image"
    aws lambda update-function-code --function-name "$FUNCTION" \
      --image-uri "${REGISTRY}/${PREFIX}-report:${TAG}" --architectures x86_64 \
      --query LastUpdateStatus --output text
  fi
fi

echo "Done."
