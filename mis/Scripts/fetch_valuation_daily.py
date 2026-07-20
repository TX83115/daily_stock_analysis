"""
fetch_valuation_daily.py
悟道全市场估值快照 -> 本地 DuckDB valuation_daily（P1：本地优先架构的第一块）。

目的：把市值/估值数据落成本地 SQL，筛选/回测只读本地，不再受
stock_screener 市值联表滞后影响；悟道拿不到时也有最近快照可用（Plan B）。

抓取策略（按调用成本自动选择）：
- 策略A（~19次/交易日）：stock_screener 按 totalMarketCapYi 降序分页扫全市场
  （limit=300 上限，用"上一页最后一名的市值"作 marketCapMaxYi 游标下翻）。
  仅在该交易日 stock_screener 市值联表已就绪时可用；联表滞后时首页即 0 行。
- 策略B（~277次/交易日）：valuation_snapshot 逐票扫（20只/批），读 daily_basic，
  对任意交易日都新鲜。策略A不可用或覆盖率<80%时自动回退。

幂等：按 trade_date DELETE+INSERT（与 fetch_* 家族一致）。可续跑：回填时只处理
valuation_daily 里缺失的交易日，新日期优先；--max-calls 配额护栏（悟道 2000次/天），
预算用尽即停，下次运行自动续。

用法：
  python fetch_valuation_daily.py                     # 只抓最新交易日
  python fetch_valuation_daily.py --date 2026-07-15   # 抓指定交易日
  python fetch_valuation_daily.py --backfill 250 --max-calls 1200
      # 最近250个交易日中缺失的，新日期优先，最多用1200次调用后停止（可反复续跑）

需环境变量 WUDAO_API_KEY。单位约定：市值列为【亿元】。
"""
import os, json, time, argparse, requests, duckdb
from datetime import datetime

KEY = os.environ.get("WUDAO_API_KEY")
MCP_URL = "https://stock.quicktiny.cn/api/mcp"
DB_PATH = "/Users/tx/market-data/market.duckdb"

# 悟道实测限速 50 次/分钟（-32028）。全局节流 + 命中限速时按 retryAfterMs 等待重试。
MIN_INTERVAL_S = 1.25
_last_call_at = [0.0]

DDL = """
CREATE TABLE IF NOT EXISTS valuation_daily (
    trade_date    DATE,
    code          VARCHAR,   -- 6位代码
    name          VARCHAR,
    close         DOUBLE,
    total_mv_yi   DOUBLE,    -- 总市值，亿元
    circ_mv_yi    DOUBLE,    -- 流通市值，亿元
    pe_ttm        DOUBLE,
    pb            DOUBLE,
    turnover_rate DOUBLE,
    volume_ratio  DOUBLE,
    source        VARCHAR,   -- screener_page | valuation_snapshot
    fetched_at    TIMESTAMP,
    PRIMARY KEY (trade_date, code)
)
"""


