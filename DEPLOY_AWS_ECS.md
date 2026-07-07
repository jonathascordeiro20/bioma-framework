# Deploy B.I.O.M.A. to AWS ECS (Fargate) — step by step

Target architecture: **ECR** (image) → **ECS Fargate** service → behind an
**ALB** (HTTPS) → secrets from **Secrets Manager** → logs to **CloudWatch**.
Artifacts in this repo: [`Dockerfile`](Dockerfile),
[`deploy/aws/task-definition.json`](deploy/aws/task-definition.json),
[`.github/workflows/deploy-ecs.yml`](.github/workflows/deploy-ecs.yml).

> Run these with **your** AWS credentials (`aws configure` / SSO). Nothing here
> stores a secret in the repo. Use a **freshly rotated** OpenRouter key.

## 0 · Prerequisites
- AWS account + `aws` CLI v2 authenticated; Docker (or let the CD build).
- A registered domain + an **ACM certificate** in your region (for HTTPS on the ALB).

## 1 · Variables
```bash
export AWS_REGION=us-east-1
export ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
export APP=bioma
export ECR="$ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$APP"
```

## 2 · ECR — container registry
```bash
aws ecr create-repository --repository-name $APP --image-scanning-configuration scanOnPush=true --region $AWS_REGION
# build + push (or skip and let the CD workflow do it)
aws ecr get-login-password --region $AWS_REGION | docker login --username AWS --password-stdin $ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com
docker build -t $APP .
docker tag $APP:latest $ECR:latest && docker push $ECR:latest
```

## 3 · Secrets Manager — the OpenRouter key (never plaintext)
```bash
aws secretsmanager create-secret --name $APP/openrouter \
  --secret-string "sk-or-...YOUR-ROTATED-KEY..." --region $AWS_REGION
# copy the returned ARN → paste into deploy/aws/task-definition.json (secrets.valueFrom)
```

## 4 · IAM roles (execution + task)
```bash
cat > /tmp/trust-ecs.json <<'JSON'
{ "Version":"2012-10-17","Statement":[{"Effect":"Allow",
  "Principal":{"Service":"ecs-tasks.amazonaws.com"},"Action":"sts:AssumeRole"}]}
JSON

# Execution role: pull image, read the secret, write logs
aws iam create-role --role-name bioma-ecs-execution-role --assume-role-policy-document file:///tmp/trust-ecs.json
aws iam attach-role-policy --role-name bioma-ecs-execution-role \
  --policy-arn arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy
aws iam put-role-policy --role-name bioma-ecs-execution-role --policy-name read-openrouter-secret \
  --policy-document "{\"Version\":\"2012-10-17\",\"Statement\":[{\"Effect\":\"Allow\",\"Action\":\"secretsmanager:GetSecretValue\",\"Resource\":\"arn:aws:secretsmanager:$AWS_REGION:$ACCOUNT_ID:secret:$APP/openrouter*\"}]}"

# Task role: the app's own permissions (minimal — none needed by default)
aws iam create-role --role-name bioma-ecs-task-role --assume-role-policy-document file:///tmp/trust-ecs.json
```

## 5 · CloudWatch log group
```bash
aws logs create-log-group --log-group-name /ecs/$APP --region $AWS_REGION
```

## 6 · Register the task definition
Edit [`deploy/aws/task-definition.json`](deploy/aws/task-definition.json): replace
`<ACCOUNT_ID>`, `<REGION>`, the secret ARN, and confirm the role ARNs. Then:
```bash
aws ecs register-task-definition --cli-input-json file://deploy/aws/task-definition.json --region $AWS_REGION
```

## 7 · ECS cluster
```bash
aws ecs create-cluster --cluster-name $APP-cluster \
  --capacity-providers FARGATE FARGATE_SPOT --region $AWS_REGION
```

