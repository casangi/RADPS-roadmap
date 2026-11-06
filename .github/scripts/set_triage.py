#!/usr/bin/env python3
"""Set Program Increment to Triage on open issues newly added to an org project.

Only issues added on or after --since with no Program Increment are changed.
Needs a token in GH_TOKEN with write access to the organization project and
read access to the repositories.
"""
from __future__ import annotations

import argparse
import os

from export_project import graphql

FIELD = "Program Increment"
VALUE = "Triage"

ITEMS_QUERY = """
query($org: String!, $num: Int!, $field: String!, $cursor: String) {
  organization(login: $org) {
    projectV2(number: $num) {
      id
      field(name: $field) {
        ... on ProjectV2SingleSelectField { id options { id name } }
      }
      items(first: 100, after: $cursor) {
        pageInfo { hasNextPage endCursor }
        nodes {
          id isArchived createdAt
          fieldValueByName(name: $field) { __typename }
          content {
            __typename
            ... on Issue { state url }
          }
        }
      }
    }
  }
}
"""

SET_VALUE_MUTATION = """
mutation($project: ID!, $item: ID!, $field: ID!, $option: String!) {
  updateProjectV2ItemFieldValue(input: {
    projectId: $project, itemId: $item, fieldId: $field,
    value: {singleSelectOptionId: $option}
  }) {
    projectV2Item { id }
  }
}
"""


def fetch_project(org: str, num: int, token: str) -> tuple[dict, list]:
    items, cursor = [], None
    while True:
        variables = {"org": org, "num": num, "field": FIELD, "cursor": cursor}
        project = graphql(ITEMS_QUERY, variables, token)["organization"]["projectV2"]
        items.extend(project["items"]["nodes"])
        if not project["items"]["pageInfo"]["hasNextPage"]:
            return project, items
        cursor = project["items"]["pageInfo"]["endCursor"]


def needs_triage(item: dict, since: str) -> bool:
    content = item["content"] or {}
    return (content.get("__typename") == "Issue"
            and content["state"] == "OPEN"
            and not item["isArchived"]
            and item["fieldValueByName"] is None
            and item["createdAt"] >= since)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--org", required=True)
    parser.add_argument("--project", type=int, required=True)
    parser.add_argument("--since", required=True, help="YYYY-MM-DD")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    token = os.environ["GH_TOKEN"]
    project, items = fetch_project(args.org, args.project, token)
    field = project["field"]
    option = next(o["id"] for o in field["options"] if o["name"] == VALUE)
    for item in items:
        if needs_triage(item, args.since):
            print(item["content"]["url"])
            if not args.dry_run:
                graphql(SET_VALUE_MUTATION, {"project": project["id"], "item": item["id"],
                                             "field": field["id"], "option": option}, token)


if __name__ == "__main__":
    main()
