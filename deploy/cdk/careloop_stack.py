"""
AWS CDK Stack for CareLoop: Alexa+ Elder Care MCP Server.

Provisions:
1. Amazon DynamoDB: Single-table schema with encryption at rest and point-in-time recovery.
2. Amazon SNS: Caregiver alert topic with server-side encryption.
3. IAM Roles: Principle of least-privilege for DynamoDB, SNS, Bedrock (Claude), and CloudWatch.
4. AWS ECS Fargate + Application Load Balancer: High-availability container execution natively
   supporting persistent Streamable HTTP (MCP spec 2025-11-25) without 29s API Gateway timeouts.
5. Amazon EventBridge: Scheduled rule executing an autonomous tick Lambda every minute.
"""

from __future__ import annotations

import os
from aws_cdk import (
    Stack,
    Duration,
    CfnOutput,
    RemovalPolicy,
    aws_ec2 as ec2,
    aws_ecs as ecs,
    aws_ecs_patterns as ecs_patterns,
    aws_dynamodb as dynamodb,
    aws_sns as sns,
    aws_kms as kms,
    aws_iam as iam,
    aws_events as events,
    aws_events_targets as targets,
    aws_lambda as lambda_,
    aws_logs as logs,
)
from constructs import Construct


class CareLoopStack(Stack):
    """CareLoop AWS Cloud Infrastructure Stack."""

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # ---------------------------------------------------------------------
        # 1. DynamoDB: Single-Table Architecture with Encryption at Rest
        # ---------------------------------------------------------------------
        table = dynamodb.Table(
            self,
            "CareLoopDataTable",
            table_name="CareLoopData",
            partition_key=dynamodb.Attribute(
                name="PK",
                type=dynamodb.AttributeType.STRING,
            ),
            sort_key=dynamodb.Attribute(
                name="SK",
                type=dynamodb.AttributeType.STRING,
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            encryption=dynamodb.TableEncryption.AWS_MANAGED,
            point_in_time_recovery=True,
            removal_policy=RemovalPolicy.DESTROY,  # Easily cleanable in hackathon/dev teardown
        )

        # ---------------------------------------------------------------------
        # 2. Amazon SNS: Family Caregiver Alert Topic
        # ---------------------------------------------------------------------
        sns_key = kms.Alias.from_alias_name(self, "SnsDefaultKey", "alias/aws/sns")
        alerts_topic = sns.Topic(
            self,
            "CareLoopAlertsTopic",
            topic_name="CareLoopAlertsTopic",
            display_name="CareLoop Family Emergency & Routine Alerts",
            master_key=sns_key,
        )

        # ---------------------------------------------------------------------
        # 3. VPC & ECS Cluster for Streamable HTTP Fargate Service
        # ---------------------------------------------------------------------
        # Use public subnets with direct egress to eliminate NAT Gateway charges
        vpc = ec2.Vpc(
            self,
            "CareLoopVpc",
            max_azs=2,
            nat_gateways=0,
            subnet_configuration=[
                ec2.SubnetConfiguration(
                    name="PublicSubnet",
                    subnet_type=ec2.SubnetType.PUBLIC,
                    cidr_mask=24,
                )
            ],
        )

        cluster = ecs.Cluster(
            self,
            "CareLoopCluster",
            vpc=vpc,
            cluster_name="CareLoopCluster",
        )

        # ---------------------------------------------------------------------
        # 4. IAM Roles: Strict Least-Privilege Access
        # ---------------------------------------------------------------------
        task_role = iam.Role(
            self,
            "CareLoopTaskRole",
            assumed_by=iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
            description="Least privilege application role for CareLoop FastMCP server",
        )

        # Grant DynamoDB read/write exclusively to the CareLoopData table
        table.grant_read_write_data(task_role)

        # Grant SNS publish exclusively to the CareLoopAlertsTopic
        alerts_topic.grant_publish(task_role)

        # Grant Bedrock Claude Foundation Model invocation strictly for summaries/Q&A
        task_role.add_to_policy(
            iam.PolicyStatement(
                sid="BedrockConverseClaudeAccess",
                effect=iam.Effect.ALLOW,
                actions=[
                    "bedrock:InvokeModel",
                    "bedrock:InvokeModelWithResponseStream",
                ],
                resources=[
                    f"arn:aws:bedrock:{self.region}::foundation-model/anthropic.claude-3-haiku-20240307-v1:0",
                    f"arn:aws:bedrock:{self.region}::foundation-model/anthropic.claude-3-5-sonnet-20240620-v1:0",
                    f"arn:aws:bedrock:{self.region}::foundation-model/anthropic.claude-*",
                ],
            )
        )

        # ---------------------------------------------------------------------
        # 5. ECS Fargate Application Load Balanced Service
        # ---------------------------------------------------------------------
        root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))

        fargate_service = ecs_patterns.ApplicationLoadBalancedFargateService(
            self,
            "CareLoopFargateService",
            cluster=cluster,
            service_name="CareLoopMcpServer",
            cpu=512,
            memory_limit_mib=1024,
            desired_count=1,
            assign_public_ip=True,
            public_load_balancer=True,
            task_image_options=ecs_patterns.ApplicationLoadBalancedTaskImageOptions(
                image=ecs.ContainerImage.from_asset(root_dir),
                container_port=8000,
                container_name="careloop-mcp",
                task_role=task_role,
                log_driver=ecs.LogDrivers.aws_logs(
                    stream_prefix="careloop",
                    log_retention=logs.RetentionDays.ONE_MONTH,
                ),
                environment={
                    "PYTHONUNBUFFERED": "1",
                    "MCP_HOST": "0.0.0.0",
                    "MCP_PORT": "8000",
                    "STORAGE_BACKEND": "dynamodb",
                    "DYNAMODB_TABLE_NAME": table.table_name,
                    "NOTIFIER_TYPE": "sns",
                    "SNS_TOPIC_ARN": alerts_topic.topic_arn,
                    "AWS_REGION": self.region,
                    "BEDROCK_MODEL_ID": "anthropic.claude-3-haiku-20240307-v1:0",
                    "CLOCK_MODE": "system",
                    "ESCALATION_TICK_INTERVAL_SECONDS": "60.0",
                },
            ),
        )

        # Configure Target Group Health Check and Idle Timeout for Streamable HTTP
        target_group = fargate_service.target_group
        target_group.configure_health_check(
            path="/health",
            port="8000",
            healthy_http_codes="200",
            interval=Duration.seconds(30),
            timeout=Duration.seconds(5),
            healthy_threshold_count=2,
            unhealthy_threshold_count=3,
        )
        target_group.set_attribute("deregistration_delay.timeout_seconds", "15")

        # Set ALB idle timeout to 300s to support long-lived Streamable HTTP streaming connections
        fargate_service.load_balancer.set_attribute(
            "idle_timeout.timeout_seconds", "300"
        )

        # ---------------------------------------------------------------------
        # 6. EventBridge Scheduled Rule: Call tick every minute
        # ---------------------------------------------------------------------
        lambda_dir = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "../tick_lambda")
        )

        tick_lambda = lambda_.Function(
            self,
            "CareLoopTickLambda",
            function_name="CareLoopTickRunner",
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler="tick_handler.handler",
            code=lambda_.Code.from_asset(lambda_dir),
            timeout=Duration.seconds(20),
            memory_size=128,
            log_retention=logs.RetentionDays.ONE_WEEK,
            environment={
                "MCP_SERVER_URL": f"http://{fargate_service.load_balancer.load_balancer_dns_name}",
            },
        )

        # Trigger tick every minute via EventBridge
        minute_rule = events.Rule(
            self,
            "CareLoopMinuteTickRule",
            rule_name="CareLoopRoutineMinuteTick",
            description="Autonomous minute tick triggering CareLoop routine health checks",
            schedule=events.Schedule.rate(Duration.minutes(1)),
        )
        minute_rule.add_target(targets.LambdaFunction(tick_lambda))

        # ---------------------------------------------------------------------
        # 7. Stack Outputs
        # ---------------------------------------------------------------------
        alb_dns = fargate_service.load_balancer.load_balancer_dns_name

        CfnOutput(
            self,
            "PublicMcpEndpoint",
            value=f"http://{alb_dns}/mcp",
            description="Streamable HTTP MCP Server Endpoint (MCP spec 2025-11-25) for Alexa+ and MCP clients",
        )

        CfnOutput(
            self,
            "SimulatorUrl",
            value=f"http://{alb_dns}/simulator",
            description="Web Simulator UI with ambient voice assistant and live MCP inspector",
        )

        CfnOutput(
            self,
            "HealthCheckUrl",
            value=f"http://{alb_dns}/health",
            description="Application Load Balancer health check endpoint",
        )

        CfnOutput(
            self,
            "DynamoDbTableName",
            value=table.table_name,
            description="Encrypted DynamoDB single-table name",
        )

        CfnOutput(
            self,
            "SnsTopicArn",
            value=alerts_topic.topic_arn,
            description="Amazon SNS Alert Topic ARN for caregiver notifications",
        )
