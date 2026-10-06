#!/usr/bin/env python3
"""Export an organization GitHub Project (v2) to flat, publicly readable files.

Writes into OUT_DIR (normally project33/ on the project-export branch):

  index.json        generated_at, project info, field names/options, current_pi,
                    pi_files (PI value -> CSV path), counts[PI][team] =
                    {total, done, by_status}
  summary.md        per-PI, per-team status tables
  pi/<PI>.csv       one row per item in that PI: team, status, kind, repo,
                    number, title, state, assignees, labels, updated_at,
                    closed_at, parent, url
  changes-log.csv   appended each run: one row per change to Status, Program
                    Increment, Team or open/closed state, plus items added to
                    or removed from the project
  state.json        snapshot used to compute the next run's changes

Only the Python standard library is used. Needs a token in GH_TOKEN that can
read the organization project (classic PAT with read:project + repo, or a
fine-grained token / GitHub App with organization "Projects: read" and
read access to the repositories).
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import os
import re
import sys
import urllib.error
import urllib.request
from collections import defaultdict

API_URL = os.environ.get("GITHUB_GRAPHQL_URL", "https://api.github.com/graphql")

FIELDS_QUERY = """
query($org: String!, $num: Int!) {
  organization(login: $org) {
    projectV2(number: $num) {
      id title url
      fields(first: 50) {
        nodes {
          __typename
          ... on ProjectV2FieldCommon { id name dataType }
          ... on ProjectV2SingleSelectField { options { id name } }
          ... on ProjectV2IterationField {
            configuration {
              duration startDay
              iterations { id title startDate duration }
              completedIterations { id title startDate duration }
            }
          }
        }
      }
    }
  }
}
"""

ITEMS_QUERY = """
query($org: String!, $num: Int!, $cursor: String) {
  organization(login: $org) {
    projectV2(number: $num) {
      items(first: 100, after: $cursor) {
        pageInfo { hasNextPage endCursor }
        nodes {
          id type isArchived updatedAt
          fieldValues(first: 30) {
            nodes {
              __typename
              ... on ProjectV2ItemFieldSingleSelectValue { name field { ... on ProjectV2FieldCommon { name } } }
              ... on ProjectV2ItemFieldIterationValue { title startDate duration field { ... on ProjectV2FieldCommon { name } } }
              ... on ProjectV2ItemFieldTextValue { text field { ... on ProjectV2FieldCommon { name } } }
              ... on ProjectV2ItemFieldNumberValue { number field { ... on ProjectV2FieldCommon { name } } }
              ... on ProjectV2ItemFieldDateValue { date field { ... on ProjectV2FieldCommon { name } } }
            }
          }
          content {
            __typename
            ... on DraftIssue { title updatedAt assignees(first: 10) { nodes { login } } }
            ... on Issue {
              number title state url updatedAt closedAt
              repository { nameWithOwner }
              assignees(first: 10) { nodes { login } }
              labels(first: 20) { nodes { name } }
              parent { number repository { nameWithOwner } }
            }
            ... on PullRequest {
              number title state url updatedAt closedAt
              repository { nameWithOwner }
              assignees(first: 10) { nodes { login } }
              labels(first: 20) { nodes { name } }
            }
          }
        }
      }
    }
  }
}
"""

CSV_COLUMNS = ["team", "status", "kind", "repo", "number", "title", "state",
               "assignees", "labels", "updated_at", "closed_at", "parent", "url"]
CHANGE_COLUMNS = ["changed_at", "repo", "number", "title", "field", "old", "new", "url"]
TRACKED = [("status", "Status"), ("pi", "Program Increment"), ("team", "Team"), ("state", "state")]
NO_TEAM = "(no team)"
NO_PI = "(no PI)"


def graphql(query: str, variables: dict, token: str) -> dict:
    body = json.dumps({"query": query, "variables": variables}).encode()
    req = urllib.request.Request(API_URL, data=body, method="POST", headers={
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "User-Agent": "radps-project-export",
    })
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            payload = json.load(resp)
    except urllib.error.HTTPError as exc:
        raise SystemExit(f"GraphQL HTTP {exc.code}: {exc.read().decode(errors='replace')[:500]}")
    if payload.get("errors"):
        raise SystemExit("GraphQL errors: " + json.dumps(payload["errors"])[:1000])
    return payload["data"]


def fetch_project(org: str, num: int, token: str, fetch=graphql) -> tuple[dict, list]:
    data = fetch(FIELDS_QUERY, {"org": org, "num": num}, token)
    project = (data.get("organization") or {}).get("projectV2")
    if not project:
        raise SystemExit(f"Project {org}/{num} not found or token lacks access")
    items, cursor = [], None
    while True:
        page = fetch(ITEMS_QUERY, {"org": org, "num": num, "cursor": cursor}, token)
        conn = page["organization"]["projectV2"]["items"]
        items.extend(conn["nodes"])
        if not conn["pageInfo"]["hasNextPage"]:
            break
        cursor = conn["pageInfo"]["endCursor"]
    return project, items


def field_values(item: dict) -> dict:
    out = {}
    for fv in (item.get("fieldValues") or {}).get("nodes") or []:
        if not fv or not fv.get("field"):
            continue
        name = fv["field"].get("name")
        t = fv.get("__typename", "")
        if t.endswith("SingleSelectValue"):
            out[name] = fv.get("name") or ""
        elif t.endswith("IterationValue"):
            out[name] = fv.get("title") or ""
        elif t.endswith("TextValue"):
            out[name] = fv.get("text") or ""
        elif t.endswith("NumberValue"):
            out[name] = "" if fv.get("number") is None else str(fv["number"])
        elif t.endswith("DateValue"):
            out[name] = fv.get("date") or ""
    return out


def to_row(item: dict, status_f: str, pi_f: str, team_f: str) -> dict | None:
    if item.get("isArchived"):
        return None
    c = item.get("content") or {}
    kind = c.get("__typename") or item.get("type") or ""
    fv = field_values(item)
    parent = c.get("parent") or None
    parent_ref = f"{parent['repository']['nameWithOwner']}#{parent['number']}" if parent else ""
    state = c.get("state") or ("DRAFT" if kind == "DraftIssue" else "")
    return {
        "key": c.get("url") or item["id"],
        "team": fv.get(team_f, "") or "",
        "status": fv.get(status_f, "") or "",
        "pi": fv.get(pi_f, "") or "",
        "kind": kind,
        "repo": (c.get("repository") or {}).get("nameWithOwner", ""),
        "number": c.get("number", ""),
        "title": c.get("title", ""),
        "state": state,
        "assignees": " ".join(a["login"] for a in ((c.get("assignees") or {}).get("nodes") or []) if a),
        "labels": "; ".join(l["name"] for l in ((c.get("labels") or {}).get("nodes") or []) if l),
        "updated_at": c.get("updatedAt") or item.get("updatedAt") or "",
        "closed_at": c.get("closedAt") or "",
        "parent": parent_ref,
        "url": c.get("url", ""),
    }


def is_done(row: dict, done_statuses: set[str]) -> bool:
    if row["status"].strip().lower() in done_statuses:
        return True
    return not row["status"] and row["state"] in ("CLOSED", "MERGED")


def pi_slug(value: str) -> str:
    slug = re.sub(r"[^0-9A-Za-z.]+", "-", value).strip("-")
    return slug or "no-pi"


def current_iteration(field: dict | None, today: dt.date) -> tuple[str | None, str | None, str | None]:
    if not field or "configuration" not in field:
        return None, None, None
    conf = field["configuration"] or {}
    for it in (conf.get("iterations") or []) + (conf.get("completedIterations") or []):
        start = dt.date.fromisoformat(it["startDate"])
        end = start + dt.timedelta(days=int(it["duration"]))
        if start <= today < end:
            return it["title"], start.isoformat(), (end - dt.timedelta(days=1)).isoformat()
    return None, None, None


def write_csv(path: str, rows: list[dict], columns: list[str]) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=columns, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def compute_changes(prev: dict, rows: list[dict], now: str) -> list[dict]:
    changes = []
    cur = {r["key"]: r for r in rows}
    for key, r in cur.items():
        old = prev.get(key)
        base = {"changed_at": now, "repo": r["repo"], "number": r["number"], "title": r["title"], "url": r["url"]}
        if old is None:
            changes.append({**base, "field": "project", "old": "", "new": "added"})
            continue
        for attr, label in TRACKED:
            if (old.get(attr) or "") != (r.get(attr) or ""):
                changes.append({**base, "field": label, "old": old.get(attr) or "", "new": r.get(attr) or ""})
    for key, old in prev.items():
        if key not in cur:
            changes.append({"changed_at": now, "repo": old.get("repo", ""), "number": old.get("number", ""),
                            "title": old.get("title", ""), "url": old.get("url", ""),
                            "field": "project", "old": "present", "new": "removed"})
    return changes


def build_summary(index: dict) -> str:
    lines = [f"# {index['project']['title']} — status by PI and team", "",
             f"Generated {index['generated_at']} from {index['project']['url']}.", ""]
    if index.get("current_pi"):
        end = f", ends {index['current_pi_end']}" if index.get("current_pi_end") else ""
        lines += [f"Current PI: **{index['current_pi']}**{end}", ""]
    statuses = [o for o in index["fields"].get(index["field_names"]["status"], {}).get("options", [])]
    for pi in index["pi_order"]:
        teams = index["counts"][pi]
        tot = sum(t["total"] for t in teams.values())
        done = sum(t["done"] for t in teams.values())
        pct = round(100 * done / tot) if tot else 0
        lines += [f"## {pi} — {done}/{tot} done ({pct}%)", ""]
        cols = statuses + sorted({s for t in teams.values() for s in t["by_status"]} - set(statuses))
        lines.append("| Team | Done/Total | % | " + " | ".join(c or "(no status)" for c in cols) + " |")
        lines.append("|---|---:|---:|" + "---:|" * len(cols))
        for team in sorted(teams, key=lambda t: (t == NO_TEAM, t.lower())):
            c = teams[team]
            p = round(100 * c["done"] / c["total"]) if c["total"] else 0
            lines.append(f"| {team} | {c['done']}/{c['total']} | {p}% | "
                         + " | ".join(str(c["by_status"].get(s, 0)) for s in cols) + " |")
        lines.append("")
    return "\n".join(lines) + "\n"


def run(args, fetch=graphql, now: dt.datetime | None = None) -> dict:
    token = os.environ.get("GH_TOKEN", "")
    if fetch is graphql and not token:
        raise SystemExit("GH_TOKEN is empty: add a PROJECT_EXPORT_TOKEN secret that can read the org project")
    now = now or dt.datetime.now(dt.timezone.utc)
    generated_at = now.replace(microsecond=0).isoformat().replace("+00:00", "Z")
    project, items = fetch_project(args.org, args.project, token, fetch)

    fields = {}
    for f in project["fields"]["nodes"]:
        if not f or "name" not in f:
            continue
        entry = {"type": f.get("dataType")}
        if "options" in f:
            entry["options"] = [o["name"] for o in f["options"]]
        if "configuration" in f:
            conf = f["configuration"] or {}
            entry["iterations"] = [
                {"title": i["title"], "start": i["startDate"], "duration_days": i["duration"]}
                for i in (conf.get("completedIterations") or []) + (conf.get("iterations") or [])]
        fields[f["name"]] = entry

    names = {"status": args.status_field, "pi": args.pi_field, "team": args.team_field}
    raw_pi_field = next((f for f in project["fields"]["nodes"] if f and f.get("name") == args.pi_field), None)
    current_pi, pi_start, pi_end = current_iteration(raw_pi_field, now.date())
    if args.current_pi:
        current_pi, pi_start, pi_end = args.current_pi, None, None

    rows = [r for r in (to_row(i, args.status_field, args.pi_field, args.team_field) for i in items) if r]
    done_statuses = {s.strip().lower() for s in args.done_statuses.split(",") if s.strip()}

    by_pi: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_pi[r["pi"] or NO_PI].append(r)

    counts: dict = {}
    pi_files: dict = {}
    for pi, prow in by_pi.items():
        path = f"pi/{pi_slug(pi) if pi != NO_PI else 'no-pi'}.csv"
        pi_files[pi] = path
        prow.sort(key=lambda r: ((r["team"] or "~").lower(), r["status"], r["repo"], str(r["number"])))
        write_csv(os.path.join(args.out, path), prow, CSV_COLUMNS)
        teams: dict = {}
        for r in prow:
            t = teams.setdefault(r["team"] or NO_TEAM, {"total": 0, "done": 0, "by_status": {}})
            t["total"] += 1
            t["done"] += is_done(r, done_statuses)
            st = r["status"] or "(no status)"
            t["by_status"][st] = t["by_status"].get(st, 0) + 1
        counts[pi] = teams

    def pi_sort(pi: str):
        nums = [int(x) for x in re.findall(r"\d+", pi)]
        return (pi != current_pi, pi == NO_PI, [-n for n in nums], pi)

    index = {
        "generated_at": generated_at,
        "project": {"org": args.org, "number": args.project, "title": project["title"], "url": project["url"]},
        "field_names": names,
        "fields": fields,
        "current_pi": current_pi,
        "current_pi_start": pi_start,
        "current_pi_end": pi_end,
        "pi_order": sorted(counts, key=pi_sort),
        "pi_files": pi_files,
        "item_count": len(rows),
        "counts": counts,
    }

    # Changes since the previous run.
    state_path = os.path.join(args.out, "state.json")
    log_path = os.path.join(args.out, "changes-log.csv")
    prev = None
    if os.path.exists(state_path):
        with open(state_path, encoding="utf-8") as fh:
            prev = json.load(fh).get("items", {})
    changes = compute_changes(prev, rows, generated_at) if prev is not None else []
    new_log = not os.path.exists(log_path)
    with open(log_path, "a", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=CHANGE_COLUMNS, extrasaction="ignore")
        if new_log:
            w.writeheader()
        w.writerows(changes)

    # Remove CSVs for PIs that no longer have items.
    pi_dir = os.path.join(args.out, "pi")
    keep = {os.path.basename(p) for p in pi_files.values()}
    for name in os.listdir(pi_dir) if os.path.isdir(pi_dir) else []:
        if name.endswith(".csv") and name not in keep:
            os.remove(os.path.join(pi_dir, name))

    with open(state_path, "w", encoding="utf-8") as fh:
        json.dump({"generated_at": generated_at,
                   "items": {r["key"]: {k: r[k] for k in ("repo", "number", "title", "url", "status", "pi", "team", "state")}
                             for r in rows}}, fh, indent=1, sort_keys=True)
    with open(os.path.join(args.out, "index.json"), "w", encoding="utf-8") as fh:
        json.dump(index, fh, indent=2)
    with open(os.path.join(args.out, "summary.md"), "w", encoding="utf-8") as fh:
        fh.write(build_summary(index))
    print(f"Exported {len(rows)} items across {len(counts)} PIs; {len(changes)} changes logged; current PI: {current_pi}")
    return index


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--org", default="casangi")
    p.add_argument("--project", type=int, default=33)
    p.add_argument("--out", required=True, help="output directory, e.g. export/project33")
    p.add_argument("--status-field", default="Status")
    p.add_argument("--pi-field", default="Program Increment")
    p.add_argument("--team-field", default="Team")
    p.add_argument("--done-statuses", default="Done", help="comma-separated Status values that count as done")
    p.add_argument("--current-pi", default=os.environ.get("CURRENT_PI") or None,
                   help="override current PI (otherwise taken from the iteration field, if any)")
    args = p.parse_args(argv)
    os.makedirs(args.out, exist_ok=True)
    run(args)


if __name__ == "__main__":
    sys.exit(main())
