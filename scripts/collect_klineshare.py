#!/usr/bin/env python3
"""collect_klineshare.py — KlineShare 及免 Key 行情源的 fetcher。

零第三方依赖（纯标准库）。默认走 hq.klineshare.cn 看板免鉴权接口，
可用 --source 切换到 tencent / sina / sohu。

数据源选择（实测于 2026-10-14）：
  klineshare  hq.klineshare.cn/api/*   A股实时/K线/分时/板块/涨停/美股，免 key
  tencent     qt.gtimg.cn + ifzq       A股/港股/美股实时与 K 线，免 key，偶发连接重置
  sina        hq.sinajs.cn             需 Referer；K 线走 quotes.sina.cn
  sohu        q.stock.sohu.com/hisHq   仅历史日线

用法示例：
  python3 scripts/collect_klineshare.py --quote 600519.SS 000001.SZ
  python3 scripts/collect_klineshare.py --kline 600519.SS --period 60 --count 120
  python3 scripts/collect_klineshare.py --trend 600519.SS
  python3 scripts/collect_klineshare.py --limit-up
  python3 scripts/collect_klineshare.py --plates
  python3 scripts/collect_klineshare.py --batch 600519.SS,000001.SZ
  python3 scripts/collect_klineshare.py --search 茅台
  python3 scripts/collect_klineshare.py --us AAPL --kline AAPL
  python3 scripts/collect_klineshare.py --quote 600519.SS --source tencent
"""

import argparse
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

HQ = "https://hq.klineshare.cn/api"
KS = "https://klineshare.cn"
UA = "Mozilla/5.0 (compatible; stocks-ai-view/1.0)"
SINA_REFERER = "https://finance.sina.com.cn"


# ─── HTTP 基础 ───────────────────────────────────────────────


def http(url, referer=None, timeout=20, retries=3, encoding="utf-8"):
    """带重试的 GET。腾讯/新浪偶发连接重置，重试后通常成功；
    5xx 也重试（搜狐实测会间歇 503）。"""
    last = None
    for attempt in range(retries):
        headers = {"User-Agent": UA, "Accept": "*/*"}
        if referer:
            headers["Referer"] = referer
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read().decode(encoding, "ignore")
        except urllib.error.HTTPError as e:
            body = ""
            try:
                body = e.read().decode(encoding, "ignore")
            except Exception:
                pass
            if e.code >= 500 and attempt < retries - 1:
                last = RuntimeError("HTTP %s" % e.code)
                time.sleep(0.6 * (attempt + 1))
                continue
            raise RuntimeError("HTTP %s %s :: %s" % (e.code, url, body[:200]))
        except Exception as e:  # noqa: BLE001 - 统一转重试
            last = e
            if attempt < retries - 1:
                time.sleep(0.6 * (attempt + 1))
    raise RuntimeError("请求失败 %s :: %s" % (url, last))


def http_json(url, **kw):
    return json.loads(http(url, **kw))


def emit(payload, out=None):
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    if out:
        with open(out, "w", encoding="utf-8") as f:
            f.write(text + "\n")
        sys.stderr.write("written: %s\n" % out)
    print(text)


# ─── KlineShare 看板（免 key）─────────────────────────────────


def ks_quote(symbol):
    return http_json("%s/quote?symbol=%s" % (HQ, urllib.parse.quote(symbol)))


def ks_realtime(symbol):
    return http_json("%s/realtime?symbol=%s" % (HQ, urllib.parse.quote(symbol)))


def ks_kline(symbol, period=None, count=None, fq=None):
    params = {"symbol": symbol}
    if period:
        params["period"] = period
    if count:
        params["count"] = count
    if fq:
        params["fq"] = fq
    return http_json("%s/kline?%s" % (HQ, urllib.parse.urlencode(params)))


def ks_trend(symbol, date=None):
    params = {"symbol": symbol}
    if date:
        params["date"] = date
    return http_json("%s/trend?%s" % (HQ, urllib.parse.urlencode(params)))


