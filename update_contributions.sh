#!/usr/bin/env bash
# Regenerate the block between the contribution markers in README.md
# from PRs and issues authored in other people's repositories.
set -euo pipefail

USER_LOGIN=shakewingo
# Append "-repo:owner/name" here to hide a repository.
QUERY="author:$USER_LOGIN -user:$USER_LOGIN is:public -repo:lda-project/lda -repo:wyf3/llm_related"

rows=$(gh api -X GET search/issues -f q="$QUERY" -f sort=created -f order=desc -f per_page=100 --jq '
  .items[]
  | (.repository_url | ltrimstr("https://api.github.com/repos/")) as $repo
  | (if .pull_request then
       (if .pull_request.merged_at then "✅ PR merged" elif .state == "open" then "🟢 PR open" else "⚪ PR closed" end)
     else
       (if .state == "open" then "🟢 Issue open" else "✔️ Issue closed" end)
     end) as $status
  | "| [\($repo)](https://github.com/\($repo)) | \($status) | [#\(.number)](\(.html_url)) \(.title | gsub("\\|"; "\\|")) | \(.created_at[:10]) |"')

block=$(printf '%s\n' \
  '| Project | Type | Title | Opened |' \
  '| --- | --- | --- | --- |' \
  "$rows" \
  '' \
  "<sub>Updated automatically on $(date -u +%Y-%m-%d).</sub>")

python3 - "$block" <<'PY'
import re, sys
path = "README.md"
text = open(path, encoding="utf-8").read()
start, end = "<!-- contributions:start -->", "<!-- contributions:end -->"
new = re.sub(re.escape(start) + r".*?" + re.escape(end),
             lambda _: f"{start}\n{sys.argv[1]}\n{end}", text, flags=re.S)
open(path, "w", encoding="utf-8").write(new)
PY