## 8 · Networking + ALB (HTTPS)
Use your default VPC (or a dedicated one). Set the subnet IDs, then:
```bash
export VPC_ID=$(aws ec2 describe-vpcs --filters Name=isDefault,Values=true --query 'Vpcs[0].VpcId' --output text)
export SUBNETS=$(aws ec2 describe-subnets --filters Name=vpc-id,Values=$VPC_ID --query 'Subnets[].SubnetId' --output text | tr '\t' ',')

# Security groups: ALB open on 443; tasks only reachable from the ALB on 8000
export ALB_SG=$(aws ec2 create-security-group --group-name $APP-alb-sg --description "bioma alb" --vpc-id $VPC_ID --query GroupId --output text)
aws ec2 authorize-security-group-ingress --group-id $ALB_SG --protocol tcp --port 443 --cidr 0.0.0.0/0
export TASK_SG=$(aws ec2 create-security-group --group-name $APP-task-sg --description "bioma tasks" --vpc-id $VPC_ID --query GroupId --output text)
aws ec2 authorize-security-group-ingress --group-id $TASK_SG --protocol tcp --port 8000 --source-group $ALB_SG

# ALB + target group (health check on /health) + HTTPS listener (needs your ACM cert ARN)
export ALB_ARN=$(aws elbv2 create-load-balancer --name $APP-alb --type application --subnets ${SUBNETS//,/ } --security-groups $ALB_SG --query 'LoadBalancers[0].LoadBalancerArn' --output text)
export TG_ARN=$(aws elbv2 create-target-group --name $APP-tg --protocol HTTP --port 8000 --vpc-id $VPC_ID --target-type ip --health-check-path /health --query 'TargetGroups[0].TargetGroupArn' --output text)
aws elbv2 create-listener --load-balancer-arn $ALB_ARN --protocol HTTPS --port 443 \
  --certificates CertificateArn=<ACM_CERT_ARN> \
  --default-actions Type=forward,TargetGroupArn=$TG_ARN
```
> Prefer the Console's "Create load balancer" wizard if you'd rather click through
> the VPC/subnet/cert wiring — the values above are what it produces.

## 9 · ECS service (Fargate, behind the ALB)
```bash
aws ecs create-service --cluster $APP-cluster --service-name $APP-service \
  --task-definition $APP --desired-count 2 --launch-type FARGATE \
  --health-check-grace-period-seconds 90 \
  --network-configuration "awsvpcConfiguration={subnets=[$SUBNETS],securityGroups=[$TASK_SG],assignPublicIp=ENABLED}" \
  --load-balancers "targetGroupArn=$TG_ARN,containerName=$APP,containerPort=8000" \
  --region $AWS_REGION
```

## 10 · Verify
```bash
export ALB_DNS=$(aws elbv2 describe-load-balancers --load-balancer-arns $ALB_ARN --query 'LoadBalancers[0].DNSName' --output text)
# point your domain (Route 53 A/ALIAS) at $ALB_DNS, then:
curl https://your-domain/health          # → {"status":"alive",...}
```

## 11 · Continuous deployment (GitHub Actions → ECS, via OIDC)
1. Create a GitHub-OIDC IAM role that trusts `token.actions.githubusercontent.com`
   for `repo:jonathascordeiro20/bioma-framework:*`, with permissions to push to
   ECR and update the ECS service (`ecr:*` on the repo, `ecs:UpdateService`,
   `ecs:RegisterTaskDefinition`, `iam:PassRole` for the two roles).
2. Add its ARN as a repo secret: **`AWS_DEPLOY_ROLE_ARN`**
   (`gh secret set AWS_DEPLOY_ROLE_ARN`).
3. Run the workflow: `gh workflow run deploy-ecs.yml` — it builds the image, pushes
   to ECR, and rolls out the new task to ECS. Uncomment the `push:` trigger in
   `.github/workflows/deploy-ecs.yml` to deploy on every merge to `main`.

## 12 · Autoscaling & cost
```bash
# target-tracking autoscaling on CPU (2 → 10 tasks at 60% CPU)
aws application-autoscaling register-scalable-target --service-namespace ecs \
  --resource-id service/$APP-cluster/$APP-service --scalable-dimension ecs:service:DesiredCount \
  --min-capacity 2 --max-capacity 10 --region $AWS_REGION
aws application-autoscaling put-scaling-policy --service-namespace ecs \
  --resource-id service/$APP-cluster/$APP-service --scalable-dimension ecs:service:DesiredCount \
  --policy-name cpu60 --policy-type TargetTrackingScaling \
  --target-tracking-scaling-policy-configuration '{"TargetValue":60.0,"PredefinedMetricSpecification":{"PredefinedMetricType":"ECSServiceAverageCPUUtilization"}}' \
  --region $AWS_REGION
```
- Use **FARGATE_SPOT** capacity for cost-tolerant traffic.
- Keep context apoptosis ON and set an **OpenRouter spend limit** on the key.

## Teardown (avoid charges)
```bash
aws ecs update-service --cluster $APP-cluster --service $APP-service --desired-count 0 --region $AWS_REGION
aws ecs delete-service --cluster $APP-cluster --service $APP-service --force --region $AWS_REGION
aws elbv2 delete-load-balancer --load-balancer-arn $ALB_ARN
aws ecs delete-cluster --cluster $APP-cluster --region $AWS_REGION
```
