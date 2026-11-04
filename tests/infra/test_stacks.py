"""Pruebas de la plantilla de CDK: lo que el ERS prohíbe y lo que exige (secciones 10 y 11)."""

import json

import aws_cdk as cdk
import pytest
from aws_cdk.assertions import Match, Template

from infra.app_stack import AppStack
from infra.base_stack import BaseStack

ENV = cdk.Environment(account="123456789012", region="us-east-1")
FORBIDDEN_TYPES = {
    "AWS::EC2::Instance",
    "AWS::EC2::NatGateway",
    "AWS::EC2::VPC",
    "AWS::RDS::DBInstance",
    "AWS::RDS::DBCluster",
    "AWS::ElasticLoadBalancing::LoadBalancer",
    "AWS::ElasticLoadBalancingV2::LoadBalancer",
    "AWS::SecretsManager::Secret",
    "AWS::KMS::Key",
}
PROJECT_FUNCTIONS = {
    "estadisticas-upload-url",
    "estadisticas-matches",
    "estadisticas-standings",
    "estadisticas-ingest",
    "estadisticas-summary",
    "estadisticas-standings-recalc",
}


@pytest.fixture(scope="module")
def app_template(tmp_path_factory) -> Template:
    app = cdk.App(outdir=str(tmp_path_factory.mktemp("app")))
    stack = AppStack(app, "EstadisticasAppStack", alert_email="alertas@example.com", env=ENV)
    return Template.from_stack(stack)


@pytest.fixture(scope="module")
def base_template(tmp_path_factory) -> Template:
    app = cdk.App(outdir=str(tmp_path_factory.mktemp("base")))
    stack = BaseStack(
        app,
        "EstadisticasBaseStack",
        github_repo="owner/repo",
        alert_email="alertas@example.com",
        env=ENV,
    )
    return Template.from_stack(stack)


def test_app_stack_has_no_forbidden_resources(app_template):
    types = {resource["Type"] for resource in app_template.to_json()["Resources"].values()}

    assert not types & FORBIDDEN_TYPES


def test_every_log_group_keeps_logs_for_one_week(app_template):
    groups = app_template.find_resources("AWS::Logs::LogGroup")

    assert len(groups) == len(PROJECT_FUNCTIONS)
    assert all(group["Properties"]["RetentionInDays"] == 7 for group in groups.values())


def test_project_functions_have_the_names_from_the_ers(app_template):
    functions = app_template.find_resources("AWS::Lambda::Function")
    names = {
        function["Properties"]["FunctionName"]
        for function in functions.values()
        if "FunctionName" in function["Properties"]
    }

    assert names == PROJECT_FUNCTIONS


def test_reserved_concurrency_limits_ingest_and_recalc(app_template):
    app_template.has_resource_properties(
        "AWS::Lambda::Function",
        {"FunctionName": "estadisticas-ingest", "ReservedConcurrentExecutions": 2},
    )
    app_template.has_resource_properties(
        "AWS::Lambda::Function",
        {"FunctionName": "estadisticas-standings-recalc", "ReservedConcurrentExecutions": 1},
    )


def test_summary_queue_moves_messages_to_the_dlq_after_three_receives(app_template):
    app_template.has_resource_properties(
        "AWS::SQS::Queue",
        {
            "QueueName": "estadisticas-summary",
            "VisibilityTimeout": 180,
            "RedrivePolicy": {
                "maxReceiveCount": 3,
                "deadLetterTargetArn": Match.any_value(),
            },
        },
    )


def test_dlq_keeps_messages_for_fourteen_days_and_has_an_alarm(app_template):
    app_template.has_resource_properties(
        "AWS::SQS::Queue",
        {"QueueName": "estadisticas-dlq", "MessageRetentionPeriod": 14 * 24 * 3600},
    )
    app_template.has_resource_properties(
        "AWS::CloudWatch::Alarm",
        {
            "AlarmName": "estadisticas-dlq-visible",
            "Threshold": 1,
            "ComparisonOperator": "GreaterThanOrEqualToThreshold",
        },
    )