def call_tool(name, arguments, _retries=3):
    for attempt in range(_retries + 1):
        wait = MIN_INTERVAL_S - (time.time() - _last_call_at[0])
        if wait > 0:
            time.sleep(wait)
        _last_call_at[0] = time.time()
        try:
            resp = requests.post(MCP_URL,
                headers={"Authorization": "Bearer " + (KEY or ""), "Content-Type": "application/json"},
                json={"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                      "params": {"name": name, "arguments": arguments}},
                timeout=60)
            resp.raise_for_status()
        except requests.exceptions.RequestException as e:
            # 瞬时网络故障（SSL EOF/连接重置等）：指数退避重试
            if attempt < _retries:
                delay = 5 * (2 ** attempt)
                print(f"  [网络] {type(e).__name__}，{delay}s 后重试 ({name})")
                time.sleep(delay)
                continue
            raise
        result = resp.json()
        err = result.get("error")
        if err:
            if err.get("code") == -32028 and attempt < _retries:   # rate limit
                delay = (err.get("data", {}).get("retryAfterMs", 60000)) / 1000.0 + 1
                print(f"  [限速] 等待 {delay:.0f}s 后重试 ({name})")
                time.sleep(delay)
                continue
            raise RuntimeError(name + " call failed: " + str(err))
        sc = result.get("result", {}).get("structuredContent", {})
        return sc.get("data", sc)


def expected_codes(con, trade_date):
    """该交易日本地有K线的股票（6位代码）。作为策略B的名单和覆盖率基准。"""
    rows = con.execute(
        "SELECT DISTINCT thscode FROM v_daily_qfq WHERE date = ?", [trade_date]).fetchall()
    return [r[0].split(".")[0] for r in rows]


def _row_from_screener(r):
    return {
        "code": r.get("code"), "name": r.get("name"), "close": r.get("close"),
        "total_mv_yi": r.get("totalMarketCapYi"), "circ_mv_yi": r.get("circMarketCapYi"),
        "pe_ttm": r.get("peTtm"), "pb": r.get("pb"),
        "turnover_rate": r.get("turnoverRate"), "volume_ratio": r.get("volumeRatio"),
    }


def fetch_via_screener_page(trade_date, expected_count, budget):
    """
    策略A：市值降序游标分页。返回 (rows_by_code | None, calls_used)。首页0行=联表滞后。
    实测：无论 limit 传多少，raw 响应每页最多约75行（standard 50行），所以翻页终止
    不能看 len(rows)<limit，只能看"游标不再下降/无新增/覆盖已够"。约74次/交易日。
    """
    rows_by_code, calls, max_yi, prev_last = {}, 0, None, None
    while calls < budget:
        args = {"date": trade_date, "marketCapMinYi": 0.1,
                "sortBy": "totalMarketCapYi", "sortOrder": "desc",
                "limit": 300, "excludeST": False,
                "detailLevel": "raw", "format": "json"}
        if max_yi is not None:
            args["marketCapMaxYi"] = max_yi
        data = call_tool("stock_screener", args)
        calls += 1
        rows = data.get("rows", [])
        if not rows:
            return (rows_by_code or None), calls   # 首页空=该日联表滞后
        new = 0
        for r in rows:
            if r.get("code") and r["code"] not in rows_by_code:
                rows_by_code[r["code"]] = _row_from_screener(r)
                new += 1
        last = rows[-1].get("totalMarketCapYi")
        if (new == 0 or last is None
                or (prev_last is not None and last >= prev_last)   # 游标停滞护栏
                or len(rows_by_code) >= expected_count):
            break
        prev_last, max_yi = last, last
    return rows_by_code, calls


def _row_from_snapshot(item):
    stock = item.get("stock", {})
    tmv, cmv = item.get("totalMv"), item.get("circMv")
    return {
        "code": stock.get("code") or item.get("code"), "name": stock.get("name"),
        "close": item.get("close"),
        "total_mv_yi": tmv / 1e4 if tmv is not None else None,   # 万元 -> 亿元
        "circ_mv_yi": cmv / 1e4 if cmv is not None else None,
        "pe_ttm": item.get("peTtm"), "pb": item.get("pb"),
        "turnover_rate": item.get("turnoverRate"), "volume_ratio": item.get("volumeRatio"),
    }


def fetch_via_snapshot(trade_date, codes, budget):
    """
    策略B：valuation_snapshot 20只/批全量扫。返回 (rows_by_code, calls_used, exhausted)。
    实测持续高频扫全市场时，个别 item 会返回"只有股票身份、估值字段全 null"的瞬时缺失
    （同一代码稍后单查正常），故对 null 市值的代码做一轮二次补查。
    """
    rows_by_code, calls = {}, 0

    def _sweep(code_list):
        nonlocal calls
        for i in range(0, len(code_list), 20):
            if calls >= budget:
                return True
            data = call_tool("valuation_snapshot", {
                "codes": code_list[i:i + 20], "date": trade_date,
                "detailLevel": "raw", "format": "json"})
            calls += 1
            for item in data.get("items", []):
                row = _row_from_snapshot(item)
                if row["code"]:
                    rows_by_code[row["code"]] = row
        return False

    exhausted = _sweep(codes)
    if not exhausted:
        nulls = [c for c, r in rows_by_code.items() if r["total_mv_yi"] is None]
        if nulls:
            print(f"  [补查] {len(nulls)} 只市值为空，二次重查")
            exhausted = _sweep(nulls)
    return rows_by_code, calls, exhausted


def write_date(con, trade_date, rows_by_code, source):
    """
    合并式写入：不能用"新数据无脑 DELETE+INSERT"——valuation_snapshot 高频扫时
    个别 item 会瞬时返回 null 估值，若直接覆盖会把先前已入库的好数据打烂。
    规则：新值非空则用新值；新值为空但库里已有非空旧值则保留旧值。
    """
    existing = {r[0]: r for r in con.execute(
        "SELECT code, name, close, total_mv_yi, circ_mv_yi, pe_ttm, pb, turnover_rate, "
        "volume_ratio, source FROM valuation_daily WHERE trade_date = ? "
        "AND total_mv_yi IS NOT NULL", [trade_date]).fetchall()}
    now = datetime.now()
    out = []
    merged_from_old = 0
    for code, r in rows_by_code.items():
        if r["total_mv_yi"] is None and code in existing:
            e = existing[code]
            out.append([trade_date, code, e[1], e[2], e[3], e[4], e[5], e[6], e[7], e[8], e[9], now])
            merged_from_old += 1
        else:
            out.append([trade_date, code, r["name"], r["close"], r["total_mv_yi"], r["circ_mv_yi"],
                        r["pe_ttm"], r["pb"], r["turnover_rate"], r["volume_ratio"], source, now])
    # 库里有而本次没抓到的代码也保留
    for code, e in existing.items():
        if code not in rows_by_code:
            out.append([trade_date, code, e[1], e[2], e[3], e[4], e[5], e[6], e[7], e[8], e[9], now])
    con.execute("DELETE FROM valuation_daily WHERE trade_date = ?", [trade_date])
    con.executemany(
        "INSERT INTO valuation_daily VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", out)
    nulls = sum(1 for row in out if row[4] is None)
    if merged_from_old or nulls:
        print(f"  [合并写入] 沿用旧值 {merged_from_old} 只；写入后市值仍为空 {nulls} 只")


def ingest_date(con, trade_date, budget):
    """抓一个交易日。返回 (calls_used, status_str)。"""
    expected = expected_codes(con, trade_date)
    if not expected:
        return 0, "skip(no local kline)"

    rows, calls = fetch_via_screener_page(trade_date, len(expected), budget)
    if rows and len(rows) >= 0.8 * len(expected):
        # 游标分页在小市值尾部会因并列市值停滞，缺口用 valuation_snapshot 定向补齐
        missing = [c for c in expected if c not in rows]
        if missing and (budget - calls) >= (len(missing) + 19) // 20:
            extra, calls_c, _ = fetch_via_snapshot(trade_date, missing, budget - calls)
            calls += calls_c
            rows.update(extra)
            print(f"  [尾部补齐] 策略A缺 {len(missing)} 只，snapshot 补回 {len(extra)} 只")
        write_date(con, trade_date, rows, "screener_page")
        return calls, f"ok source=screener_page rows={len(rows)}/{len(expected)}"
    print(f"  [诊断] 策略A覆盖 {len(rows) if rows else 0}/{len(expected)}，回退策略B")

    # 策略A不可用/覆盖不足 -> 策略B（先检查预算够不够跑完，不够就整日跳过，避免白烧调用）
    need_b = (len(expected) + 19) // 20
    if budget - calls < need_b:
        return calls, f"deferred(策略B需{need_b}次、预算余{budget - calls}，整日跳过下次续跑)"
    rows_b, calls_b, _ = fetch_via_snapshot(trade_date, expected, budget - calls)
    calls += calls_b
    if not rows_b:
        return calls, "fail(两种策略均无数据)"
    write_date(con, trade_date, rows_b, "valuation_snapshot")
    return calls, f"ok source=valuation_snapshot rows={len(rows_b)}/{len(expected)}"


def main():
    if not KEY:
        raise SystemExit("WUDAO_API_KEY 未设置（环境变量或 ~/.env）。")
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", help="抓指定交易日 YYYY-MM-DD")
    ap.add_argument("--backfill", type=int, default=0,
                    help="回填最近N个交易日中 valuation_daily 缺失的（新日期优先）")
    ap.add_argument("--max-calls", type=int, default=1500, help="本次运行调用上限（配额护栏）")
    args = ap.parse_args()

    con = duckdb.connect(DB_PATH)
    con.execute(DDL)

    if args.date:
        dates = [args.date]
    else:
        n = max(args.backfill, 1)
        # 待处理 = 缺失的交易日 + 质量不达标的交易日（覆盖<90% 或 市值空值>10%），
        # 新日期优先。质量差的日期会被合并式写入逐次修复（自愈）。
        dates = [r[0].isoformat() for r in con.execute(
            """WITH recent AS (SELECT DISTINCT date FROM v_daily_qfq ORDER BY date DESC LIMIT ?),
               kcnt AS (SELECT date, count(*) AS n FROM v_daily_qfq
                        WHERE date IN (SELECT date FROM recent) GROUP BY date),
               vq AS (SELECT trade_date, count(*) AS n,
                             sum(CASE WHEN total_mv_yi IS NULL THEN 1 ELSE 0 END) AS null_n
                      FROM valuation_daily GROUP BY trade_date)
               SELECT k.date FROM kcnt k LEFT JOIN vq v ON v.trade_date = k.date
               WHERE v.trade_date IS NULL
                  OR v.n < 0.9 * k.n
                  OR v.null_n > 0.1 * v.n
               ORDER BY k.date DESC""", [n]).fetchall()]
        if not dates:
            print("最近", n, "个交易日均已入库且质量达标，无需抓取。")

    used = 0
    for d in dates:
        if used >= args.max_calls:
            print(f"配额护栏 {args.max_calls} 用尽，剩余日期下次续跑。")
            break
        calls, status = ingest_date(con, d, args.max_calls - used)
        used += calls
        print(f"{d}: {status} calls={calls} (累计 {used}/{args.max_calls})")

    total = con.execute("SELECT count(DISTINCT trade_date), count(*) FROM valuation_daily").fetchone()
    print(f"valuation_daily 现有 {total[0]} 个交易日 / {total[1]} 行。")
    con.close()


if __name__ == "__main__":
    main()
