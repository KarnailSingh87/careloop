"""
Unit and integration tests for CareLoop deployment constructs, CDK stack synthesis,
SAM template specifications, and the EventBridge Lambda tick handler.
"""

from unittest.mock import patch, MagicMock
import io
import json
import os
import urllib.error
import pytest
import yaml

import aws_cdk as cdk
from aws_cdk.assertions import Template, Match

from deploy.cdk.careloop_stack import CareLoopStack
from deploy.tick_lambda.tick_handler import handler


# =============================================================================
# 1. Tick Handler Lambda Tests
# =============================================================================


def test_tick_handler_missing_url(monkeypatch):
    """Tick handler should fail fast if MCP_SERVER_URL is not set."""
    monkeypatch.delenv("MCP_SERVER_URL", raising=False)
    res = handler({}, None)
    assert res["statusCode"] == 500
    assert "not configured" in res["error"]


def test_tick_handler_success(monkeypatch):
    """Tick handler should call /api/mcp/call with tool=tick_escalation."""
    monkeypatch.setenv("MCP_SERVER_URL", "http://careloop-alb.us-east-1.elb.amazonaws.com")

    mock_resp = MagicMock()
    mock_resp.getcode.return_value = 200
    mock_resp.read.return_value = json.dumps({"status": "ticked", "protocol_version": "2025-11-25"}).encode("utf-8")
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp) as mock_urlopen:
        res = handler({}, None)
        assert res["statusCode"] == 200
        assert res["result"]["status"] == "ticked"

        req = mock_urlopen.call_args[0][0]
        assert req.get_full_url() == "http://careloop-alb.us-east-1.elb.amazonaws.com/api/mcp/call"
        body = json.loads(req.data.decode("utf-8"))
        assert body["tool"] == "tick_escalation"


def test_tick_handler_with_env_auth_token(monkeypatch):
    """Tick handler attaches Bearer token if ALEXA_AUTH_TOKEN is present in env."""
    monkeypatch.setenv("MCP_SERVER_URL", "http://careloop-alb.us-east-1.elb.amazonaws.com")
    monkeypatch.setenv("ALEXA_AUTH_TOKEN", "alexa_sec_999")

    mock_resp = MagicMock()
    mock_resp.getcode.return_value = 200
    mock_resp.read.return_value = json.dumps({"status": "ticked"}).encode("utf-8")
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp) as mock_urlopen:
        res = handler({}, None)
        assert res["statusCode"] == 200
        req = mock_urlopen.call_args[0][0]
        assert req.get_header("Authorization") == "Bearer alexa_sec_999"
        assert req.get_header("X-alexa-auth-token") == "alexa_sec_999"


def test_tick_handler_with_secrets_manager_token(monkeypatch):
    """Tick handler resolves token from Secrets Manager if ALEXA_AUTH_TOKEN_SECRET_ARN is provided."""
    monkeypatch.setenv("MCP_SERVER_URL", "http://careloop-alb.us-east-1.elb.amazonaws.com")
    monkeypatch.delenv("ALEXA_AUTH_TOKEN", raising=False)
    monkeypatch.delenv("MCP_AUTH_TOKEN", raising=False)
    monkeypatch.setenv(
        "ALEXA_AUTH_TOKEN_SECRET_ARN", "arn:aws:secretsmanager:us-east-1:123456789012:secret:careloop-token"
    )

    mock_sm = MagicMock()
    mock_sm.get_secret_value.return_value = {"SecretString": "sec_token_from_sm_123"}

    mock_resp = MagicMock()
    mock_resp.getcode.return_value = 200
    mock_resp.read.return_value = json.dumps({"status": "ticked"}).encode("utf-8")
    mock_resp.__enter__.return_value = mock_resp

    with patch("boto3.client", return_value=mock_sm):
        with patch("urllib.request.urlopen", return_value=mock_resp) as mock_urlopen:
            res = handler({}, None)
            assert res["statusCode"] == 200
            req = mock_urlopen.call_args[0][0]
            assert req.get_header("Authorization") == "Bearer sec_token_from_sm_123"


def test_tick_handler_http_error(monkeypatch):
    """Tick handler captures HTTP error response codes gracefully."""
    monkeypatch.setenv("MCP_SERVER_URL", "http://careloop-alb.us-east-1.elb.amazonaws.com")

    fp = io.BytesIO(b'{"error": "Escalation worker failure"}')
    err = urllib.error.HTTPError(
        url="http://careloop-alb.us-east-1.elb.amazonaws.com/api/mcp/call",
        code=502,
        msg="Bad Gateway",
        hdrs={},
        fp=fp,
    )

    with patch("urllib.request.urlopen", side_effect=err):
        res = handler({}, None)
        assert res["statusCode"] == 502
        assert "Escalation worker failure" in res["error"]


