#!/usr/bin/env bash
# Build the API image, push it to ECR and redeploy the ECS service (what the CI does on push to develop).
# Run from anywhere, in Git Bash, after `terraform apply` in deployment/terraform/envs/dev.
#
#   ./scripts/deploy_image.sh            # tag = current git sha
#   ./scripts/deploy_image.sh mytag      # custom tag (latest is always pushed too)

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TF_DIR="$REPO_ROOT/deployment/terraform/envs/dev"
TAG="${1:-$(git -C "$REPO_ROOT" rev-parse --short HEAD)}"

ECR_URL="$(terraform -chdir="$TF_DIR" output -raw ecr_repository_url)"
CLUSTER="$(terraform -chdir="$TF_DIR" output -raw ecs_cluster_name)"
SERVICE="$(terraform -chdir="$TF_DIR" output -raw ecs_service_name)"
REGISTRY="${ECR_URL%%/*}"
REGION="${REGISTRY#*.ecr.}"; REGION="${REGION%%.*}"

echo ">> Login to $REGISTRY"
aws ecr get-login-password --region "$REGION" | docker login --username AWS --password-stdin "$REGISTRY"

echo ">> Build $ECR_URL:$TAG"
docker build -t "$ECR_URL:$TAG" -t "$ECR_URL:latest" "$REPO_ROOT"

echo ">> Push"
docker push "$ECR_URL:$TAG"
docker push "$ECR_URL:latest"

echo ">> Redeploy $SERVICE"
aws ecs update-service --cluster "$CLUSTER" --service "$SERVICE" --force-new-deployment --query 'service.deployments[0].status' --output text
aws ecs wait services-stable --cluster "$CLUSTER" --services "$SERVICE"

echo ">> Public IP"
TASK="$(aws ecs list-tasks --cluster "$CLUSTER" --service-name "$SERVICE" --query 'taskArns[0]' --output text)"
ENI="$(aws ecs describe-tasks --cluster "$CLUSTER" --tasks "$TASK" --query 'tasks[0].attachments[0].details[?name==`networkInterfaceId`].value' --output text)"
IP="$(aws ec2 describe-network-interfaces --network-interface-ids "$ENI" --query 'NetworkInterfaces[0].Association.PublicIp' --output text)"
echo "Swagger: http://$IP:8000/docs"
