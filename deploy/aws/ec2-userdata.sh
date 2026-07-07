#!/bin/bash
# B.I.O.M.A. — EC2 user-data bootstrap (Amazon Linux 2023).
# Paste this as the instance "User data" (or --user-data file://...). On first
# boot it installs Docker, pulls the image from ECR (via the instance IAM role),
# reads OPENROUTER_API_KEY from Secrets Manager, and runs the app on port 80.
#
# The instance profile must allow: ECR pull, secretsmanager:GetSecretValue on
# bioma/openrouter, and (optional) SSM for keyless shell access.
set -euxo pipefail

APP=bioma
ORIGINS="https://app.example.com"   # <-- set to your real front-end origin(s)

# Region + account from the instance metadata (IMDSv2) — no hardcoding.
TOKEN=$(curl -s -X PUT "http://169.254.169.254/latest/api/token" -H "X-aws-ec2-metadata-token-ttl-seconds: 300")
REGION=$(curl -s -H "X-aws-ec2-metadata-token: $TOKEN" http://169.254.169.254/latest/dynamic/instance-identity/document | grep -oP '"region"\s*:\s*"\K[^"]+')
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text --region "$REGION")
IMAGE="$ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com/$APP:latest"

# Docker
dnf -y update
dnf -y install docker
systemctl enable --now docker

# ECR login (instance role)
aws ecr get-login-password --region "$REGION" \
  | docker login --username AWS --password-stdin "$ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com"

# OpenRouter key from Secrets Manager (never stored on disk in plaintext beyond the container env)
KEY=$(aws secretsmanager get-secret-value --secret-id "$APP/openrouter" \
      --query SecretString --output text --region "$REGION" 2>/dev/null || echo "")

# Run (auto-restart on reboot/crash). Maps host :80 → container :8000.
docker pull "$IMAGE"
docker rm -f "$APP" 2>/dev/null || true
docker run -d --name "$APP" --restart unless-stopped -p 80:8000 \
  -e OPENROUTER_API_KEY="$KEY" \
  -e BIOMA_ALLOWED_ORIGINS="$ORIGINS" \
  -e OMP_NUM_THREADS=1 -e MKL_NUM_THREADS=1 -e KMP_DUPLICATE_LIB_OK=TRUE \
  "$IMAGE"

# A tiny auto-update timer (re-pull latest every 10 min) — optional; remove if undesired.
cat > /usr/local/bin/bioma-update.sh <<EOF
#!/bin/bash
set -e
aws ecr get-login-password --region "$REGION" | docker login --username AWS --password-stdin "$ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com"
NEW=\$(docker pull "$IMAGE" | grep -c "Downloaded newer image" || true)
if [ "\$NEW" -gt 0 ]; then
  docker rm -f "$APP" || true
  docker run -d --name "$APP" --restart unless-stopped -p 80:8000 \
    -e OPENROUTER_API_KEY="\$(aws secretsmanager get-secret-value --secret-id $APP/openrouter --query SecretString --output text --region $REGION)" \
    -e BIOMA_ALLOWED_ORIGINS="$ORIGINS" -e OMP_NUM_THREADS=1 -e KMP_DUPLICATE_LIB_OK=TRUE "$IMAGE"
fi
EOF
chmod +x /usr/local/bin/bioma-update.sh
echo "*/10 * * * * root /usr/local/bin/bioma-update.sh >> /var/log/bioma-update.log 2>&1" > /etc/cron.d/bioma-update
