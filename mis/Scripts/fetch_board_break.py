import requests
import duckdb
import json
import sys
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
    con.execute("""CREATE TABLE IF NOT EXISTS board_break_baseline (
        trade_date DATE, raw_json VARCHAR,
        fetched_at TIMESTAMP DEFAULT current_timestamp, source VARCHAR DEFAULT 'wudao')""")
    con.execute("""CREATE TABLE IF NOT EXISTS board_break_summary_daily (
        trade_date DATE, prev_date DATE,
        total_prev_limit_ups INTEGER, sealed_again_count INTEGER, broken_count INTEGER, missing_count INTEGER,
        break_rate DOUBLE, avg_broken_pct_chg DOUBLE,
        status_limit_down INTEGER, status_hard_break INTEGER, status_mild_break INTEGER,
        status_high_open_low_close INTEGER, status_flat INTEGER, status_red_close INTEGER,
        high_board_broken_count INTEGER, sentiment_signal VARCHAR,
        fetched_at TIMESTAMP DEFAULT current_timestamp)""")
    con.execute("""CREATE TABLE IF NOT EXISTS board_break_detail_daily (
        trade_date DATE, code VARCHAR, name VARCHAR,
        prev_streak INTEGER, prev_limit_up_type VARCHAR, prev_open_num INTEGER, prev_reason_type VARCHAR,
        industry VARCHAR, theme VARCHAR,
        sealed_again BOOLEAN, today_streak INTEGER, status VARCHAR,
        pct_chg DOUBLE, open_pct DOUBLE, high_pct DOUBLE, low_pct DOUBLE,
        turnover_rate DOUBLE, amount BIGINT, has_factor BOOLEAN,
        fetched_at TIMESTAMP DEFAULT current_timestamp)""")

def fetch_and_store(target_date: str):
    result = call_tool("board_break_analysis", {
        "tradeDate": target_date, "focus": "all", "limit": 300,
        "detailLevel": "raw", "format": "json"
    })

    sc = result["structuredContent"]
    data = sc["data"]
    raw = sc["rawData"]
    items = raw["items"]
    summary = data["summary"]

    td = normalize_date(data["tradeDate"])
    pd_ = normalize_date(data["prevDate"])

    print(f"=== {td} 汇总 ===")
    print(json.dumps(summary, ensure_ascii=False, indent=2))

    with duckdb.connect(DB_PATH) as con:
        ensure_tables(con)

        con.execute("DELETE FROM board_break_baseline WHERE trade_date = ?", [td])
        con.execute("INSERT INTO board_break_baseline (trade_date, raw_json) VALUES (?, ?)",
                    [td, json.dumps(result, ensure_ascii=False)])

        sb = summary["statusBreakdown"]
        con.execute("DELETE FROM board_break_summary_daily WHERE trade_date = ?", [td])
        con.execute("""INSERT INTO board_break_summary_daily VALUES
            (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, current_timestamp)""",
            [td, pd_, summary["totalPrevLimitUps"], summary["sealedAgainCount"],
             summary["brokenCount"], summary["missingCount"], summary["breakRate"],
             summary["avgBrokenPctChg"],
             sb.get("limit_down", 0), sb.get("hard_break", 0), sb.get("mild_break", 0),
             sb.get("high_open_low_close", 0), sb.get("flat", 0), sb.get("red_close", 0),
             summary["highBoardBrokenCount"], summary["sentimentSignal"]])

        con.execute("DELETE FROM board_break_detail_daily WHERE trade_date = ?", [td])
        for it in items:
            con.execute("""INSERT INTO board_break_detail_daily VALUES
                (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, current_timestamp)""",
                [td, it["code"], it["name"], it["prevStreak"], it.get("prevLimitUpType"),
                 it.get("prevOpenNum"), it.get("prevReasonType"), it.get("industry"), it.get("theme"),
                 it["sealedAgain"], it.get("todayStreak"), it["status"],
                 it["pctChg"], it.get("openPct"), it.get("highPct"), it.get("lowPct"),
                 it.get("turnoverRate"), it.get("amount"), it.get("hasFactor")])

    print(f"[{td}] board_break_analysis 已存档（3张表，{len(items)}条明细）")

if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else str(date.today())
    fetch_and_store(target)