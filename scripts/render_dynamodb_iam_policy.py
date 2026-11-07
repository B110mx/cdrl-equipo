"""Renderiza la política DynamoDB de un rol a partir de ARN de entorno."""

import argparse
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.access_control import load_policy


ACTION_MAP = {
    ("events", "read"): ("dynamodb:Query",),
    ("events", "write"): ("dynamodb:PutItem", "dynamodb:TransactWriteItems"),
    ("events", "administer"): ("dynamodb:DeleteItem",),
    ("audit", "append_audit"): ("dynamodb:PutItem",),
    ("audit", "query_audit"): ("dynamodb:GetItem", "dynamodb:Query"),
}
TABLE_ARN_PATTERN = re.compile(
    r"^arn:aws(?:-[a-z]+)?:dynamodb:[a-z0-9-]+:\d{12}:table/[A-Za-z0-9_.-]+$")


def render_policy(role, environment=None):
    environment = environment or os.environ
    policy = load_policy()
    if role not in policy["roles"]:
        raise ValueError("unknown access role")

    statements = []
    for collection, operations in policy["roles"][role].items():
        if not operations:
            continue
        table_env = policy["collections"][collection]["arn_env"]
        table_arn = environment.get(table_env, "")
        if not table_arn or not TABLE_ARN_PATTERN.fullmatch(table_arn):
            raise ValueError(f"{table_env} must contain a table ARN")
        for operation in operations:
            actions = ACTION_MAP.get((collection, operation))
            if actions is None:
                raise ValueError(
                    f"no AWS IAM action mapping for {collection}/{operation}")
            resources = [table_arn]
            if "dynamodb:Query" in actions:
                resources.append(f"{table_arn}/index/*")
            statements.append({
                "Effect": "Allow",
                "Action": list(actions),
                "Resource": resources,
            })

    return {
        "Version": "2012-10-17",
        "Statement": statements,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--role", required=True, choices=load_policy()["roles"])
    args = parser.parse_args()
    try:
        rendered = render_policy(args.role)
    except ValueError as error:
        print(str(error), file=sys.stderr)
        return 2
    print(json.dumps(rendered, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