def ks_batch(symbols):
    return http_json(
        "%s/stocks/batch?symbols=%s" % (HQ, urllib.parse.quote(",".join(symbols)))
    )


def ks_search(keyword):
    return http_json("%s/search?keyword=%s" % (HQ, urllib.parse.quote(keyword)))


def ks_plates():
    return http_json("%s/plates" % HQ)


def ks_plate_stocks(plate_id):
    return http_json("%s/plate/stocks?plate_id=%s" % (HQ, urllib.parse.quote(str(plate_id))))


def ks_limit_up():
    return http_json("%s/limit_up" % HQ)


def ks_limit_down():
    return http_json("%s/limit_down" % HQ)


def ks_break_limit_up():
    return http_json("%s/break_limit_up" % HQ)


def ks_yesterday_limit_up():
    return http_json("%s/yesterday_limit_up" % HQ)


def ks_limit_up_ladder():
    return http_json("%s/limit_up_ladder" % HQ)


def ks_pcp_distribution():
    return http_json("%s/pcp_distribution" % HQ)


def ks_market_temperature():
    return http_json("%s/market_temperature" % HQ)


def ks_us_quote(symbols):
    return http_json(
        "%s/usstock/quotes?symbols=%s" % (HQ, urllib.parse.quote(",".join(symbols)))
    )


def ks_us_kline(symbol, count=None):
    params = {"symbol": symbol}
    if count:
        params["count"] = count
    return http_json("%s/usstock/kline?%s" % (HQ, urllib.parse.urlencode(params)))


# ─── 腾讯（免 key）────────────────────────────────────────────


def _tx_code(symbol):
    """把 600519.SS / 000001.SZ / 00700.HK / AAPL.US 归一成腾讯代码。
    美股必须用 us + 裸代码（usAAPL）；带 .OQ/.US 后缀腾讯会返回 none_match。"""
    s = symbol.strip()
    if s.startswith(("sh", "sz", "hk", "us", "bj")):
        return s
    if "." not in s:
        return s
    code, _, suffix = s.partition(".")
    suffix = suffix.lower()
    if suffix in ("ss", "sh"):
        return "sh" + code
    if suffix == "sz":
        return "sz" + code
    if suffix == "bj":
        return "bj" + code
    if suffix == "hk":
        return "hk" + code
    if suffix in ("us", "usaq", "ny", "nas", "oq"):
        return "us" + code
    return code


def tencent_quote(symbols):
    codes = ",".join(_tx_code(s) for s in symbols)
    text = http("https://qt.gtimg.cn/q=" + codes, encoding="gbk")
    out = {}
    # 形如 v_sh600519="1~名称~代码~现价~..."
    for chunk in text.split(";"):
        chunk = chunk.strip()
        if not chunk or "=" not in chunk:
            continue
        key, _, rest = chunk.partition("=")
        code = key.strip().replace("v_", "")
        out[code] = rest.strip().strip('"')
    return out


def tencent_kline(symbol, period="day", count=30, fq="qfq"):
    code = _tx_code(symbol)
    if code.startswith("us"):
        # 美股 K 线端点与字段名都不同：usfqkline + qfqday
        url = (
            "https://web.ifzq.gtimg.cn/appstock/app/usfqkline/get"
            "?param=%s,%s,,,%d,%s" % (code, period, count, fq)
        )
        key = "qfq%s" % period
    else:
        url = (
            "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
            "?param=%s,%s,,,%d,%s" % (code, period, count, fq)
        )
        key = "qfq%s" % period
    data = http_json(url)
    try:
        return data["data"][code][key]
    except KeyError:
        # 未复权时字段名为 day / week / month
        try:
            return data["data"][code][period]
        except KeyError:
            return data["data"][code]


def tencent_trend(symbol):
    code = _tx_code(symbol)
    data = http_json(
        "https://web.ifzq.gtimg.cn/appstock/app/minute/query?code=%s" % code
    )
    return data["data"][code]["data"]["data"]


# ─── 新浪（免 key，需 Referer）────────────────────────────────