# =============================================================================
# 2. AWS CDK Stack Synthesis and Infrastructure Tests
# =============================================================================


@pytest.fixture(scope="module")
def synthesized_cdk_template():
    """Synthesizes the CDK stack for testing."""
    app = cdk.App()
    stack = CareLoopStack(
        app,
        "CareLoopTestStack",
        bedrock_model_id="anthropic.claude-3-haiku-20240307-v1:0",
        auth_token_secret_arn="arn:aws:secretsmanager:us-east-1:123456789012:secret:careloop-token-AbCdEf",
        env=cdk.Environment(account="123456789012", region="us-east-1"),
    )
    return Template.from_stack(stack)


def test_cdk_dynamodb_specification(synthesized_cdk_template):
    """Verify DynamoDB single-table schema, SSE, PITR, and TTL."""
    synthesized_cdk_template.has_resource_properties(
        "AWS::DynamoDB::Table",
        {
            "TableName": "CareLoopData",
            "BillingMode": "PAY_PER_REQUEST",
            "KeySchema": [
                {"AttributeName": "PK", "KeyType": "HASH"},
                {"AttributeName": "SK", "KeyType": "RANGE"},
            ],
            "SSESpecification": {
                "SSEEnabled": True,
            },
            "TimeToLiveSpecification": {
                "AttributeName": "TTL",
                "Enabled": True,
            },
            "PointInTimeRecoverySpecification": {
                "PointInTimeRecoveryEnabled": True,
            },
        },
    )


def test_cdk_sns_topic_encrypted(synthesized_cdk_template):
    """Verify Amazon SNS topic is provisioned with KMS encryption."""
    synthesized_cdk_template.has_resource_properties(
        "AWS::SNS::Topic",
        {
            "TopicName": "CareLoopAlertsTopic",
            "KmsMasterKeyId": Match.any_value(),
        },
    )


def test_cdk_task_role_least_privilege_and_bedrock_restriction(synthesized_cdk_template):
    """Verify IAM Task Role restricts Bedrock access strictly to configured model."""
    synthesized_cdk_template.has_resource_properties(
        "AWS::IAM::Policy",
        {
            "PolicyDocument": {
                "Statement": Match.array_with(
                    [
                        Match.object_like(
                            {
                                "Action": [
                                    "bedrock:InvokeModel",
                                    "bedrock:InvokeModelWithResponseStream",
                                ],
                                "Effect": "Allow",
                                "Resource": "arn:aws:bedrock:us-east-1::foundation-model/anthropic.claude-3-haiku-20240307-v1:0",
                            }
                        ),
                    ]
                )
            }
        },
    )


def test_cdk_ecs_fargate_and_alb_settings(synthesized_cdk_template):
    """Verify ALB target group health checks and idle timeout for Streamable HTTP."""
    # Target group health check
    synthesized_cdk_template.has_resource_properties(
        "AWS::ElasticLoadBalancingV2::TargetGroup",
        {
            "HealthCheckPath": "/health",
            "HealthCheckPort": "8000",
            "Protocol": "HTTP",
            "Matcher": {"HttpCode": "200"},
            "HealthCheckIntervalSeconds": 30,
            "HealthCheckTimeoutSeconds": 5,
        },
    )

    # ALB idle timeout (300s for persistent HTTP streaming)
    synthesized_cdk_template.has_resource_properties(
        "AWS::ElasticLoadBalancingV2::LoadBalancer",
        {
            "Type": "application",
            "LoadBalancerAttributes": Match.array_with(
                [
                    {"Key": "idle_timeout.timeout_seconds", "Value": "300"},
                ]
            ),
        },
    )


def test_cdk_eventbridge_rule_and_dlq(synthesized_cdk_template):
    """Verify EventBridge 1-minute schedule, dead-letter queue, and retry policy."""
    # SQS Dead Letter Queue
    synthesized_cdk_template.has_resource_properties(
        "AWS::SQS::Queue",
        {
            "QueueName": "CareLoopTickRunnerDLQ",
            "MessageRetentionPeriod": 1209600,
        },
    )

    # EventBridge Rule
    synthesized_cdk_template.has_resource_properties(
        "AWS::Events::Rule",
        {
            "ScheduleExpression": "rate(1 minute)",
            "Targets": Match.array_with(
                [
                    Match.object_like(
                        {
                            "DeadLetterConfig": Match.any_value(),
                            "RetryPolicy": {
                                "MaximumEventAgeInSeconds": 300,
                                "MaximumRetryAttempts": 2,
                            },
                        }
                    )
                ]
            ),
        },
    )


