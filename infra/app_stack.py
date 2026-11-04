"""Stack de aplicación: bucket, tablas, colas, funciones, API, alarmas y parámetros (ERS 6 y 10)."""

from pathlib import Path
from typing import Any

from aws_cdk import CfnOutput, Duration, RemovalPolicy, Stack, Tags
from aws_cdk import aws_apigatewayv2 as apigwv2
from aws_cdk import aws_apigatewayv2_authorizers as authorizers
from aws_cdk import aws_apigatewayv2_integrations as integrations
from aws_cdk import aws_cloudwatch as cloudwatch
from aws_cdk import aws_cloudwatch_actions as cw_actions
from aws_cdk import aws_dynamodb as dynamodb
from aws_cdk import aws_events as events
from aws_cdk import aws_events_targets as targets
from aws_cdk import aws_iam as iam
from aws_cdk import aws_lambda as _lambda
from aws_cdk import aws_lambda_destinations as destinations
from aws_cdk import aws_lambda_event_sources as event_sources
from aws_cdk import aws_logs as logs
from aws_cdk import aws_s3 as s3
from aws_cdk import aws_s3_notifications as s3_notifications
from aws_cdk import aws_sns as sns
from aws_cdk import aws_sns_subscriptions as subscriptions
from aws_cdk import aws_sqs as sqs
from aws_cdk import aws_ssm as ssm
from constructs import Construct

PREFIX = "estadisticas"
SOURCE_DIR = Path(__file__).resolve().parents[1] / "src"
DAILY_LIMIT_PARAM = "/estadisticas/upload/daily-limit"
SUMMARY_MODE_PARAM = "/estadisticas/summary/mode"
DAILY_STANDINGS_CRON = "cron(0 6 * * ? *)"  # 06:00 UTC = 03:00 en Argentina.


