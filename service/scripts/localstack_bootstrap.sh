#!/usr/bin/env bash
# Provisions the LocalStack resources `make dev` expects to already exist: the SQS queue
# the webhook enqueues to, and the KMS key/alias Encryptor uses for tenant secrets. LocalStack
# itself starts empty — nothing creates these automatically, unlike real AWS where Terraform did.
set -euo pipefail

ENDPOINT="${AWS_ENDPOINT_URL:-http://localhost:4566}"
REGION="${AWS_REGION:-us-east-1}"
QUEUE_NAME="${SQS_QUEUE_NAME:-wa-platform-dev-inbound}"
KMS_ALIAS="${KMS_ALIAS:-alias/wa-platform-dev}"
export AWS_ACCESS_KEY_ID="${AWS_ACCESS_KEY_ID:-test}"
export AWS_SECRET_ACCESS_KEY="${AWS_SECRET_ACCESS_KEY:-test}"

awslocal() { aws --endpoint-url "$ENDPOINT" --region "$REGION" "$@"; }

until awslocal sqs list-queues >/dev/null 2>&1; do
  echo "waiting for localstack..."
  sleep 1
done

if ! awslocal sqs get-queue-url --queue-name "$QUEUE_NAME" >/dev/null 2>&1; then
  awslocal sqs create-queue --queue-name "$QUEUE_NAME" >/dev/null
  echo "created queue $QUEUE_NAME"
fi

if ! awslocal kms list-aliases --query "Aliases[?AliasName=='$KMS_ALIAS']" --output text | grep -q "$KMS_ALIAS"; then
  key_id=$(awslocal kms create-key --query 'KeyMetadata.KeyId' --output text)
  awslocal kms create-alias --alias-name "$KMS_ALIAS" --target-key-id "$key_id"
  echo "created kms key $key_id with alias $KMS_ALIAS"
fi