def test_cdk_outputs_defined(synthesized_cdk_template):
    """Verify infrastructure outputs export endpoints without fabrication."""
    template_json = synthesized_cdk_template.to_json()
    outputs = template_json.get("Outputs", {})
    assert "PublicMcpEndpoint" in outputs
    assert "SimulatorUrl" in outputs
    assert "HealthCheckUrl" in outputs
    assert "DynamoDbTableName" in outputs
    assert "DynamoDbTableArn" in outputs
    assert "SnsTopicArn" in outputs
    assert "EventBridgeRuleName" in outputs
    assert "TickDLQArn" in outputs
    assert "TickDLQUrl" in outputs


# =============================================================================
# 3. AWS SAM Template Specification & Validation Tests
# =============================================================================


class _CFTag:
    def __init__(self, tag, val):
        self.tag = tag
        self.val = val


def _cfn_constructor(loader, tag_suffix, node):
    if isinstance(node, yaml.ScalarNode):
        return _CFTag(tag_suffix, loader.construct_scalar(node))
    elif isinstance(node, yaml.SequenceNode):
        return _CFTag(tag_suffix, loader.construct_sequence(node))
    elif isinstance(node, yaml.MappingNode):
        return _CFTag(tag_suffix, loader.construct_mapping(node))


@pytest.fixture(scope="module")
def parsed_sam_template():
    """Parses SAM template.yaml with PyYAML CloudFormation constructors."""
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    template_path = os.path.join(root, "template.yaml")
    assert os.path.exists(template_path)

    cfn_loader = yaml.SafeLoader
    cfn_loader.add_multi_constructor("!", _cfn_constructor)
    with open(template_path, "r", encoding="utf-8") as f:
        data = yaml.load(f, Loader=cfn_loader)
    return data


def test_sam_template_structure_and_resources(parsed_sam_template):
    """Verify SAM template contains all required resources."""
    resources = parsed_sam_template.get("Resources", {})
    assert "CareLoopTable" in resources
    assert "CareLoopTopic" in resources
    assert "CareLoopTaskRole" in resources
    assert "CareLoopExecutionRole" in resources
    assert "CareLoopCluster" in resources
    assert "CareLoopALB" in resources
    assert "CareLoopTargetGroup" in resources
    assert "CareLoopTaskDefinition" in resources
    assert "CareLoopService" in resources
    assert "CareLoopTickDLQ" in resources
    assert "CareLoopTickFunction" in resources


def test_sam_dynamodb_configuration(parsed_sam_template):
    """Verify DynamoDB schema, SSE, PITR, and TTL in SAM template."""
    table_props = parsed_sam_template["Resources"]["CareLoopTable"]["Properties"]
    assert table_props["BillingMode"] == "PAY_PER_REQUEST"
    assert table_props["SSESpecification"]["SSEEnabled"] is True
    assert table_props["PointInTimeRecoverySpecification"]["PointInTimeRecoveryEnabled"] is True
    assert table_props["TimeToLiveSpecification"]["AttributeName"] == "TTL"
    assert table_props["TimeToLiveSpecification"]["Enabled"] is True


def test_sam_tick_function_and_dlq(parsed_sam_template):
    """Verify SAM tick function has EventBridge schedule, DLQ, and retry policy."""
    func_props = parsed_sam_template["Resources"]["CareLoopTickFunction"]["Properties"]
    assert func_props["Runtime"] == "python3.11"
    assert func_props["Timeout"] == 20

    events = func_props.get("Events", {})
    minute_sched = events.get("MinuteSchedule", {}).get("Properties", {})
    sched_expr = minute_sched.get("ScheduleExpression") or minute_sched.get("Schedule")
    assert sched_expr == "rate(1 minute)"
    dlq_config = minute_sched.get("DeadLetterConfig", {})
    assert dlq_config.get("Arn") is not None or dlq_config.get("Type") == "SQS"
    assert minute_sched.get("RetryPolicy", {}).get("MaximumRetryAttempts") == 2
    assert minute_sched.get("RetryPolicy", {}).get("MaximumEventAgeInSeconds") == 300


def test_sam_outputs_complete(parsed_sam_template):
    """Verify all required CloudFormation outputs are declared in SAM template."""
    outputs = parsed_sam_template.get("Outputs", {})
    required_outputs = [
        "PublicMcpEndpoint",
        "SimulatorUrl",
        "HealthCheckUrl",
        "DynamoDbTableName",
        "DynamoDbTableArn",
        "SnsTopicArn",
        "TickDLQArn",
        "TickDLQUrl",
    ]
    for out in required_outputs:
        assert out in outputs, f"Missing required output: {out}"


def test_dockerfile_specification():
    """Verify Dockerfile uses Python 3.11, exposes 8000, has health check, and runs careloop.server."""
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    dockerfile_path = os.path.join(root, "Dockerfile")
    assert os.path.exists(dockerfile_path)

    with open(dockerfile_path, "r", encoding="utf-8") as f:
        content = f.read()

    assert "FROM python:3.11-slim" in content
    assert "EXPOSE 8000" in content
    assert "HEALTHCHECK" in content
    assert "careloop.server" in content
