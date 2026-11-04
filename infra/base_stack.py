"""Stack base: proveedor OIDC de GitHub, rol de despliegue y presupuesto (ERS sección 10.6)."""

from aws_cdk import Stack
from aws_cdk import aws_budgets as budgets
from aws_cdk import aws_iam as iam
from constructs import Construct

GITHUB_HOST = "token.actions.githubusercontent.com"
DEPLOY_ROLE_NAME = "estadisticas-github-deploy"
BUDGET_NAME = "estadisticas-monthly-budget"


class BaseStack(Stack):
    """Se despliega una vez, a mano. Así destruir la aplicación no rompe el pipeline."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        github_repo: str,
        alert_email: str | None = None,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        provider = iam.OpenIdConnectProvider(
            self,
            "GitHubOidcProvider",
            url=f"https://{GITHUB_HOST}",
            client_ids=["sts.amazonaws.com"],
        )
        deploy_role = iam.Role(
            self,
            "GitHubDeployRole",
            role_name=DEPLOY_ROLE_NAME,
            assumed_by=iam.WebIdentityPrincipal(
                provider.open_id_connect_provider_arn,
                conditions={
                    "StringEquals": {f"{GITHUB_HOST}:aud": "sts.amazonaws.com"},
                    # Solo la rama main de este repositorio puede desplegar.
                    "StringLike": {f"{GITHUB_HOST}:sub": f"repo:{github_repo}:ref:refs/heads/main"},
                },
            ),
        )
        # Los roles de bootstrap de CDK son los únicos que el rol de despliegue puede asumir.
        deploy_role.add_to_policy(
            iam.PolicyStatement(
                actions=["sts:AssumeRole"],
                resources=[f"arn:{self.partition}:iam::{self.account}:role/cdk-hnb659fds-*"],
            )
        )

        if alert_email:
            budgets.CfnBudget(
                self,
                "MonthlyBudget",
                budget=budgets.CfnBudget.BudgetDataProperty(
                    budget_name=BUDGET_NAME,
                    budget_type="COST",
                    time_unit="MONTHLY",
                    budget_limit=budgets.CfnBudget.SpendProperty(amount=1, unit="USD"),
                ),
                notifications_with_subscribers=[
                    budgets.CfnBudget.NotificationWithSubscribersProperty(
                        notification=budgets.CfnBudget.NotificationProperty(
                            notification_type="ACTUAL",
                            comparison_operator="GREATER_THAN",
                            threshold=80,
                            threshold_type="PERCENTAGE",
                        ),
                        subscribers=[
                            budgets.CfnBudget.SubscriberProperty(
                                subscription_type="EMAIL",
                                address=alert_email,
                            )
                        ],
                    ),
                    budgets.CfnBudget.NotificationWithSubscribersProperty(
                        notification=budgets.CfnBudget.NotificationProperty(
                            notification_type="FORECASTED",
                            comparison_operator="GREATER_THAN",
                            threshold=100,
                            threshold_type="PERCENTAGE",
                        ),
                        subscribers=[
                            budgets.CfnBudget.SubscriberProperty(
                                subscription_type="EMAIL",
                                address=alert_email,
                            )
                        ],
                    ),
                ],
            )
