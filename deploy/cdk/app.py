#!/usr/bin/env python3
"""
AWS CDK Application entrypoint for CareLoop.
"""

import os
import aws_cdk as cdk

try:
    from careloop_stack import CareLoopStack
except ImportError:
    from deploy.cdk.careloop_stack import CareLoopStack

app = cdk.App()

account = os.getenv("CDK_DEFAULT_ACCOUNT")
region = os.getenv("CDK_DEFAULT_REGION", os.getenv("AWS_REGION", "us-east-1"))

env = cdk.Environment(account=account, region=region)

bedrock_model_id = app.node.try_get_context("bedrockModelId") or os.getenv(
    "BEDROCK_MODEL_ID", "anthropic.claude-3-haiku-20240307-v1:0"
)
auth_token_secret_arn = app.node.try_get_context("authTokenSecretArn") or os.getenv("ALEXA_AUTH_TOKEN_SECRET_ARN")

CareLoopStack(
    app,
    "CareLoopStack",
    env=env,
    bedrock_model_id=bedrock_model_id,
    auth_token_secret_arn=auth_token_secret_arn,
    description="CareLoop: Streamable HTTP MCP Server for Alexa+ Elderly Care (Hackathon & AWS Builder Challenge)",
)

app.synth()