def _sina_code(symbol):
    s = symbol.strip()
    if s.startswith(("sh", "sz", "bj")):
        return s
    code, _, suffix = s.partition(".")
    suffix = suffix.lower()
    if suffix in ("ss", "sh"):
        return "sh" + code
    if suffix == "bj":
        return "bj" + code
    return "sz" + code


def sina_quote(symbols):
    codes = ",".join(_sina_code(s) for s in symbols)
    text = http("https://hq.sinajs.cn/list=" + codes, referer=SINA_REFERER, encoding="gbk")
    out = {}
    for chunk in text.split(";"):
        chunk = chunk.strip()
        if not chunk or "=" not in chunk:
            continue
        key, _, rest = chunk.partition("=")
        out[key.strip().replace("hq_str_", "")] = rest.strip().strip('"')
    return out


def sina_kline(symbol, scale=240, datalen=30):
    code = _sina_code(symbol)
    url = (
        "https://quotes.sina.cn/cn/api/json_v2.php/CN_MarketDataService.getKLineData"
        "?symbol=%s&scale=%d&ma=no&datalen=%d" % (code, scale, datalen)
    )
    return http_json(url)


# ─── 搜狐（免 key，仅历史日线）────────────────────────────────


def sohu_kline(symbol, start, end):
    code = symbol.split(".")[0]
    url = "http://q.stock.sohu.com/hisHq?code=cn_%s&start=%s&end=%s" % (code, start, end)
    return http_json(url)


# ─── KlineShare 付费 API（需要 X-API-Key）─────────────────────


def ks_api_get(path, api_key):
    """KlineShare REST。api_key 从环境变量 KLS_API_KEY 读取，不写入仓库。"""
    req = urllib.request.Request(KS + path, headers={"X-API-Key": api_key, "User-Agent": UA})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode("utf-8", "ignore"))


def ks_mcp_call(tool, arguments, api_key):
    """KlineShare MCP（Streamable HTTP，SSE 响应）。"""
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": tool, "arguments": arguments},
    }
    req = urllib.request.Request(
        KS + "/mcp",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "X-API-Key": api_key,
            "User-Agent": UA,
        },
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        text = r.read().decode("utf-8", "ignore")
    for line in text.splitlines():
        if line.startswith("data: "):
            return json.loads(line[6:])
    return text


# ─── CLI ──────────────────────────────────────────────────────


