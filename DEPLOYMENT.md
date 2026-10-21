# CareLoop AWS Deployment & Infrastructure Guide

CareLoop is a self-hosted, enterprise-grade Model Context Protocol (MCP) server for **Alexa+** elder care. This document details the infrastructure architecture, transport compatibility evaluation, preflight verification, deployment procedures, status monitoring, smoke testing, and teardown commands.

---

## 1. Hosting Target & Transport Compatibility Evaluation

### Streamable HTTP Transport Requirements (MCP Spec 2025-11-25)
The Model Context Protocol (MCP) Streamable HTTP transport standard mandates:
1. **Persistent Streaming Connections**: Clients (e.g. Alexa+, simulator, desktop assistants) establish and maintain long-lived HTTP sessions using Server-Sent Events (SSE) and chunked HTTP POST responses.
2. **Bi-directional Communication**: Routine status updates, ambient voice prompts, and tool streaming responses are pushed asynchronously from server to client over the open stream.
3. **Low Latency & Continuous State**: The server maintains in-memory exponential moving average (EWMA) baselines, circular distribution statistics, and an active escalation state machine.

### Architecture Comparison: ECS Fargate + ALB vs. API Gateway + Lambda

| Architecture Dimension | API Gateway + AWS Lambda | ECS Fargate + Application Load Balancer (ALB) | Selection Verdict |
| :--- | :--- | :--- | :--- |
| **Max Connection Timeout** | **Hard 29-second limit** (non-configurable). Disconnects long-lived MCP sessions prematurely. | **Configurable up to 4,000 seconds** (configured to 300s). Natively maintains persistent MCP streaming. | **ECS Fargate wins** |
| **HTTP Streaming / SSE** | Buffers responses; does not support arbitrary chunked HTTP SSE streams to standard HTTP MCP clients. | Natively proxies HTTP/1.1 chunked transfer and HTTP/2 Server-Sent Events without buffering. | **ECS Fargate wins** |
| **Cold Starts & Baseline Prewarming** | Ephemeral execution (500ms–3s cold start) requires reloading historical events and recalculating baselines on every voice query. | Container remains warm (sub-10ms response time); circular statistics and baseline models stay in memory. | **ECS Fargate wins** |
| **Autonomous Scheduled Tick** | Would require separate Lambda or EventBridge execution. | Fargate runs FastMCP server continuously; EventBridge triggers a lightweight 20s runner Lambda once per minute. | **ECS Fargate wins** |
| **Cost Profile** | $0 when idle, but unpredictable under active SSE connections. | Fixed predictable cost: ~$12/mo (Fargate 0.5 vCPU / 1GB RAM) + ~$16/mo (ALB) = ~$28/mo. Zero NAT Gateway charges. | **ECS Fargate optimal** |

**Evaluation Decision**: AWS ECS Fargate behind an Application Load Balancer (ALB) is the **required and mathematically sound hosting target** for CareLoop's Streamable HTTP implementation. Ephemeral API Gateway + Lambda is fundamentally incompatible with the persistent streaming requirements of the MCP 2025-11-25 specification.

---

## 2. Infrastructure Architecture & Components

```
                                  [ Amazon EventBridge ]
                                  (1-minute scheduled tick)
                                             |
                                             v
                                  [ CareLoopTickRunner ]
                                  (AWS Lambda + SQS DLQ)
                                             |
                                             v (HTTP POST /api/mcp/call)
[ Alexa+ / MCP Client ] ---> [ Application Load Balancer ] (Port 80/443, 300s idle timeout)
                                             |
                                             v
                             [ AWS ECS Fargate Container ]
                              - FastMCP Streamable HTTP (:8000)
                              - In-memory circular statistics
                              - PrivacyLogFilter (PII scrubbing)
                                             |
                   +-------------------------+-------------------------+
                   |                         |                         |
                   v                         v                         v
          [ Amazon DynamoDB ]         [ Amazon SNS ]          [ Amazon Bedrock ]
          - PK (String), SK (String)  - CareLoopAlertsTopic   - claude-3-haiku
          - KMS SSE at rest           - KMS SSE (aws/sns)     - Scoped least-privilege
          - Point-in-time recovery    - SMS & Email alerts    - Daily summary & Q&A
          - TTL auto-purge enabled    - Delivery tracking
```

