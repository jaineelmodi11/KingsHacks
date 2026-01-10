# Deploy to AWS App Runner (Backboard Backend)

Fastest hackathon path: Dockerize locally → push to Amazon ECR → create an App Runner service pointing at the image with env vars set.

## Prereqs
- AWS CLI configured and `aws sts get-caller-identity` works.
- Choose a region (example: `ca-central-1`).
- Backboard key rotated and placed in an env var for deployment.

## 1) Build and test the container locally
```bash
# from repo root
docker build -t backboard-api .
docker run --rm --env-file .env -p 8000:8000 backboard-api
curl -s http://127.0.0.1:8000/healthz
```

## 2) Push to Amazon ECR
```bash
AWS_REGION=ca-central-1           # pick your region
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
REPO=backboard-api

aws ecr create-repository --repository-name $REPO --region $AWS_REGION || true

aws ecr get-login-password --region $AWS_REGION | \
  docker login --username AWS --password-stdin \
  $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com

docker tag backboard-api:latest \
  $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$REPO:latest

docker push \
  $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$REPO:latest
```

## 3) Create an App Runner service (from ECR image)
- Source: ECR image you just pushed.
- Port: `8000` (App Runner will pass `PORT`; Docker CMD uses `${PORT:-8000}`).
- Env vars (App Runner console → Environment):
  - `BACKBOARD_API_KEY=<your_rotated_key>`
  - `API_BASE_URL=https://app.backboard.io/api`
- Health check: HTTP path `/healthz` (switch from default TCP).

After deploy, test:
```bash
curl -s https://<your-apprunner-url>/healthz
```

## 4) Notes
- SQLite (`backend/data/sessions.db`) is fine for demos but will reset on redeploy in App Runner; for persistence, migrate sessions + audit_log to DynamoDB or RDS later.
- Keep your Backboard key rotated—never commit it.***
