#!/usr/bin/env python3
"""Regenerate contributions.json and the contributions table in README.md.

Lists public issues and PRs opened in other people's repositories, plus merged
PRs in those repositories that credit the user as a co-author. A co-authored PR
that closes one of the listed issues is shown on that issue's row instead of its
own. Co-authorship is searched only in those repositories because copies of an
upstream project carry the same commits without being marked as forks.
"""

import json
import re
import subprocess
from datetime import datetime, timezone

USER = "shakewingo"
HIDDEN_REPOS = ["lda-project/lda", "wyf3/llm_related"]

LABELS = {
    ("pr", "merged", "author"): "✅ PR merged",
    ("pr", "merged", "co-author"): "🤝 PR co-authored",
    ("pr", "open", "author"): "🟢 PR open",
    ("pr", "closed", "author"): "⚪ PR closed",
    ("issue", "open", "author"): "🟢 Issue open",
    ("issue", "closed", "author"): "✔️ Issue closed",
}


def gh(path: str, **params: str) -> dict | list:
    args = ["gh", "api", "-X", "GET", path]
    for key, value in params.items():
        args += ["-f", f"{key}={value}"]
    return json.loads(subprocess.run(args, check=True, capture_output=True, text=True).stdout)


def closed_issue_urls(repo: str, number: int) -> list[str]:
    owner, name = repo.split("/")
    query = (
        f'{{ repository(owner: "{owner}", name: "{name}") {{ pullRequest(number: {number}) '
        "{ closingIssuesReferences(first: 20) { nodes { url } } } } }"
    )
    out = subprocess.run(["gh", "api", "graphql", "-f", f"query={query}"],
                         check=True, capture_output=True, text=True).stdout
    nodes = json.loads(out)["data"]["repository"]["pullRequest"]["closingIssuesReferences"]["nodes"]
    return [node["url"] for node in nodes]


def authored() -> list[dict]:
    hidden = " ".join(f"-repo:{repo}" for repo in HIDDEN_REPOS)
    query = f"author:{USER} -user:{USER} is:public {hidden}"
    items = []
    for it in gh("search/issues", q=query, per_page="100")["items"]:
        pr = it.get("pull_request")
        items.append({
            "repo": it["repository_url"].removeprefix("https://api.github.com/repos/"),
            "number": it["number"],
            "title": it["title"],
            "url": it["html_url"],
            "kind": "pr" if pr else "issue",
            "state": "merged" if pr and pr.get("merged_at") else it["state"],
            "role": "author",
            "date": it["created_at"][:10],
        })
    return items


def coauthored(repos: set[str], known_urls: set[str]) -> list[dict]:
    query = f'"Co-authored-by: {USER}" ' + " ".join(f"repo:{repo}" for repo in sorted(repos))
    items = {}
    for commit in gh("search/commits", q=query, per_page="100")["items"]:
        repo = commit["repository"]["full_name"]
        for pr in gh(f"repos/{repo}/commits/{commit['sha']}/pulls"):
            if pr["merged_at"] and pr["html_url"] not in known_urls:
                items[pr["html_url"]] = {
                    "repo": repo,
                    "number": pr["number"],
                    "title": pr["title"],
                    "url": pr["html_url"],
                    "kind": "pr",
                    "state": "merged",
                    "role": "co-author",
                    "date": pr["created_at"][:10],
                    "closes": closed_issue_urls(repo, pr["number"]),
                }
    return list(items.values())


def main() -> None:
    items = authored()
    by_url = {it["url"]: it for it in items}
    for pr in coauthored({it["repo"] for it in items}, set(by_url)):
        closes = pr.pop("closes")
        issue = next((by_url[url] for url in closes if by_url.get(url, {}).get("kind") == "issue"), None)
        if issue:
            issue["fixed_by"] = {"number": pr["number"], "url": pr["url"], "role": "co-author"}
        else:
            items.append(pr)
    items.sort(key=lambda it: (it["date"], it["number"]), reverse=True)
    updated = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    with open("contributions.json", "w", encoding="utf-8") as f:
        json.dump({"updated": updated, "items": items}, f, ensure_ascii=False, indent=2)
        f.write("\n")

    rows = []
    for it in items:
        title = it["title"].replace("|", r"\|")
        label = LABELS[it["kind"], it["state"], it["role"]]
        if fix := it.get("fixed_by"):
            label += " · 🤝 co-authored fix"
            title += f" · fixed by [#{fix['number']}]({fix['url']}) (co-authored)"
        rows.append(
            f"| [{it['repo']}](https://github.com/{it['repo']}) "
            f"| {label} | [#{it['number']}]({it['url']}) {title} | {it['date']} |"
        )
    block = "\n".join([
        "| Project | Type | Title | Date |",
        "| --- | --- | --- | --- |",
        *rows,
        "",
        f"<sub>Updated automatically on {updated}.</sub>",
    ])
    start, end = "<!-- contributions:start -->", "<!-- contributions:end -->"
    with open("README.md", encoding="utf-8") as f:
        text = f.read()
    text = re.sub(re.escape(start) + ".*?" + re.escape(end),
                  lambda _: f"{start}\n{block}\n{end}", text, flags=re.S)
    with open("README.md", "w", encoding="utf-8") as f:
        f.write(text)


if __name__ == "__main__":
    main()