### Components Provisioned:
1. **Amazon DynamoDB (`CareLoopData`)**:
   - Single-table design (`PK` partition key, `SK` sort key).
   - On-Demand billing mode (`PAY_PER_REQUEST`) with zero idle cost.
   - Server-side encryption with AWS-managed KMS.
   - Point-in-Time Recovery (PITR) enabled.
   - Time-to-Live (`TTL`) attribute enabled for automatic retention pruning.
2. **Amazon SNS (`CareLoopAlertsTopic`)**:
   - Encrypted with KMS (`alias/aws/sns`).
   - Supports SMS, email, and mobile push notifications for family caregivers.
3. **AWS IAM Least-Privilege Roles**:
   - `CareLoopTaskRole`: Restricted strictly to `CareLoopData` table ARN, `CareLoopAlertsTopic` ARN, and Bedrock model ARN `arn:aws:bedrock:${AWS::Region}::foundation-model/${BedrockModelId}`.
   - `CareLoopExecutionRole`: Container pull from ECR and logging to CloudWatch.
   - `CareLoopTickRunner` Role: Basic Lambda execution role with optional Secrets Manager token access.
4. **AWS Secrets Manager Integration**:
   - Optional `ALEXA_AUTH_TOKEN_SECRET_ARN` parameter. If configured, secrets are injected directly into container environment and retrieved at runtime by Lambda, never written to git or CloudFormation templates.
5. **Scheduled EventBridge Escalation Worker**:
   - Runs every 1 minute (`rate(1 minute)`).
   - 20-second timeout.
   - Dead Letter Queue (`CareLoopTickRunnerDLQ`) with 14-day retention.
   - Retry policy: maximum 2 attempts, maximum 300s event age.
6. **Application Load Balancer & Health Checks**:
   - Health check path: `/health` on port 8000, 30-second interval, 5-second timeout, 2 healthy thresholds.
   - Idle timeout: 300 seconds for persistent Streamable HTTP streaming.
7. **CloudWatch Logs & Metrics**:
   - Log group: `/ecs/careloop-mcp` with 30-day retention.
   - `PrivacyLogFilter` scrubs tokens, passwords, authorization headers, phone numbers, and PII from logs.

---

## 3. Prerequisites & Environment Setup

### Prerequisites:
- **AWS CLI v2** configured with active credentials (`aws configure` or SSO).
- **Docker** daemon running locally (to build the container image).
- **Python 3.11+** virtual environment.
- **AWS CDK v2** (`npm install -g aws-cdk`) OR **AWS SAM CLI** (`sam --version`).
- **Amazon Bedrock Foundation Model Access**: Ensure `anthropic.claude-3-haiku-20240307-v1:0` is enabled in your AWS region (us-east-1, us-west-2, or eu-west-1) via AWS Bedrock Console -> Model Access.

### Required IAM Deployment Permissions:
The deploying user or role must have permissions for:
- `cloudformation:*`
- `ec2:*` (VPC, Subnets, Route Tables, Security Groups, Load Balancers)
- `ecs:*` (Cluster, TaskDefinition, Service)
- `iam:*` (CreateRole, PutRolePolicy, AttachRolePolicy, PassRole)
- `dynamodb:*` (CreateTable, DescribeTable, DeleteTable, UpdateTimeToLive)
- `sns:*` (CreateTopic, SetTopicAttributes, DeleteTopic)
- `events:*` (PutRule, PutTargets, DeleteRule, RemoveTargets)
- `lambda:*` (CreateFunction, AddPermission, DeleteFunction)
- `sqs:*` (CreateQueue, SetQueueAttributes, DeleteQueue)
- `logs:*` (CreateLogGroup, PutRetentionPolicy, DeleteLogGroup)
- `secretsmanager:GetSecretValue` (if using secret ARN)

