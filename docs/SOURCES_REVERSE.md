# 行情数据源逆向结论（KlineShare / Tushare / 免 Key 源）

> 逆向执行时间：2026-10-14（容器内 AArch64，Python 3 标准库 urllib 直连实测）
> 约束：未 pip install 任何包；未创建任何账号；未使用任何真实密钥。
> 所有「实测」结论均来自本机 curl / urllib 的真实 HTTP 响应；「未核实」表示未做动态验证。

---

## 0. 结论摘要（TL;DR）

| 目标 | 有无白嫖路径 | 关键事实 |
|---|---|---|
| **KlineShare 主站 API（klineshare.cn/v1、/v2）** | **无** | 除 `GET /v1/health` 与 `/public/v1/*` 元数据外，全部 401。试用 key / demo key 全部返回「无效的 API Key」 |
| **KlineShare MCP（/mcp）** | **半白嫖** | `initialize` / `tools/list` / `resources/list` 免 key；`get_health`、`get_public_catalog`、`get_market_indices`、`search_indices` 四个 tool 免 key 可调；数据类 tool 仍需 key |
| **KlineShare 行情看板（hq.klineshare.cn/api）** | **有（重大发现）** | 看板前端自用的 `/api/*` 全部免鉴权：实时快照、K 线（含分钟线）、分时、板块、涨停/跌停/炸板/连板、涨跌分布、市场温度。这是本次最有价值的白嫖入口 |
| **Tushare Pro** | **无** | 无 token → `40101 您上传Token！`；demo/test/trial/free/sample 等全部「您的token不对」。无 GET 版本内部接口 |
| **腾讯 / 新浪** | **有** | 传统免 key 源，A股 + 港股 + 美股实时与 K 线均可，无需任何 header |

**可直接落地使用的免 key 数据面**（详见第 4 节）：
1. `https://hq.klineshare.cn/api/*` — A股实时/K线/分时/板块/涨停专题/美股日线与分时，**全免鉴权**
2. `https://qt.gtimg.cn/q=...` — 腾讯全市场实时快照
3. `https://web.ifzq.gtimg.cn/appstock/app/fqkline/get` — 腾讯 K 线（A股/港股/美股，含复权）
4. `https://hq.sinajs.cn/list=...`（需 `Referer`）— 新浪实时快照
5. `https://q.stock.sohu.com/hisHq` — 搜狐历史日线

对应 fetcher：`scripts/collect_klineshare.py`（默认源 = hq.klineshare.cn 免 key 接口，可 `--source` 切换腾讯/新浪/搜狐）。

---

## 1. KlineShare 站点结构（逆向得到的真实拓扑）

三个不同角色、**鉴权模型完全不同**的域名，混用会误判：

| 域名 | 角色 | 鉴权 |
|---|---|---|
| `klineshare.cn` | 门户 + 付费 API + 用户中心（Nuxt SPA） | 业务 API 需 `X-API-Key`；`/public/v1/*` 免 key |
| `hq.klineshare.cn` | 量化看板（Vite/Vue SPA，纯前端） | `/api/*` 公开数据 **免鉴权**；`favorites`/`recent`/`groups` 需 Bearer token |
| `pay.klineshare.cn` | 支付 | nginx，`/user/v1` 404 |

### 1.1 门户前端逆向（只读抓 JS）

从 `/user/register/` 页面提取 Nuxt 入口 `/_nuxt/CVDNvBaF.js`，找到路由表与注册页 chunk `CqN7x0W6.js`、API 封装 `BEv1vv1A.js`：

- `BEv1vv1A.js`：用户中心 API 前缀为 `/user/v1`，token 存 `sessionStorage['ext_portal_token']`，以 `Authorization: Bearer` 发送；另有 `payOrigin` 独立前缀。
- `CqN7x0W6.js`：注册表单字段只有 `username` / `password` / `display_name`（可选）+ 可选 `token`（邀请）/ `campaign_code`（团购）。**注册页无手机号、无验证码字段**。
- 注册页会先请求 `/public/v1/registration/status` 判断是否开放自助注册。

### 1.2 注册链路实测（未真正创建账号）

```
POST https://klineshare.cn/user/v1/register   {"username":"ab","password":"123456"}
→ HTTP 400 {"message":"用户名至少 3 个字符","success":false}

GET  https://klineshare.cn/public/v1/registration/status
→ HTTP 200 {"hint":"可免费自助注册；付费套餐登录后购买。","invite_registration":true,"open_registration":true,"success":true}
```

