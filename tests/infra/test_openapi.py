"""El contrato OpenAPI y las rutas de CDK deben describir la misma API (RF-15)."""

from pathlib import Path

import aws_cdk as cdk
import pytest
import yaml
from aws_cdk.assertions import Template

from infra.app_stack import AppStack

OPENAPI = Path(__file__).resolve().parents[2] / "docs" / "openapi.yaml"


@pytest.fixture(scope="module")
def cdk_routes(tmp_path_factory) -> set[tuple[str, str]]:
    app = cdk.App(outdir=str(tmp_path_factory.mktemp("openapi")))
    stack = AppStack(app, "EstadisticasAppStack", env=cdk.Environment(region="us-east-1"))
    routes = Template.from_stack(stack).find_resources("AWS::ApiGatewayV2::Route")
    return {tuple(route["Properties"]["RouteKey"].split(" ", 1)) for route in routes.values()}


def test_openapi_documents_exactly_the_routes_deployed_by_cdk(cdk_routes):
    spec = yaml.safe_load(OPENAPI.read_text(encoding="utf-8"))
    documented = {
        (method.upper(), path)
        for path, operations in spec["paths"].items()
        for method in operations
    }

    assert documented == cdk_routes


def test_openapi_has_responses_for_every_operation():
    spec = yaml.safe_load(OPENAPI.read_text(encoding="utf-8"))

    assert spec["openapi"].startswith("3.")
    for operations in spec["paths"].values():
        for operation in operations.values():
            assert operation["responses"], operation
