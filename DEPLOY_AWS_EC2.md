# Deploy B.I.O.M.A. to a single AWS EC2 instance — step by step

Simplest path: one VM that runs the container. On first boot the
[`ec2-userdata.sh`](deploy/aws/ec2-userdata.sh) bootstrap installs Docker, pulls
the image from ECR, reads the OpenRouter key from Secrets Manager, and starts the
app on port 80.

> Prereqs: the image is already in **ECR** and the key is in **Secrets Manager**
> (steps 2–3 of [`DEPLOY_AWS_ECS.md`](DEPLOY_AWS_ECS.md)). Run everything with your
> own AWS credentials. Use a **freshly rotated** key.

## 1 · Variables
```bash
export AWS_REGION=us-east-1
export ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
export APP=bioma
```

## 2 · Instance IAM role (ECR pull + read the secret + keyless shell)
```bash
cat > /tmp/trust-ec2.json <<'JSON'
{ "Version":"2012-10-17","Statement":[{"Effect":"Allow",
  "Principal":{"Service":"ec2.amazonaws.com"},"Action":"sts:AssumeRole"}]}
JSON
aws iam create-role --role-name bioma-ec2-role --assume-role-policy-document file:///tmp/trust-ec2.json
aws iam attach-role-policy --role-name bioma-ec2-role --policy-arn arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly
aws iam attach-role-policy --role-name bioma-ec2-role --policy-arn arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore
aws iam put-role-policy --role-name bioma-ec2-role --policy-name read-openrouter-secret \
  --policy-document "{\"Version\":\"2012-10-17\",\"Statement\":[{\"Effect\":\"Allow\",\"Action\":\"secretsmanager:GetSecretValue\",\"Resource\":\"arn:aws:secretsmanager:$AWS_REGION:$ACCOUNT_ID:secret:$APP/openrouter*\"}]}"
aws iam create-instance-profile --instance-profile-name bioma-ec2-profile
aws iam add-role-to-instance-profile --instance-profile-name bioma-ec2-profile --role-name bioma-ec2-role
```

## 3 · Security group (HTTP/HTTPS open; SSH only from your IP)
```bash
export VPC_ID=$(aws ec2 describe-vpcs --filters Name=isDefault,Values=true --query 'Vpcs[0].VpcId' --output text)
export SG=$(aws ec2 create-security-group --group-name $APP-ec2-sg --description "bioma ec2" --vpc-id $VPC_ID --query GroupId --output text)
export MYIP=$(curl -s https://checkip.amazonaws.com)
aws ec2 authorize-security-group-ingress --group-id $SG --protocol tcp --port 80  --cidr 0.0.0.0/0
aws ec2 authorize-security-group-ingress --group-id $SG --protocol tcp --port 443 --cidr 0.0.0.0/0
aws ec2 authorize-security-group-ingress --group-id $SG --protocol tcp --port 22  --cidr ${MYIP}/32   # optional; SSM works without SSH
```

## 4 · (Optional) SSH key pair
```bash
aws ec2 create-key-pair --key-name bioma-key --query KeyMaterial --output text > ~/.ssh/bioma-key.pem
chmod 600 ~/.ssh/bioma-key.pem
```
> Skip this if you use **Session Manager** (the role already allows it):
> `aws ssm start-session --target <instance-id>` — no key, no open port 22.

## 5 · Launch the instance (with the bootstrap)
```bash
export AMI=$(aws ssm get-parameters --names /aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64 --query 'Parameters[0].Value' --output text --region $AWS_REGION)

aws ec2 run-instances \
  --image-id $AMI \
  --instance-type t3.xlarge \
  --iam-instance-profile Name=bioma-ec2-profile \
  --security-group-ids $SG \
  --key-name bioma-key \
  --user-data file://deploy/aws/ec2-userdata.sh \
  --block-device-mappings '[{"DeviceName":"/dev/xvda","Ebs":{"VolumeSize":30,"VolumeType":"gp3"}}]' \
  --tag-specifications 'ResourceType=instance,Tags=[{Key=Name,Value=bioma}]' \
  --region $AWS_REGION
```
- **Instance type**: `t3.large` (2 vCPU / 8 GB) minimum; **`t3.xlarge`** (4 vCPU / 16 GB) recommended so mitosis has real cores + torch has RAM. `c7i.xlarge` for compute-heavy.
- **Disk**: 30 GB gp3 (the torch image is a few GB).

## 6 · Verify
```bash
export IID=$(aws ec2 describe-instances --filters Name=tag:Name,Values=bioma Name=instance-state-name,Values=running --query 'Reservations[0].Instances[0].InstanceId' --output text)
export IP=$(aws ec2 describe-instances --instance-ids $IID --query 'Reservations[0].Instances[0].PublicIpAddress' --output text)
# first boot pulls the image (~1–2 min); then:
curl http://$IP/health         # → {"status":"alive",...}
# shell in without SSH:
aws ssm start-session --target $IID
```

## 7 · HTTPS (a domain + TLS)
Point a DNS A-record at the instance's public IP (or an Elastic IP), then put
**Caddy** in front for automatic certificates:
```bash
# on the instance (SSM/SSH):
sudo dnf -y install 'dnf-command(copr)' && sudo dnf -y copr enable @caddy/caddy && sudo dnf -y install caddy
echo "your-domain.com { reverse_proxy localhost:80 }" | sudo tee /etc/caddy/Caddyfile
sudo systemctl enable --now caddy      # auto-provisions a Let's Encrypt cert
```
> For multiple instances / zero-downtime, use an **ALB** instead (see the ECS
> runbook's ALB section) with the instances in a target group.

## 8 · Updates & teardown
```bash
# The bootstrap installs a 10-min auto-update cron. To update now:
aws ssm start-session --target $IID   # then: sudo /usr/local/bin/bioma-update.sh

# Teardown (stop charges):
aws ec2 terminate-instances --instance-ids $IID --region $AWS_REGION
```

## EC2 vs ECS — which?
- **EC2** (this): cheapest + simplest for 1 box; you patch the OS. Good for a
  pilot / single-tenant.
- **ECS Fargate** ([`DEPLOY_AWS_ECS.md`](DEPLOY_AWS_ECS.md)): no servers to patch,
  built-in rolling deploys + autoscaling behind an ALB. Better for production
  scale. Both use the SAME image + secret.