**结论（事实层面）**：免费自助注册确实开放，且**不需要手机号**，只需用户名（≥3 字符）+ 密码（≥6 字符）。注册成功即返回 `api_key`（前端代码 `fe.alert(String(e.api_key), "API Key（仅显示一次）")`）。

**边界说明**：本次未执行真实注册（不属于授权范围，且会产生真实账号）。因此「注册后免费额度具体是多少」**未核实**。文档与 catalog 只说注册送「基础权限」，未列免费档位的数值；catalog 的 `tier_columns` 只有 4 个付费档（基础版 ¥99/月、专业版 ¥199/月、旗舰版 ¥399/月、国内期货 ¥399/月），`register_roles` 同样只有这 4 个——**没有独立「免费版」档位**，但 `scope_rows` 里反复出现「免费版及以上」的措辞（如 `zfpg`、`yjfp`、`finance` 权限描述），说明账号体系里存在一个未在价目表展示的基础/免费层级。这是文档与动态配置之间的矛盾点，**未核实**其真实配额。

---

## 2. KlineShare 付费 API（klineshare.cn）— 实测明细

### 2.1 免 key 端点（实测全部 200）

| URL | 说明 |
|---|---|
| `GET /v1/health` | `{"success":true,"version":"1"}` |
| `GET /public/v1/catalog` | 139 KB：套餐档位、scope×档位矩阵（145 条）、指数列表、批量上限 |
| `GET /public/v1/docs.md` | 105 KB 完整 API Markdown 文档 |
| `GET /public/v1/corp/schema` | 上市公司资料字段说明 |
| `GET /public/v1/etf/schema` | ETF 响应字段说明 |
| `GET /public/v1/moneyflow/schema` | 资金流三表字段说明 |
| `GET /public/v1/moneyflow/ranking/catalog` | 新浪资金流排行目录 |
| `GET /public/v1/indices` | 主要指数 symbol 清单 |
| `GET /public/v1/registration/status` | 注册开放状态 |
| `GET /llms-full.txt` | 同 docs.md，供 LLM 阅读 |

`/public/v1/moneyflow/ranking/em/catalog` 在 llms.txt 中被引用，**本次未逐个实测**（不影响结论，属同类元数据）。

### 2.2 需 key 端点（实测 401）

无 key 时统一返回：

```json
{"code":401,"message":"缺少 API Key（Header: X-API-Key 或参数 api_key）","success":false}
```

实测 401 的路径：`/v1/me`、`/v1/realtime`、`/v2/realtime`、`/v1/kline`、`/v1/stock`、`/v1/stocks`、`/v1/calendar`、`/v1/catalog/indices`、`/v1/catalog/plates`、`/v1/metal/realtime`、`/v1/usstock/realtime`、`/v1/hkstock/realtime`、`/v1/futures/realtime`、`/v1/global-index/realtime`。

实测 404（路径不存在，非鉴权问题）：`/v1/index`、`/v1/plate`、`/v1/market`、`/v1/status`、`/v1/docs`、`/v1/quote`、`/v1/indices`、`/openapi.json`、`/swagger.json`。真实路径在 `scope_rows[].path` 里，如 `/v1/index/realtime`、`/v1/plate/realtime`。

### 2.3 试用/demo key 探测（全部失败）

REST 侧，`X-API-Key` 与 `?api_key=` 分别试过：

```
demo / test / trial / free / guest / anonymous / api_key / apikey / sample / public
→ 全部 {"code":401,"message":"无效的 API Key","success":false}
```

MCP 侧同样失败（`X-API-Key`、`?token=`、`?api_key=` 三种传法都试）：

```
tools/call get_realtime  symbol=600519.SS
→ {"http_status":401,"code":401,"message":"无效的 API Key","success":false}
```

未在 `/docs`、`/pricing`、`/docs/auth`、`/docs/mcp`、`/docs/skills`、`/llms-full.txt` 页面中发现任何可直接使用的示例 key——文档里的 key 一律是占位符 `tg_xxx` / `tg_xxxxxxxxxxxxxxxxxxxxxxxx` / `tg_你的密钥`。

**结论：KlineShare 主站 API 无白嫖路径。** 免 key 能拿到的只有元数据（文档、套餐矩阵、指数清单），没有任何行情数值。

### 2.4 KlineShare MCP（`https://klineshare.cn/mcp`）— 部分免 key