def test_uploads_bucket_blocks_public_access_and_requires_tls(app_template):
    app_template.has_resource_properties(
        "AWS::S3::Bucket",
        {
            "PublicAccessBlockConfiguration": {
                "BlockPublicAcls": True,
                "BlockPublicPolicy": True,
                "IgnorePublicAcls": True,
                "RestrictPublicBuckets": True,
            }
        },
    )
    policies = json.dumps(app_template.find_resources("AWS::S3::BucketPolicy"))
    assert "aws:SecureTransport" in policies


def test_incoming_csv_uploads_trigger_the_ingest_function(app_template):
    notifications = app_template.find_resources("Custom::S3BucketNotifications")
    configuration = next(iter(notifications.values()))["Properties"]["NotificationConfiguration"]
    lambda_config = configuration["LambdaFunctionConfigurations"][0]
    rules = {rule["Name"]: rule["Value"] for rule in lambda_config["Filter"]["Key"]["FilterRules"]}

    assert lambda_config["Events"] == ["s3:ObjectCreated:*"]
    assert rules == {"prefix": "incoming/", "suffix": ".csv"}


def test_standings_run_once_a_day_at_0600_utc(app_template):
    app_template.has_resource_properties(
        "AWS::Events::Rule",
        {"ScheduleExpression": "cron(0 6 * * ? *)"},
    )


def test_routes_match_the_contract_and_only_upload_requires_iam(app_template):
    routes = app_template.find_resources("AWS::ApiGatewayV2::Route")
    found = {
        route["Properties"]["RouteKey"]: route["Properties"].get("AuthorizationType", "NONE")
        for route in routes.values()
    }

    assert found == {
        "GET /partidos": "NONE",
        "GET /tabla": "NONE",
        "POST /uploads": "AWS_IAM",
    }


def test_api_stage_throttles_every_route(app_template):
    app_template.has_resource_properties(
        "AWS::ApiGatewayV2::Stage",
        {"DefaultRouteSettings": {"ThrottlingRateLimit": 5, "ThrottlingBurstLimit": 10}},
    )


def test_configuration_parameters_have_the_values_from_the_ers(app_template):
    app_template.has_resource_properties(
        "AWS::SSM::Parameter",
        {"Name": "/estadisticas/upload/daily-limit", "Value": "20"},
    )
    app_template.has_resource_properties(
        "AWS::SSM::Parameter",
        {"Name": "/estadisticas/summary/mode", "Value": "template"},
    )


def test_no_policy_statement_uses_a_wildcard_resource(app_template):
    for policy in app_template.find_resources("AWS::IAM::Policy").values():
        for statement in policy["Properties"]["PolicyDocument"]["Statement"]:
            assert statement.get("Resource") != "*", statement


def test_deploy_role_only_accepts_the_main_branch_of_the_repo(base_template):
    roles = base_template.find_resources("AWS::IAM::Role")
    deploy = next(
        role
        for role in roles.values()
        if role["Properties"].get("RoleName") == "estadisticas-github-deploy"
    )
    trust = json.dumps(deploy["Properties"]["AssumeRolePolicyDocument"])

    assert "repo:owner/repo:ref:refs/heads/main" in trust
    assert "sts.amazonaws.com" in trust
    assert "repo:owner/repo:*" not in trust


def test_base_stack_creates_no_access_keys(base_template):
    base_template.resource_count_is("AWS::IAM::AccessKey", 0)


def test_monthly_budget_is_one_dollar_with_alerts(base_template):
    base_template.has_resource_properties(
        "AWS::Budgets::Budget",
        {
            "Budget": {
                "BudgetName": "estadisticas-monthly-budget",
                "BudgetLimit": {"Amount": 1, "Unit": "USD"},
                "TimeUnit": "MONTHLY",
            }
        },
    )
