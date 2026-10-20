"""
Unit tests for deployment constructs and Lambda tick handler.
"""

from unittest.mock import patch, MagicMock
import io
import json
import os
import urllib.error
import pytest

from deploy.tick_lambda.tick_handler import handler


def test_tick_handler_missing_url(monkeypatch):
    monkeypatch.delenv("MCP_SERVER_URL", raising=False)
    res = handler({}, None)
    assert res["statusCode"] == 500
    assert "not configured" in res["error"]


def test_tick_handler_success(monkeypatch):
    monkeypatch.setenv("MCP_SERVER_URL", "http://careloop-alb.us-east-1.elb.amazonaws.com")

    mock_resp = MagicMock()
    mock_resp.getcode.return_value = 200
    mock_resp.read.return_value = json.dumps({"status": "ticked", "protocol_version": "2025-11-25"}).encode("utf-8")
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp):
        res = handler({}, None)
        assert res["statusCode"] == 200
        assert res["result"]["status"] == "ticked"


def test_tick_handler_http_error(monkeypatch):
    monkeypatch.setenv("MCP_SERVER_URL", "http://careloop-alb.us-east-1.elb.amazonaws.com")

    fp = io.BytesIO(b'{"error": "Internal Error"}')
    err = urllib.error.HTTPError(
        url="http://careloop-alb.us-east-1.elb.amazonaws.com/api/mcp/call",
        code=500,
        msg="Internal Error",
        hdrs={},
        fp=fp,
    )

    with patch("urllib.request.urlopen", side_effect=err):
        res = handler({}, None)
        assert res["statusCode"] == 500
        assert "Internal Error" in res["error"]


def test_sam_template_specification():
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    template_path = os.path.join(root, "template.yaml")
    assert os.path.exists(template_path)

    with open(template_path, "r", encoding="utf-8") as f:
        content = f.read()

    # DynamoDB with encryption at rest and single-table schema
    assert "CareLoopTable:" in content
    assert "AWS::DynamoDB::Table" in content
    assert "SSEEnabled: true" in content
    assert "AttributeName: PK" in content
    assert "AttributeName: SK" in content

    # SNS Topic with encryption
    assert "CareLoopTopic:" in content
    assert "AWS::SNS::Topic" in content
    assert "KmsMasterKeyId: alias/aws/sns" in content

    # IAM Least-Privilege Role
    assert "CareLoopTaskRole:" in content
    assert "dynamodb:GetItem" in content
    assert "sns:Publish" in content
    assert "bedrock:InvokeModel" in content

    # ECS Fargate + ALB
    assert "CareLoopCluster:" in content
    assert "CareLoopService:" in content
    assert "CareLoopALB:" in content
    assert "CareLoopTargetGroup:" in content

    # Scheduled EventBridge Rule
    assert "CareLoopTickFunction:" in content
    assert "Schedule: \"rate(1 minute)\"" in content

    # Outputs
    assert "PublicMcpEndpoint:" in content
    assert "/mcp" in content
    assert "SimulatorUrl:" in content


def test_cdk_stack_specification():
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    cdk_stack_path = os.path.join(root, "deploy", "cdk", "careloop_stack.py")
    assert os.path.exists(cdk_stack_path)

    with open(cdk_stack_path, "r", encoding="utf-8") as f:
        content = f.read()

    assert "class CareLoopStack(Stack):" in content
    assert "dynamodb.Table" in content
    assert "encryption=dynamodb.TableEncryption.AWS_MANAGED" in content
    assert "sns.Topic" in content
    assert "bedrock:InvokeModel" in content
    assert "ApplicationLoadBalancedFargateService" in content
    assert "rate(Duration.minutes(1))" in content
    assert "PublicMcpEndpoint" in content


def test_dockerfile_specification():
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    dockerfile_path = os.path.join(root, "Dockerfile")
    assert os.path.exists(dockerfile_path)

    with open(dockerfile_path, "r", encoding="utf-8") as f:
        content = f.read()

    assert "FROM python:3.11-slim" in content
    assert "EXPOSE 8000" in content
    assert "HEALTHCHECK" in content
    assert "careloop.server" in content
