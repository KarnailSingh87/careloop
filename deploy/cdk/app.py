#!/usr/bin/env python3
"""
AWS CDK Application entrypoint for CareLoop.
"""

import os
import aws_cdk as cdk
from careloop_stack import CareLoopStack

app = cdk.App()

account = os.getenv("CDK_DEFAULT_ACCOUNT")
region = os.getenv("CDK_DEFAULT_REGION", os.getenv("AWS_REGION", "us-east-1"))

env = cdk.Environment(account=account, region=region)

CareLoopStack(
    app,
    "CareLoopStack",
    env=env,
    description="CareLoop: Streamable HTTP MCP Server for Alexa+ Elderly Care (Hackathon & AWS Builder Challenge)",
)

app.synth()
