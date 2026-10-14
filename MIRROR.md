# Mirror node C

该仓是 stocks-ai-view 的镜像节点, 仅用于多账号 cron 错峰 (2 分钟级数据粒度)。

- 代码唯一事实源: https://github.com/qwerzxcva/stocks-ai-view
- 本仓 cron 分钟位: 0,5,10,15,20,25,30,35,40,45,50,55 (mod 5)
- 只跑采集链路; AI/复盘/归档/回溯已禁用 schedule
- 不要在本地手改代码, 会被下次部署覆盖