def build_parser():
    p = argparse.ArgumentParser(description="KlineShare / 免 Key 行情源 fetcher")
    p.add_argument("--source", default="klineshare",
                   choices=["klineshare", "tencent", "sina", "sohu"],
                   help="数据源，默认 klineshare（hq.klineshare.cn 免 key）")
    p.add_argument("--out", help="输出到文件（默认打印到 stdout）")

    g = p.add_argument_group("动作（互斥，可多选）")
    g.add_argument("--quote", nargs="+", metavar="SYMBOL", help="实时快照")
    g.add_argument("--realtime", nargs="+", metavar="SYMBOL", help="精简快照")
    g.add_argument("--kline", nargs="+", metavar="SYMBOL", help="K 线")
    g.add_argument("--trend", nargs="+", metavar="SYMBOL", help="当日分时")
    g.add_argument("--batch", nargs="+", metavar="SYMBOL", help="批量快照")
    g.add_argument("--search", metavar="KEYWORD", help="搜索股票/板块")
    g.add_argument("--plates", action="store_true", help="板块列表")
    g.add_argument("--plate-stocks", metavar="PLATE_ID", help="板块成分股")
    g.add_argument("--limit-up", action="store_true", help="涨停池")
    g.add_argument("--limit-down", action="store_true", help="跌停池")
    g.add_argument("--break-limit-up", action="store_true", help="炸板池")
    g.add_argument("--yesterday-limit-up", action="store_true", help="昨涨停池")
    g.add_argument("--ladder", action="store_true", help="连板天梯")
    g.add_argument("--pcp", action="store_true", help="涨跌幅分布")
    g.add_argument("--temperature", action="store_true", help="市场温度")
    g.add_argument("--us", nargs="+", metavar="SYMBOL", help="美股（ks 源）")

    p.add_argument("--period", help="K 线周期：1/5/15/30/60（ks）；day/week/month（tencent）")
    p.add_argument("--count", type=int, default=120, help="K 线条数")
    p.add_argument("--fq", help="复权：qfq/hfq/none")
    p.add_argument("--start", help="sohu 起始日 YYYYMMDD")
    p.add_argument("--end", help="sohu 截止日 YYYYMMDD")
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    src = args.source

    actions = [
        args.quote, args.realtime, args.kline, args.trend, args.batch,
        args.search, args.plates, args.plate_stocks, args.limit_up,
        args.limit_down, args.break_limit_up, args.yesterday_limit_up,
        args.ladder, args.pcp, args.temperature, args.us,
    ]
    if not any(a for a in actions):
        build_parser().print_help()
        return 2

    results = {}

    def run(name, fn):
        try:
            results[name] = fn()
        except Exception as e:  # noqa: BLE001 - 单点失败不阻断其他动作
            results[name] = {"error": str(e)}

    if src == "klineshare":
        # 带 .US 后缀的 symbol 自动走美股端点；--us 作为等价格式
        us_extra = list(args.us or [])
        if args.quote:
            us_extra += [s for s in args.quote if s.upper().endswith(".US")]
        if us_extra:
            run("us_quote", lambda: ks_us_quote(us_extra))
        if args.kline:
            us_kline = [s for s in args.kline if s.upper().endswith(".US")]
            for s in us_kline:
                run("us_kline:" + s, lambda s=s: ks_us_kline(s, args.count))
            args.kline = [s for s in args.kline if not s.upper().endswith(".US")]
        if args.quote:
            for s in args.quote:
                if not s.upper().endswith(".US"):
                    run("quote:" + s, lambda s=s: ks_quote(s))
        if args.realtime:
            for s in args.realtime:
                run("realtime:" + s, lambda s=s: ks_realtime(s))
        if args.kline:
            for s in args.kline:
                run("kline:" + s,
                    lambda s=s: ks_kline(s, args.period, args.count, args.fq))
        if args.trend:
            for s in args.trend:
                run("trend:" + s, lambda s=s: ks_trend(s))
        if args.batch:
            run("batch", lambda: ks_batch(args.batch))
        if args.search:
            run("search", lambda: ks_search(args.search))
        if args.plates:
            run("plates", ks_plates)
        if args.plate_stocks:
            run("plate_stocks", lambda: ks_plate_stocks(args.plate_stocks))
        if args.limit_up:
            run("limit_up", ks_limit_up)
        if args.limit_down:
            run("limit_down", ks_limit_down)
        if args.break_limit_up:
            run("break_limit_up", ks_break_limit_up)
        if args.yesterday_limit_up:
            run("yesterday_limit_up", ks_yesterday_limit_up)
        if args.ladder:
            run("ladder", ks_limit_up_ladder)
        if args.pcp:
            run("pcp_distribution", ks_pcp_distribution)
        if args.temperature:
            run("market_temperature", ks_market_temperature)

    elif src == "tencent":
        if args.quote:
            run("quote", lambda: tencent_quote(args.quote))
        if args.kline:
            for s in args.kline:
                run("kline:" + s,
                    lambda s=s: tencent_kline(s, args.period or "day", args.count,
                                              args.fq or "qfq"))
        if args.trend:
            for s in args.trend:
                run("trend:" + s, lambda s=s: tencent_trend(s))

    elif src == "sina":
        if args.quote:
            run("quote", lambda: sina_quote(args.quote))
        if args.kline:
            scale = args.period or 240
            for s in args.kline:
                run("kline:" + s,
                    lambda s=s: sina_kline(s, int(scale), args.count))

    elif src == "sohu":
        if args.kline:
            start = args.start or "20260101"
            end = args.end or time.strftime("%Y%m%d")
            for s in args.kline:
                run("kline:" + s, lambda s=s: sohu_kline(s, start, end))

    emit(results, args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