协议：Streamable HTTP，`Content-Type: application/json` + `Accept: application/json, text/event-stream`，GET 会 406。

**免 key 可用的 JSON-RPC 方法**（实测）：

- `initialize` → 200，`serverInfo: {name:"klineshare", version:"1.28.1"}`
- `tools/list` → 200，返回 **128 个 tool**
- `resources/list` → 200，返回 `docs://api-reference`

**免 key 可用的 tool**（实测，`tools/call` 成功返回数据）：

| Tool | 返回 |
|---|---|
| `get_health` | `{"http_status":200,"success":true,"version":"1"}` |
| `get_public_catalog` | 完整 catalog JSON（同 `/public/v1/catalog`） |
| `get_market_indices` | 10 条主要指数（symbol/name/group/is_primary/quote_ready） |
| `search_indices` | `{"keyword":"300"}` → 沪深300 等指数 + `meta.catalog` 统计 |

**需 key 的 tool**（实测返回 `未配置 EXT_API_KEY` 或 `无效的 API Key`）：

```
get_my_permissions, get_realtime, get_realtime_v2, get_trend, get_auction, get_kline,
get_kline_v2, get_index_realtime, get_usstock_realtime, get_futures_realtime,
get_global_index_realtime, get_metal_realtime, get_global_bond_realtime,
get_etf_realtime, search_stocks, search_etfs, search_bonds, get_bond_realtime, ...
```

注意：`get_hkstock_realtime`、`get_me` 在 128 个 tool 中不存在（返回 `Unknown tool`），文档与实际 tool 集不完全一致。

**MCP 鉴权方式**（文档 `/docs/mcp`）：`X-API-Key: tg_xxx` 或 `Authorization: Bearer tg_xxx` 或 `?token=tg_xxx` 或 `?api_key=tg_xxx`。客户端配置示例：

```json
{
  "mcpServers": {
    "klineshare": {
      "url": "https://klineshare.cn/mcp",
      "headers": { "X-API-Key": "tg_你的密钥" }
    }
  }
}
```

---

## 3. Tushare Pro — 实测无免 token 路径

### 3.1 API 行为实测

```
POST https://api.tushare.pro  (无 body)              → {"code":40101,"msg":"不是合格的json格式，EOF"}
POST https://api.tushare.pro  {"api_name":"daily",...} (无 token)
                                                     → {"code":40101,"msg":"您上传Token！"}
POST https://api.tushare.pro  token=demo|test|trial|free|sample|public|123456|token|tushare
                                                     → {"code":40101,"msg":"您的token不对，请确认。"}
```

**任何 HTTP 方法 / 任何路径都返回同一 JSON**——`api.tushare.pro` 是单一 JSON-RPC-ish 入口，没有 GET 版本、没有 `/api/...` 子路径、没有 `/openapi.json`、没有 `/status`。实测 `/api`、`/docs`、`/status`、`/health`、`/v1`、`/openapi.json`、`/swagger.json`、`/trade_cal` 全部返回 `40101 不是合格的json格式，EOF`（即未进入业务逻辑）。

### 3.2 积分门槛（文档实测，`/document/2?doc_id=340` 等）

- 新注册送 **100 积分**（`/document/1?doc_id=13`）。
- 120 积分档：非复权日线 `daily`、`new_share`、`shibor_lpr`、`libor`、`hibor`，**每分钟 50 次 / 每天 8000 次**。
- 2000 积分档：`trade_cal`、`adj_factor`、`daily_basic`、`income`、`balancesheet`、`cashflow`、`index_basic`、`fund_basic`、`hk_basic` 等绝大多数接口。
- 分钟数据 / 港美股 / 新闻公告等**单独付费开权限**，与积分无关。

**结论**：Tushare 没有「无 token 可用」的接口。120 积分档的 `daily`（日线，非复权）是理论最低门槛，但仍需注册 + 手机号 + 拿 token。本次未注册，**未动态验证** token 真实性。

`waditu/tushare`（旧版 0.x）README 明确写「TuShare Pro版已发布，请访问新的官网」，旧版的 `get_hist_data` 等免 token 接口**随旧版一起废弃**，api.tushare.org 域名已无法解析（实测 DNS 失败）。

---

## 4. 可白嫖的免 key 数据源（重点）

### 4.1 `hq.klineshare.cn/api/*` —— KlineShare 看板前端自用接口（本次最大发现）

