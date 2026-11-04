"""Punto de entrada de CDK: crea los dos stacks del proyecto (ERS sección 11.3).

Contexto requerido: `-c github_repo=owner/repo`. Opcional: `-c alert_email=...`.
"""

import aws_cdk as cdk

from infra.app_stack import AppStack
from infra.base_stack import BaseStack


def main() -> None:
    app = cdk.App()
    github_repo = app.node.try_get_context("github_repo")
    if not github_repo:
        raise ValueError("Falta el contexto github_repo, por ejemplo: -c github_repo=owner/repo")
    alert_email = app.node.try_get_context("alert_email")
    env = cdk.Environment(region="us-east-1")

    BaseStack(
        app,
        "EstadisticasBaseStack",
        github_repo=github_repo,
        alert_email=alert_email,
        env=env,
    )
    AppStack(app, "EstadisticasAppStack", alert_email=alert_email, env=env)
    app.synth()


if __name__ == "__main__":
    main()
