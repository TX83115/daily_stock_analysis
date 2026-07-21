"""
fetch_valuation_daily.py
本地优先市值架构 v2："股本锚点 + 本地重构"，取代 v1 的"每日全市场快照"。

v1(2026-07-20/21) 为何演进到 v2：
市值 = 股本 x 收盘价。收盘价本地免费有(v_daily_qfq)；股本几乎不变——用 v1 已入库
的两个真实交易日交叉验证(07-10 反推股本 -> 乘以07-20收盘价 -> 与07-20真实入库市值
比对，跨7个交易日、零额外API调用)：98.4%的股票误差<0.1%，仅0.5%(真实送转/增发/
回购)误差超5%。v1"每天全量扫一遍市值"因此是浪费——真正需要按天刷新的只是股本，
而股本一周甚至更久刷一次都够用。

架构：
- shares_outstanding 表：每只股票的总/流通股本(亿股)，滚动刷新，不是每日快照。
- v_market_cap 视图：v_daily_qfq.close x shares_outstanding，任意(code,date)组合
  零查询成本、零存储增长地算出市值。
- valuation_daily 表(v1遗留，本文件不再写入)：已入库的真实交易日快照保留作地面
  真值 —— 免费一次性拿来反推初始股本(见 --bootstrap)，之后不再新增。

滚动节奏：一周一轮(用户确认)，每天刷新 1/7 全市场(约790只 ≈ 40次调用/天，
远低于悟道 50次/分钟+5000次/天配额)。刷新顺序=股本锚点最久未更新的排最前，
保证每只票至多约7天刷新一次；从未刷新过的(新股/未覆盖)优先级最高。

用法：
  python fetch_valuation_daily.py --bootstrap
      # 冷启动：从已入库 valuation_daily 免费反推初始股本(零API调用)，只需跑一次
  python fetch_valuation_daily.py
      # 日常调度：刷新最该更新的一批(默认 --daily-quota 40 ≈ 一周滚动全市场一轮)
  python fetch_valuation_daily.py --daily-quota 280
      # 一次性把全市场刷新一遍(~277次调用)

需环境变量 WUDAO_API_KEY。单位：股本=亿股，市值=亿元。
"""
import os, time, argparse, requests, duckdb
from datetime import datetime, date

KEY = os.environ.get("WUDAO_API_KEY")
MCP_URL = "https://stock.quicktiny.cn/api/mcp"
DB_PATH = "/Users/tx/market-data/market.duckdb"

# 悟道实测限速 50 次/分钟（-32028）。全局节流 + 命中限速时按 retryAfterMs 等待重试。
MIN_INTERVAL_S = 1.25
_last_call_at = [0.0]

DDL_SHARES = """
CREATE TABLE IF NOT EXISTS shares_outstanding (
    code             VARCHAR PRIMARY KEY,
    name             VARCHAR,
    total_shares_yi  DOUBLE,   -- 总股本，亿股
    circ_shares_yi   DOUBLE,   -- 流通股本，亿股
    as_of_date       DATE,     -- 该股本反推自哪个交易日的市值/收盘（锚点日）
    fetched_at       TIMESTAMP
)
"""