从看板首页提取 Vite 入口 `index-ChhH-4F-.js`，在 `assets/market-C3dPKZzr.js` 中找到 39 个 `/api/*` 端点。**全部公开数据端点免鉴权、无 Referer/UA 要求、无 key**。

实测汇总（2026-10-14 盘中/收盘后均可 200）：

| 端点 | 参数 | 返回 |
|---|---|---|
| `/api/quote` | `symbol=600519.SS` | 快照对象：open/high/low/close/price/pre_close/volume/turnover/name/change_percent + `valuation{pe_ttm,pb,total_market_cap,...}` |
| `/api/realtime` | `symbol=600519.SS` | 精简快照（无 valuation） |
| `/api/stocks/batch` | `symbols=600519.SS,000001.SZ` | 数组：price/change_percent/limit_status/turnover_ratio/limit_up_days/per/total_capital |
| `/api/kline` | `symbol` + `period=1\|5\|15\|30\|60\|101\|102` + `count` + `fq=qfq` | K 线数组：OHLC + volume/turnover/amount + average_px/px_change/px_change_rate + ma5/ma10/ma20/ma60 + turnover_ratio |
| `/api/trend` | `symbol` | 当日分时：`{data:[{timestamp,price,avg_price,volume,turnover,change_percent}]}` |
| `/api/search` | `keyword=茅台`（URL 编码） | `{stocks:[{name,symbol,plates,bkjs}]}` |
| `/api/stock/plates` | `symbol` | 所属板块 + 涨跌幅 + 入选理由 |
| `/api/plates` | — | 全部板块数组：name/change_percent/rise_count/fall_count/limit_up_count/fund_flow |
| `/api/plate/brief` | `plate_id` | 板块概要 |
| `/api/plate/stocks` | `plate_id` | 板块成分股 |
| `/api/limit_up` / `/api/limit_down` / `/api/break_limit_up` / `/api/yesterday_limit_up` | — | 涨停/跌停/炸板/昨涨停池 |
| `/api/limit_up_ladder` | — | 连板天梯 `{ladder:[{height,label,count,stocks}]}` |
| `/api/pcp_distribution` | — | 全市场涨跌幅分布直方图 |
| `/api/market_temperature` | — | 市场温度序列 `{points:[{timestamp,temperature,rise_count,fall_count,limit_up_count}]}` |
| `/api/market/indices` | — | 指数清单 |
| `/api/usstock/quotes` | `symbols=AAPL` | 美股快照（盘前/盘中实时） |
| `/api/usstock/kline` | `symbol=AAPL&count=3` | 美股日 K `{bars:[...]}` |
| `/api/trend` | `symbol=AAPL.US` | 美股分时 |
| `/api/favorites` `/api/recent` `/api/groups/list` | — | **401 Unauthorized**（用户私有数据，需 Bearer） |

已禁用市场（实测 `{"error":"Market disabled: xxx"}` + HTTP 404）：`/api/crypto/*`、`/api/futures/*`。港股 symbol（`00700.HK`）`/api/quote` 返回 `quote: null`，`/api/kline` 500——**该看板不支持港股**。

**要点**：
- `period` 用分钟数（1/5/15/30/60）或东财风格码（101=日, 102=周?）；实测 `period=60` 返回真正 60 分钟线，`period=101`/`102` 返回日线。`day`/`d`/`w`/`m` 字符串会 500。
- `count` 实测 5000 也能返回（2.1 MB），未见截断。
- 连续 8 次请求全 200，无限流迹象；未做压力测试。
- K 线自带 `ma5/ma10/ma20/ma60`，服务端算好，省客户端计算。

### 4.2 腾讯（免 key，全市场）

```
GET https://qt.gtimg.cn/q=sh600519,sz000001
GET https://qt.gtimg.cn/q=hk00700
GET https://qt.gtimg.cn/q=usAAPL
```

GBK 编码，`~` 分隔字段数组。本项目 `realtime.js:26-60` 已核对过字段位（p[3]=现价 p[4]=昨收 p[32]=涨跌幅% p[38]=换手率 p[39]=PE(TTM) p[44]=总市值亿 p[45]=流通市值亿 p[46]=PB p[30]=时间），与本次实测一致。

K 线：

```
GET https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param=sh600519,day,,,10,qfq
GET https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param=hk00700,day,,,5,qfq
GET https://web.ifzq.gtimg.cn/appstock/app/usfqkline/get?param=usAAPL.OQ,day,,,5,qfq
GET https://web.ifzq.gtimg.cn/appstock/app/minute/query?code=sh600519     # 分时
```