### Estimated AWS Cost Drivers:
- **ECS Fargate Task (0.5 vCPU, 1 GB RAM)**: ~$0.017/hour (~$12.50/month).
- **Application Load Balancer (ALB)**: ~$0.0225/hour (~$16.20/month) + LCU charges (~$1.00/month).
- **Networking**: VPC uses direct public subnets with zero NAT Gateways ($0.00/month vs $32.40/month saved).
- **DynamoDB**: On-Demand billing ($0 idle; $1.25 per million writes; $0.25 per million reads).
- **Amazon SNS**: First 1,000 email notifications free; SMS ~$0.0075/message (destination dependent).
- **EventBridge & Lambda Tick Runner**: ~43,200 invocations/month (well within AWS Free Tier of 1M requests/month).
- **Amazon Bedrock Claude 3 Haiku**: $0.25 per 1M input tokens, $1.25 per 1M output tokens (~$0.50/month for daily summaries).
- **Total Estimated Idle Cost**: **~$30.00 / month**.

---

## 4. Local Template Validation & Infrastructure Tests

Before touching any AWS APIs or creating cloud resources, validate all infrastructure templates locally.

### Step 1: Run Infrastructure Unit Tests
Verify CDK synthesis, SAM template schema, DynamoDB TTL, Bedrock IAM scoping, SQS DLQ, and tick handler:
```bash
.venv/bin/pytest -v tests/test_deployment.py
```
*Expected result: 16 passed tests.*

### Step 2: Validate CDK Stack Synthesis Locally
```bash
.venv/bin/python -c "
import aws_cdk as cdk
from deploy.cdk.careloop_stack import CareLoopStack
from aws_cdk.assertions import Template

app = cdk.App()
stack = CareLoopStack(app, 'ValidationStack', env=cdk.Environment(account='123456789012', region='us-east-1'))
template = Template.from_stack(stack)
print('Synthesized successfully with', len(template.to_json()['Resources']), 'AWS resources.')
"
```

### Step 3: Validate SAM Template Locally (Optional if SAM CLI is installed)
```bash
sam validate --template template.yaml
```

---

## 5. Deployment Procedures

> **IMPORTANT**: Do NOT run deployment commands until explicit approval and credentials have been verified.

### Option A: Deploying via AWS CDK (Recommended)

1. **Navigate to CDK directory and install dependencies**:
   ```bash
   cd deploy/cdk
   pip install -r requirements.txt
   ```

2. **Bootstrap the AWS Environment (One-time setup per account/region)**:
   ```bash
   cdk bootstrap aws://<YOUR_ACCOUNT_ID>/<YOUR_AWS_REGION>
   ```

3. **Deploy the Stack (with optional Secrets Manager ARN)**:
   ```bash
   # Deploy standard stack:
   cdk deploy CareLoopStack --outputs-file cdk-outputs.json

   # Or deploy with an existing AWS Secrets Manager token secret:
   cdk deploy CareLoopStack \
     --context authTokenSecretArn="arn:aws:secretsmanager:<REGION>:<ACCOUNT>:secret:careloop-token-XYZ" \
     --outputs-file cdk-outputs.json
   ```

4. **Retrieve Real Infrastructure Outputs (Never guess URLs)**:
   ```bash
   cat cdk-outputs.json
   ```

---

### Option B: Deploying via AWS SAM

1. **Build Container and Artifacts**:
   ```bash
   sam build
   ```

2. **Deploy with Interactive Guided Setup**:
   ```bash
   sam deploy --guided \
     --stack-name careloop \
     --capabilities CAPABILITY_IAM \
     --region us-east-1
   ```

3. **Retrieve Real Stack Outputs via AWS CLI**:
   ```bash
   aws cloudformation describe-stacks \
     --stack-name careloop \
     --query "Stacks[0].Outputs" \
     --output table
   ```

---

## 6. Post-Deployment Status Checks & Health Verification

Once deployed, retrieve the public endpoint directly from CloudFormation outputs:

