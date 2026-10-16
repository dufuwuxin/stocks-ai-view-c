#!/usr/bin/env bash
# pages-data-sync.sh — 把 A 仓 (qwerzxcva/stocks-ai-view) + db-market 的关键数据同步到
# stocks-ai-view-c/data/ (GitHub Pages 同源), 保持前端同源优先路由的数据新鲜。
# 由 .github/workflows/pages-sync.yml 每10分钟触发。
set -u
FILES_A="latest.json cycle.json sector_pool.json lowpool.json cycle_deep.json cloud_analysis.json ai_review.json engine_weights.json morning_review.json daily_brief.json review_today.json universe.json hot_impact.json enrich.json multidim.json decision.json self_reflect.json edge_report.json anomaly_report.json signal_audit.json validation_report.json ban_prob.json ban_pick.json flow_divergence.json scenario.json"
TOKEN="$1"
put() { # repo path content_file
  local repo="$1" path="$2" f="$3" sha
  sha=$(curl -s --max-time 15 -H "Authorization: token $TOKEN" "https://api.github.com/repos/$repo/contents/$path" | python3 -c 'import json,sys
try: print(json.load(sys.stdin)["sha"])
except Exception: print("")' 2>/dev/null)
  if [ -n "$sha" ]; then
    python3 - "$repo" "$path" "$f" "$sha" <<'PYEOF'
import json, sys, urllib.request, base64
repo, path, f, sha = sys.argv[1:5]
body = {"message": "pages-sync: " + path.split("/")[-1], "content": base64.b64encode(open(f, "rb").read()).decode(), "sha": sha}
req = urllib.request.Request(f"https://api.github.com/repos/{repo}/contents/{path}", data=json.dumps(body).encode(),
    headers={"Authorization": "token " + __import__("os").environ["GH_TOKEN"], "Content-Type": "application/json"}, method="PUT")
try:
    urllib.request.urlopen(req, timeout=30)
except Exception as e:
    print("put fail", path, e)
PYEOF
  else
    python3 - "$repo" "$path" "$f" <<'PYEOF'
import json, sys, urllib.request, base64
repo, path, f = sys.argv[1:4]
body = {"message": "pages-sync: " + path.split("/")[-1], "content": base64.b64encode(open(f, "rb").read()).decode()}
req = urllib.request.Request(f"https://api.github.com/repos/{repo}/contents/{path}", data=json.dumps(body).encode(),
    headers={"Authorization": "token " + __import__("os").environ["GH_TOKEN"], "Content-Type": "application/json"}, method="PUT")
try:
    urllib.request.urlopen(req, timeout=30)
except Exception as e:
    print("put fail", path, e)
PYEOF
  fi
}
TMP=$(mktemp -d)
for f in $FILES_A; do
  curl -s --max-time 20 "https://raw.githubusercontent.com/qwerzxcva/stocks-ai-view/main/data/$f" -o "$TMP/$f" 2>/dev/null
  if head -c1 "$TMP/$f" 2>/dev/null | grep -q '[\[{]'; then
    put "dufuwuxin/stocks-ai-view-c" "data/$f" "$TMP/$f"
  fi
  sleep 0.3
done
# db-market
for f in today_picks.json morning_review.json afternoon_picks.json entry_plans.json review_today.json close_review.json engine_weights.json universe.json; do
  curl -s --max-time 20 "https://raw.githubusercontent.com/jiegengxiangjianxue1/db-market/main/market/$f" -o "$TMP/m_$f" 2>/dev/null
  if head -c1 "$TMP/m_$f" 2>/dev/null | grep -q '[\[{]'; then
    put "dufuwuxin/stocks-ai-view-c" "data/$f" "$TMP/m_$f"
  fi
  sleep 0.3
done
echo "sync done $(date)"
