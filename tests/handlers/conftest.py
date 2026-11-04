"""Ambiente de AWS simulado con moto para las pruebas de los handlers."""

from types import SimpleNamespace

import boto3
import pytest
from helpers import BUCKET, MATCHES_TABLE, QUEUE_NAME, REGION, STANDINGS_TABLE
from moto import mock_aws

from estadisticas.aws import reset_clients
from estadisticas.config import DAILY_LIMIT_PARAM, clear_parameter_cache


@pytest.fixture
def aws(monkeypatch):
    """Bucket, tablas, cola y parámetro de cuota simulados. Cada prueba arranca limpia."""
    for name, value in (
        ("AWS_ACCESS_KEY_ID", "testing"),
        ("AWS_SECRET_ACCESS_KEY", "testing"),
        ("AWS_SESSION_TOKEN", "testing"),
        ("AWS_DEFAULT_REGION", REGION),
    ):
        monkeypatch.setenv(name, value)
    with mock_aws():
        reset_clients()
        clear_parameter_cache()
        s3 = boto3.client("s3", region_name=REGION)
        s3.create_bucket(Bucket=BUCKET)
        dynamodb = boto3.client("dynamodb", region_name=REGION)
        for table in (MATCHES_TABLE, STANDINGS_TABLE):
            dynamodb.create_table(
                TableName=table,
                KeySchema=[
                    {"AttributeName": "pk", "KeyType": "HASH"},
                    {"AttributeName": "sk", "KeyType": "RANGE"},
                ],
                AttributeDefinitions=[
                    {"AttributeName": "pk", "AttributeType": "S"},
                    {"AttributeName": "sk", "AttributeType": "S"},
                ],
                BillingMode="PAY_PER_REQUEST",
            )
        sqs = boto3.client("sqs", region_name=REGION)
        queue_url = sqs.create_queue(QueueName=QUEUE_NAME)["QueueUrl"]
        ssm = boto3.client("ssm", region_name=REGION)
        ssm.put_parameter(Name=DAILY_LIMIT_PARAM, Value="20", Type="String")
        monkeypatch.setenv("MATCHES_TABLE", MATCHES_TABLE)
        monkeypatch.setenv("STANDINGS_TABLE", STANDINGS_TABLE)
        monkeypatch.setenv("UPLOADS_BUCKET", BUCKET)
        monkeypatch.setenv("SUMMARY_QUEUE_URL", queue_url)
        resources = boto3.resource("dynamodb", region_name=REGION)
        yield SimpleNamespace(
            s3=s3,
            sqs=sqs,
            ssm=ssm,
            queue_url=queue_url,
            matches=resources.Table(MATCHES_TABLE),
            standings=resources.Table(STANDINGS_TABLE),
        )
        reset_clients()
        clear_parameter_cache()
