# Mirror node C

stocks-ai-view 的采集镜像节点 (多账号分片, 分散出口 IP)。

- 代码唯一事实源: https://github.com/qwerzxcva/stocks-ai-view
- 本仓分片: c
- 本仓 cron 分钟位: 0,5,10,...,55 (mod 5)
- 只跑 shard-collect 与 bulk-collect; 其余 workflow 的 schedule 已由
  scripts/deploy_mirror.py 禁用 (避免与 A 仓重复执行整条流水线,
  重复烧 Actions 额度且 commit 互相覆盖)
- **本仓不承载站点**: 唯一站点是
  https://qwerzxcva.github.io/stocks-ai-view/ (A 仓, Pages 源即 main
  根目录, data/ 与 index.html 同源)。前端 gh_sources.js 并发读三仓 raw
  取 ts 最新的那份, 本仓只作为第三个采集出口与容错节点。
- 不要在本地手改代码, 会被下次 deploy_mirror.py 覆盖