class AppStack(Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        alert_email: str | None = None,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)
        Tags.of(self).add("project", "estadisticas-serverless")
        Tags.of(self).add("env", "demo")

        bucket = self._uploads_bucket()
        matches = self._table("MatchesTable", f"{PREFIX}-matches", ttl="expires_at")
        standings = self._table("StandingsTable", f"{PREFIX}-standings")
        dlq = sqs.Queue(
            self,
            "DeadLetterQueue",
            queue_name=f"{PREFIX}-dlq",
            retention_period=Duration.days(14),
            encryption=sqs.QueueEncryption.SQS_MANAGED,
        )
        summary_queue = sqs.Queue(
            self,
            "SummaryQueue",
            queue_name=f"{PREFIX}-summary",
            visibility_timeout=Duration.seconds(180),
            retention_period=Duration.days(4),
            encryption=sqs.QueueEncryption.SQS_MANAGED,
            dead_letter_queue=sqs.DeadLetterQueue(max_receive_count=3, queue=dlq),
        )
        daily_limit = ssm.StringParameter(
            self,
            "DailyLimitParameter",
            parameter_name=DAILY_LIMIT_PARAM,
            string_value="20",
        )
        ssm.StringParameter(
            self,
            "SummaryModeParameter",
            parameter_name=SUMMARY_MODE_PARAM,
            string_value="template",
        )

        environment = {
            "MATCHES_TABLE": matches.table_name,
            "STANDINGS_TABLE": standings.table_name,
            "UPLOADS_BUCKET": bucket.bucket_name,
            "SUMMARY_QUEUE_URL": summary_queue.queue_url,
        }
        upload_fn = self._function(
            "upload-url",
            "UploadUrl",
            "estadisticas.handlers.api_uploads.upload_url_handler",
            timeout=10,
            environment=environment,
            statements=[
                _table_statement(matches.table_arn, ["dynamodb:UpdateItem"], ["SYSTEM#QUOTA"]),
                iam.PolicyStatement(
                    actions=["s3:PutObject"],
                    resources=[bucket.arn_for_objects("incoming/*")],
                ),
                iam.PolicyStatement(
                    actions=["ssm:GetParameter"], resources=[daily_limit.parameter_arn]
                ),
            ],
        )
        matches_fn = self._function(
            "matches",
            "Matches",
            "estadisticas.handlers.api_matches.matches_handler",
            timeout=10,
            environment=environment,
            statements=[_table_statement(matches.table_arn, ["dynamodb:Query"], ["SEASON#*"])],
        )
        standings_fn = self._function(
            "standings",
            "Standings",
            "estadisticas.handlers.api_standings.standings_handler",
            timeout=10,
            environment=environment,
            statements=[
                iam.PolicyStatement(actions=["dynamodb:Query"], resources=[standings.table_arn])
            ],
        )
        ingest_fn = self._function(
            "ingest",
            "Ingest",
            "estadisticas.handlers.ingest.ingest_handler",
            timeout=60,
            environment=environment,
            reserved_concurrency=2,
            statements=[
                iam.PolicyStatement(
                    actions=["s3:GetObject", "s3:DeleteObject"],
                    resources=[bucket.arn_for_objects("incoming/*")],
                ),
                iam.PolicyStatement(
                    actions=["s3:PutObject"],
                    resources=[
                        bucket.arn_for_objects("processed/*"),
                        bucket.arn_for_objects("rejected/*"),
                        bucket.arn_for_objects("reports/*"),
                    ],
                ),
                _table_statement(
                    matches.table_arn,
                    ["dynamodb:GetItem", "dynamodb:UpdateItem", "dynamodb:PutItem"],
                    ["SEASON#*", "SYSTEM#SEASONS"],
                ),
                iam.PolicyStatement(
                    actions=["sqs:SendMessage"],
                    resources=[summary_queue.queue_arn, dlq.queue_arn],
                ),
            ],
        )
        summary_fn = self._function(
            "summary",
            "Summary",
            "estadisticas.handlers.summary.summary_handler",
            timeout=30,
            environment=environment,
            statements=[
                _table_statement(
                    matches.table_arn,
                    ["dynamodb:GetItem", "dynamodb:UpdateItem"],
                    ["SEASON#*"],
                ),
            ],
        )
        recalc_fn = self._function(
            "standings-recalc",
            "StandingsRecalc",
            "estadisticas.handlers.standings_recalc.standings_recalc_handler",
            timeout=60,
            environment=environment,
            reserved_concurrency=1,
            statements=[
                _table_statement(
                    matches.table_arn, ["dynamodb:Query"], ["SEASON#*", "SYSTEM#SEASONS"]
                ),
                iam.PolicyStatement(
                    actions=["dynamodb:Query", "dynamodb:BatchWriteItem"],
                    resources=[standings.table_arn],
                ),
                iam.PolicyStatement(actions=["sqs:SendMessage"], resources=[dlq.queue_arn]),
            ],
        )

        # Las funciones que disparan los eventos reintentan y, si fallan del todo, van a la DLQ.
        for fn in (ingest_fn, recalc_fn):
            fn.configure_async_invoke(
                retry_attempts=2,
                max_event_age=Duration.hours(1),
                on_failure=destinations.SqsDestination(dlq),
            )
        bucket.add_event_notification(
            s3.EventType.OBJECT_CREATED,
            s3_notifications.LambdaDestination(ingest_fn),
            s3.NotificationKeyFilter(prefix="incoming/", suffix=".csv"),
        )
        summary_fn.add_event_source(
            event_sources.SqsEventSource(summary_queue, batch_size=1, max_concurrency=2)
        )
        events.Rule(
            self,
            "DailyStandingsRule",
            rule_name=f"{PREFIX}-daily-standings",
            schedule=events.Schedule.expression(DAILY_STANDINGS_CRON),
            targets=[targets.LambdaFunction(recalc_fn)],
        )

        api = apigwv2.HttpApi(
            self,
            "HttpApi",
            api_name=f"{PREFIX}-api",
            create_default_stage=False,
        )
        apigwv2.HttpStage(
            self,
            "DefaultStage",
            http_api=api,
            stage_name="$default",
            auto_deploy=True,
            throttle=apigwv2.ThrottleSettings(rate_limit=5, burst_limit=10),
        )
        api.add_routes(
            path="/partidos",
            methods=[apigwv2.HttpMethod.GET],
            integration=integrations.HttpLambdaIntegration("MatchesIntegration", matches_fn),
        )
        api.add_routes(
            path="/tabla",
            methods=[apigwv2.HttpMethod.GET],
            integration=integrations.HttpLambdaIntegration("StandingsIntegration", standings_fn),
        )
        api.add_routes(
            path="/uploads",
            methods=[apigwv2.HttpMethod.POST],
            integration=integrations.HttpLambdaIntegration("UploadsIntegration", upload_fn),
            authorizer=authorizers.HttpIamAuthorizer(),
        )

        topic = sns.Topic(self, "AlertsTopic", topic_name=f"{PREFIX}-alerts")
        if alert_email:
            topic.add_subscription(subscriptions.EmailSubscription(alert_email))
        alert = cw_actions.SnsAction(topic)
        self._alarm(
            "DlqVisibleAlarm",
            f"{PREFIX}-dlq-visible",
            dlq.metric_approximate_number_of_messages_visible(period=Duration.minutes(1)),
            threshold=1,
        ).add_alarm_action(alert)
        for name, fn in (
            ("upload-url", upload_fn),
            ("matches", matches_fn),
            ("standings", standings_fn),
            ("ingest", ingest_fn),
            ("summary", summary_fn),
            ("standings-recalc", recalc_fn),
        ):
            self._alarm(
                f"{_title(name)}ErrorsAlarm",
                f"{PREFIX}-{name}-errors",
                fn.metric_errors(period=Duration.minutes(5)),
                threshold=1,
            ).add_alarm_action(alert)
        self._alarm(
            "Api5xxAlarm",
            f"{PREFIX}-api-5xx",
            cloudwatch.Metric(
                namespace="AWS/ApiGateway",
                metric_name="5xx",
                dimensions_map={"ApiId": api.api_id},
                statistic="Sum",
                period=Duration.minutes(5),
            ),
            threshold=5,
        ).add_alarm_action(alert)

        CfnOutput(self, "ApiUrl", value=api.url or "")
        CfnOutput(self, "UploadsBucketName", value=bucket.bucket_name)
        CfnOutput(self, "SummaryQueueUrl", value=summary_queue.queue_url)

    def _uploads_bucket(self) -> s3.Bucket:
        return s3.Bucket(
            self,
            "UploadsBucket",
            bucket_name=f"{PREFIX}-uploads-{self.account}-{self.region}",
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            enforce_ssl=True,
            encryption=s3.BucketEncryption.S3_MANAGED,
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
            lifecycle_rules=[
                s3.LifecycleRule(prefix="incoming/", expiration=Duration.days(1)),
                s3.LifecycleRule(prefix="processed/", expiration=Duration.days(30)),
                s3.LifecycleRule(prefix="rejected/", expiration=Duration.days(30)),
                s3.LifecycleRule(prefix="reports/", expiration=Duration.days(30)),
            ],
        )

    def _table(self, construct_id: str, name: str, ttl: str | None = None) -> dynamodb.Table:
        return dynamodb.Table(
            self,
            construct_id,
            table_name=name,
            partition_key=dynamodb.Attribute(name="pk", type=dynamodb.AttributeType.STRING),
            sort_key=dynamodb.Attribute(name="sk", type=dynamodb.AttributeType.STRING),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            time_to_live_attribute=ttl,
            removal_policy=RemovalPolicy.DESTROY,
        )

    def _function(
        self,
        name: str,
        title: str,
        handler: str,
        *,
        timeout: int,
        environment: dict[str, Any],
        statements: list[iam.PolicyStatement],
        reserved_concurrency: int | None = None,
    ) -> _lambda.Function:
        log_group = logs.LogGroup(
            self,
            f"{title}Logs",
            log_group_name=f"/aws/lambda/{PREFIX}-{name}",
            retention=logs.RetentionDays.ONE_WEEK,
            removal_policy=RemovalPolicy.DESTROY,
        )
        role = iam.Role(
            self,
            f"{title}Role",
            role_name=f"{PREFIX}-{name}-role",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
        )
        role.add_to_policy(
            iam.PolicyStatement(
                actions=["logs:CreateLogStream", "logs:PutLogEvents"],
                resources=[log_group.log_group_arn],
            )
        )
        for statement in statements:
            role.add_to_policy(statement)
        return _lambda.Function(
            self,
            f"{title}Function",
            function_name=f"{PREFIX}-{name}",
            runtime=_lambda.Runtime.PYTHON_3_12,
            handler=handler,
            code=_lambda.Code.from_asset(str(SOURCE_DIR), exclude=["**/__pycache__"]),
            memory_size=256,
            timeout=Duration.seconds(timeout),
            role=role,
            environment=environment,
            log_group=log_group,
            reserved_concurrent_executions=reserved_concurrency,
        )

    def _alarm(
        self,
        construct_id: str,
        name: str,
        metric: cloudwatch.Metric,
        *,
        threshold: int,
    ) -> cloudwatch.Alarm:
        return cloudwatch.Alarm(
            self,
            construct_id,
            alarm_name=name,
            metric=metric,
            threshold=threshold,
            evaluation_periods=1,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
            treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING,
        )


def _table_statement(
    table_arn: str, actions: list[str], leading_keys: list[str]
) -> iam.PolicyStatement:
    """Permite acciones solo sobre las claves de partición indicadas (dynamodb:LeadingKeys)."""
    return iam.PolicyStatement(
        actions=actions,
        resources=[table_arn],
        conditions={"ForAllValues:StringLike": {"dynamodb:LeadingKeys": leading_keys}},
    )


def _title(name: str) -> str:
    return "".join(part.capitalize() for part in name.split("-"))
