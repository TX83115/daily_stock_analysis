import requests
import duckdb
import json
from datetime import date

WUDAO_URL = "https://stock.quicktiny.cn/api/mcp"
API_KEY = "lb_95edefd519bcfd361b1d008c205f07ff13488e696aa85914433ee589c695679c"
DB_PATH = "/Users/tx/market-data/market.duckdb"

def call_tool(tool_name, arguments):
    resp = requests.post(
        WUDAO_URL,
        headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/call",
              "params": {"name": tool_name, "arguments": arguments}},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    if "error" in data:
        raise RuntimeError(data["error"])
    return data["result"]

def normalize_date(d: str) -> str:
    d = d.replace("-", "")
    return f"{d[0:4]}-{d[4:6]}-{d[6:8]}"

def ensure_tables(con):
    con.execute("""CREATE TABLE IF NOT EXISTS sentiment_baseline (
        trade_date DATE, raw_stats VARCHAR, raw_ladder VARCHAR,
        fetched_at TIMESTAMP DEFAULT current_timestamp, source VARCHAR DEFAULT 'wudao')""")
    con.execute("""CREATE TABLE IF NOT EXISTS sentiment_daily (
        trade_date DATE, day_of_week VARCHAR,
        sealed_up INTEGER, touched_up INTEGER, broken_up INTEGER, seal_rate_up DOUBLE,
        sealed_down INTEGER, touched_down INTEGER, opened_down INTEGER, seal_rate_down DOUBLE,
        total_stocks INTEGER, max_board_level INTEGER,
        promo_1to2 DOUBLE, promo_2to3 DOUBLE, promo_3to4 DOUBLE, promo_high DOUBLE,
        prev_date DATE, fetched_at TIMESTAMP DEFAULT current_timestamp)""")
    con.execute("""CREATE TABLE IF NOT EXISTS board_summary_daily (
        trade_date DATE, board_level INTEGER, stock_count INTEGER)""")
    con.execute("""CREATE TABLE IF NOT EXISTS theme_summary_daily (
        trade_date DATE, theme VARCHAR, limit_up_count INTEGER, max_continue_num INTEGER)""")
    con.execute("""CREATE TABLE IF NOT EXISTS limit_up_leaders_daily (
        trade_date DATE, board_level INTEGER, code VARCHAR, name VARCHAR,
        change_percent DOUBLE, order_amount BIGINT, primary_theme VARCHAR, reason_type VARCHAR)""")

def fetch_and_store(target_date: str):
    stats = call_tool("limit_stats", {"date": target_date})
    ladder = call_tool("limit_up_ladder", {"date": target_date})

    print("=== 原始返回 ===")
    print(json.dumps(stats, ensure_ascii=False, indent=2))
    print(json.dumps(ladder, ensure_ascii=False, indent=2))

    s = stats["structuredContent"]["data"]
    l = ladder["structuredContent"]["data"]
    td = normalize_date(s["date"])

    with duckdb.connect(DB_PATH) as con:
        ensure_tables(con)

        con.execute("INSERT INTO sentiment_baseline (trade_date, raw_stats, raw_ladder) VALUES (?, ?, ?)",
                    [td, json.dumps(stats, ensure_ascii=False), json.dumps(ladder, ensure_ascii=False)])

        promo = l.get("emotionMetrics", {}).get("promotionRates", {})
        prev = l.get("emotionMetrics", {}).get("prevDate")
        board_levels = [b["level"] for b in l.get("boardSummary", [])]

        con.execute("DELETE FROM sentiment_daily WHERE trade_date = ?", [td])
        con.execute("""INSERT INTO sentiment_daily
            (trade_date, day_of_week, sealed_up, touched_up, broken_up, seal_rate_up,
             sealed_down, touched_down, opened_down, seal_rate_down,
             total_stocks, max_board_level, promo_1to2, promo_2to3, promo_3to4, promo_high, prev_date)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", [
            td, l.get("dayOfWeek"),
            s["sealedLimitUp"], s["touchedLimitUp"], s["brokenLimitUp"], s["limitUpSealRate"],
            s["sealedLimitDown"], s["touchedLimitDown"], s["openedLimitDown"], s["limitDownSealRate"],
            l.get("totalStocks"), max(board_levels, default=0),
            promo.get("1to2"), promo.get("2to3"), promo.get("3to4"), promo.get("high"),
            normalize_date(prev) if prev else None])

        con.execute("DELETE FROM board_summary_daily WHERE trade_date = ?", [td])
        for b in l.get("boardSummary", []):
            con.execute("INSERT INTO board_summary_daily VALUES (?, ?, ?)", [td, b["level"], b["count"]])

        con.execute("DELETE FROM theme_summary_daily WHERE trade_date = ?", [td])
        for t in l.get("primaryThemeStats", []):
            con.execute("INSERT INTO theme_summary_daily VALUES (?, ?, ?, ?)",
                        [td, t["theme"], t["limitUpCount"], t["maxContinueNum"]])

        con.execute("DELETE FROM limit_up_leaders_daily WHERE trade_date = ?", [td])
        for r in l.get("rows", []):
            con.execute("INSERT INTO limit_up_leaders_daily VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                        [td, r["level"], r["code"], r["name"], r["changePercent"],
                         r["orderAmount"], r.get("primaryTheme"), r.get("reasonType")])

    print(f"[{td}] 原始数据+结构化数据均已存档（5张表）")

if __name__ == "__main__":
    import sys
    target = sys.argv[1] if len(sys.argv) > 1 else str(date.today())
    fetch_and_store(target)