DDL_VIEW = """
CREATE OR REPLACE VIEW v_market_cap AS
SELECT
    substr(k.thscode, 1, 6) AS code,
    k.date AS trade_date,
    k.close,
    s.total_shares_yi * k.close AS total_mv_yi,
    s.circ_shares_yi * k.close AS circ_mv_yi,
    s.as_of_date AS shares_as_of_date
FROM v_daily_qfq k
JOIN shares_outstanding s ON s.code = substr(k.thscode, 1, 6)
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


def _table_exists(con, name):
    return con.execute(
        "SELECT 1 FROM information_schema.tables WHERE table_name = ?", [name]).fetchone() is not None


def bootstrap_from_valuation_daily(con):
    """
    冷启动：从 v1 已入库的 valuation_daily 真实快照，每只票取最新一条免费反推股本，
    零API调用。valuation_daily 不存在（全新环境）时跳过，回退到实时刷新覆盖。
    """
    if not _table_exists(con, "valuation_daily"):
        print("valuation_daily 表不存在，跳过免费引导，改用实时刷新覆盖全市场。")
        return 0
    rows = con.execute("""
        SELECT code, name, total_mv_yi / close AS total_shares_yi,
               circ_mv_yi / close AS circ_shares_yi, trade_date
        FROM (
            SELECT *, row_number() OVER (PARTITION BY code ORDER BY trade_date DESC) AS rn
            FROM valuation_daily
            WHERE close > 0 AND total_mv_yi IS NOT NULL AND total_mv_yi > 0
        ) WHERE rn = 1
    """).fetchall()
    if not rows:
        return 0
    codes = [r[0] for r in rows]
    now = datetime.now()
    con.execute(f"DELETE FROM shares_outstanding WHERE code IN ({','.join(['?'] * len(codes))})", codes)
    con.executemany(
        "INSERT INTO shares_outstanding VALUES (?, ?, ?, ?, ?, ?)",
        [[r[0], r[1], r[2], r[3], r[4], now] for r in rows])
    return len(rows)


def pick_codes_to_refresh(con, quota):
    """
    选出本轮该刷新的代码：从未刷新过的(锚点缺失)优先，其余按锚点日期升序
    (最久未刷新的优先)。quota 次调用 = quota*20 只代码。
    """
    limit = quota * 20
    latest_kline_date = con.execute("SELECT max(date) FROM v_daily_qfq").fetchone()[0]
    universe = [r[0] for r in con.execute(
        "SELECT DISTINCT substr(thscode, 1, 6) FROM v_daily_qfq WHERE date = ?",
        [latest_kline_date]).fetchall()]
    known = {r[0]: r[1] for r in con.execute(
        "SELECT code, as_of_date FROM shares_outstanding").fetchall()}
    ordered = sorted(universe, key=lambda c: (known.get(c) is not None, known.get(c) or date.min))
    return ordered[:limit]


def _shares_row_from_snapshot(item):
    stock = item.get("stock", {})
    code = stock.get("code") or item.get("code")
    close = item.get("close")
    tmv, cmv = item.get("totalMv"), item.get("circMv")   # 万元
    if not code or not close or close <= 0 or tmv is None:
        return None
    as_of = item.get("actualTradeDate")
    if as_of and len(as_of) == 8:
        as_of = f"{as_of[:4]}-{as_of[4:6]}-{as_of[6:]}"
    return {
        "code": code, "name": stock.get("name"),
        "total_shares_yi": (tmv / 1e4) / close,
        "circ_shares_yi": (cmv / 1e4) / close if cmv is not None else None,
        "as_of_date": as_of,
    }


def refresh_shares(con, codes, quota):
    """
    20只/批调用 valuation_snapshot(取最新交易日)反推股本并 upsert。个别瞬时空值
    (高频扫描时观测到)本轮跳过——它仍在 pick_codes_to_refresh 的"待刷新"队列里，
    下一轮自然重试，不需要在本函数内部重试。
    返回 (rows, calls_used)。
    """
    rows, calls = [], 0
    for i in range(0, len(codes), 20):
        if calls >= quota:
            break
        data = call_tool("valuation_snapshot", {
            "codes": codes[i:i + 20], "detailLevel": "raw", "format": "json"})
        calls += 1
        for item in data.get("items", []):
            r = _shares_row_from_snapshot(item)
            if r:
                rows.append(r)
    if rows:
        updated_codes = [r["code"] for r in rows]
        now = datetime.now()
        con.execute(
            f"DELETE FROM shares_outstanding WHERE code IN ({','.join(['?'] * len(updated_codes))})",
            updated_codes)
        con.executemany(
            "INSERT INTO shares_outstanding VALUES (?, ?, ?, ?, ?, ?)",
            [[r["code"], r["name"], r["total_shares_yi"], r["circ_shares_yi"], r["as_of_date"], now]
             for r in rows])
    return rows, calls


def main():
    if not KEY:
        raise SystemExit("WUDAO_API_KEY 未设置（环境变量或 ~/.env）。")
    ap = argparse.ArgumentParser()
    ap.add_argument("--daily-quota", type=int, default=40,
                    help="本次调用上限。默认40≈全市场一周滚动一轮(5523/20/7≈40)。")
    ap.add_argument("--bootstrap", action="store_true",
                    help="从已入库 valuation_daily 免费反推初始股本(零API调用)，仅需跑一次。")
    args = ap.parse_args()

    con = duckdb.connect(DB_PATH)
    con.execute(DDL_SHARES)

    if args.bootstrap:
        n = bootstrap_from_valuation_daily(con)
        print(f"从 valuation_daily 免费反推股本 {n} 只（零API调用）。")

    con.execute(DDL_VIEW)

    codes = pick_codes_to_refresh(con, args.daily_quota)
    if not codes:
        print("无待刷新代码。")
    else:
        rows, calls = refresh_shares(con, codes, args.daily_quota)
        print(f"本轮刷新 {len(rows)}/{len(codes)} 只股本，用了 {calls} 次调用。")

    total = con.execute(
        "SELECT count(*), min(as_of_date), max(as_of_date) FROM shares_outstanding").fetchone()
    print(f"shares_outstanding 现有 {total[0]} 只，最旧锚点 {total[1]}，最新锚点 {total[2]}。")
    con.close()


if __name__ == "__main__":
    main()
