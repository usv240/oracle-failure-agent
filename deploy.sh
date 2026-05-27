#!/bin/bash
# One-command deploy to Google Cloud Run
# Usage: ./deploy.sh [PROJECT_ID]
set -euo pipefail

PROJECT_ID="${1:-$(gcloud config get-value project)}"
REGION="us-central1"
SERVICE="oracle"
IMAGE="gcr.io/${PROJECT_ID}/${SERVICE}:latest"

echo "Deploying The Failure Oracle to Cloud Run..."
echo "  Project: ${PROJECT_ID}"
echo "  Region:  ${REGION}"
echo "  Image:   ${IMAGE}"

# Build + push
gcloud builds submit \
  --tag "${IMAGE}" \
  --project "${PROJECT_ID}"

# Deploy (env vars loaded from env-cloud.yaml — keep this file out of git)
gcloud run deploy "${SERVICE}" \
  --image "${IMAGE}" \
  --region "${REGION}" \
  --platform managed \
  --allow-unauthenticated \
  --memory 1Gi \
  --cpu 1 \
  --min-instances 0 \
  --max-instances 3 \
  --port 8080 \
  --timeout 300 \
  --env-vars-file env-cloud.yaml \
  --project "${PROJECT_ID}"

URL=$(gcloud run services describe "${SERVICE}" \
  --region "${REGION}" \
  --project "${PROJECT_ID}" \
  --format 'value(status.url)')

echo ""
echo "Deployed: ${URL}"