注意 `qt.gtimg.cn` 与 `web.ifzq.gtimg.cn` 从本容器访问时**偶发连接重置**（本次 `qt.gtimg.cn` 首次失败、重试成功），需重试逻辑。

### 4.3 新浪（免 key，需 Referer）

```
GET https://hq.sinajs.cn/list=sh600519,sz000001      # 必须带 Referer: https://finance.sina.com.cn
GET https://quotes.sina.cn/cn/api/json_v2.php/CN_MarketDataService.getKLineData?symbol=sh600519&scale=240&ma=no&datalen=5
GET https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData?symbol=sh600519&scale=240&ma=no&datalen=3
GET https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/Market_Center.getHQNodeData?page=1&num=5&sort=symbol&asc=1&node=hs_a
```

GBK 编码，逗号分隔固定字段位。`hq.sinajs.cn` 不带 Referer 实测被拒。

### 4.4 搜狐（免 key，纯 HTTP）

```
GET http://q.stock.sohu.com/hisHq?code=cn_600519&start=20261001&end=20261014
→ [{"status":0,"hq":[["2026-10-14","1270.10","1286.00","11.11","0.87%","1266.00","1286.75","23773","304560.78","0.19%","6.00"], ...]}]
```

### 4.5 实测不通的源

| 源 | 结果 |
|---|---|
| `push2.eastmoney.com` / `82.push2.eastmoney.com` | Connection reset by peer（本容器网络不可达，非接口失效） |
| `push2his.eastmoney.com` | Remote end closed connection without response |
| `stock.xueqiu.com/v5/stock/quote.json` | HTTP 400（雪球需 cookie/token） |
| `api.doctorxiong.club` | SSL EOF |
| `api.tushare.org` | DNS 无法解析 |

---

## 5. 脚本：`scripts/collect_klineshare.py`

单文件、零第三方依赖（纯标准库），默认走 **hq.klineshare.cn 免 key 接口**，可用 `--source` 切换到腾讯/新浪/搜狐。

```bash
python3 scripts/collect_klineshare.py --quote 600519.SS 000001.SZ
python3 scripts/collect_klineshare.py --kline 600519.SS --period 60 --count 120
python3 scripts/collect_klineshare.py --trend 600519.SS
python3 scripts/collect_klineshare.py --limit-up
python3 scripts/collect_klineshare.py --plates
python3 scripts/collect_klineshare.py --batch 600519.SS,000001.SZ,sh000001
python3 scripts/collect_klineshare.py --search 茅台
python3 scripts/collect_klineshare.py --us AAPL --kline AAPL
python3 scripts/collect_klineshare.py --quote 600519.SS --source tencent   # tencent|sina|sohu
```

默认输出 JSON 到 stdout；`--out data/xxx.json` 落盘。

**KlineShare 付费 key 用法**（如果之后拿到 key，脚本同样支持 REST 与 MCP 两条路径）：

```bash
# REST
curl -sS "https://klineshare.cn/v1/kline?symbol=600519.SS&period=86400&count=100" \
  -H "X-API-Key: tg_你的密钥"

# MCP
curl -sS -X POST https://klineshare.cn/mcp \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json, text/event-stream' \
  -H 'X-API-Key: tg_你的密钥' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"get_kline_v2","arguments":{"symbol":"600519.SS","period":"86400","count":100}}}'
```

---

## 6. 限制与未完成项（明确保留）

1. **未注册 KlineShare 账号**：注册后免费额度的具体数值（每分钟次数、可调 scope）**未核实**。文档只说「免费注册即可获得基础权限与 API Key」，价目表只有 4 个付费档。
2. **未注册 Tushare 账号**：120 积分档 `daily` 的真实可用性**未动态验证**。
3. `hq.klineshare.cn` 未做压力测试与限流探测；未知其防爬策略与 IP 封禁阈值。生产使用应加退避与缓存。
4. `hq.klineshare.cn` 是第三方商业站的**看板前端接口**，非公开承诺 API：字段与可用性随时可能变更或关闭，不应作为唯一数据源，需与腾讯/新浪互为降级。
5. 腾讯 `qt.gtimg.cn` 在本容器有连接重置现象，脚本已加重试，但重试次数与超时未针对生产调优。
6. 东财 push2/push2his 在本容器不可达，**未验证**其接口本身是否有效（属网络环境限制，非接口结论）。
7. 港股数据：腾讯/新浪可用，KlineShare 看板不支持。