```bash
ALB_DNS=$(aws cloudformation describe-stacks \
  --stack-name CareLoopStack \
  --query "Stacks[0].Outputs[?OutputKey=='PublicMcpEndpoint'].OutputValue" \
  --output text | sed 's|http://||' | sed 's|/mcp||')

echo "CareLoop ALB DNS: ${ALB_DNS}"
```

### 1. Target Group Health Check:
```bash
curl -f -i http://${ALB_DNS}/health
```
*Expected response: HTTP 200 OK with `{"status": "healthy", ...}`.*

### 2. Check ECS Service & Fargate Task Status:
```bash
aws ecs describe-services \
  --cluster CareLoopCluster \
  --services CareLoopMcpServer \
  --query "services[0].{Status:status, RunningCount:runningCount, DesiredCount:desiredCount}"
```

### 3. Check Live CloudWatch Logs (Privacy-Scrubbed):
```bash
aws logs tail /ecs/careloop-mcp --follow
```

### 4. Check EventBridge Tick Monitoring & Dead Letter Queue:
```bash
DLQ_URL=$(aws cloudformation describe-stacks \
  --stack-name CareLoopStack \
  --query "Stacks[0].Outputs[?OutputKey=='TickDLQUrl'].OutputValue" \
  --output text)

aws sqs get-queue-attributes \
  --queue-url "${DLQ_URL}" \
  --attribute-names ApproximateNumberOfMessages ApproximateNumberOfMessagesNotVisible
```
*Expected response: `ApproximateNumberOfMessages: 0` (indicating all 1-minute ticks succeed).*

---

## 7. Live Smoke Testing

### Step 1: MCP Client End-to-End Discovery & Tool Execution
Use CareLoop's real MCP client to discover tools and verify Streamable HTTP roundtrips against the deployed ALB endpoint:
```bash
python scripts/client_test.py --url "http://${ALB_DNS}/mcp"
```
*Verifies: `log_routine_event`, `check_routine_health`, `schedule_reminder`, `notify_family`, `confirm_ok`, `daily_summary`, `ask_memory`, and `tick_escalation`.*

### Step 2: REST Bridge Verification:
```bash
curl -X POST "http://${ALB_DNS}/api/mcp/call" \
  -H "Content-Type: application/json" \
  -d '{"tool": "check_routine_health", "arguments": {"person_id": "eleanor"}}'
```

### Step 3: Opt-in Amazon SNS Alert Delivery Smoke Test (Manual Opt-In)
```bash
TOPIC_ARN=$(aws cloudformation describe-stacks \
  --stack-name CareLoopStack \
  --query "Stacks[0].Outputs[?OutputKey=='SnsTopicArn'].OutputValue" \
  --output text)

RUN_AWS_SMOKE_TEST=1 CARELOOP_SNS_TOPIC_ARN="${TOPIC_ARN}" .venv/bin/pytest -v tests/test_aws_sns_smoke.py
```

---

## 8. Documented Clean Teardown Procedure

To immediately terminate all running AWS resources, delete persistent storage, and avoid recurring charges:

### Teardown via CDK:
```bash
cd deploy/cdk
cdk destroy CareLoopStack --force
```

### Teardown via SAM:
```bash
sam delete --stack-name careloop --no-prompts
```

### Verify Teardown Completion:
```bash
aws cloudformation describe-stacks --stack-name CareLoopStack 2>&1 | grep -q "does not exist" && echo "Stack torn down cleanly."
```

---

## 9. Local Independence: Zero AWS Dependency for Local Development & Demos

CareLoop is architected so that the local SQLite database and console notifier operate 100% offline without AWS credentials:

```bash
# Run CareLoop locally with SQLite and Console Notifier
STORAGE_BACKEND=sqlite \
NOTIFIER_TYPE=console \
CLOCK_MODE=simulated \
python -m careloop.server
```

- Open the interactive simulator UI at `http://127.0.0.1:8000/simulator`.
- Run scenarios like *"Dad skips lunch"* with complete state persistence and escalation notifications printed to the terminal console.
- Run unit test suite completely offline:
  ```bash
  .venv/bin/pytest -v
  ```
