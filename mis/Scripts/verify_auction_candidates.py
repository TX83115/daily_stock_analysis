"""
verify_auction_candidates.py
9:25 auction three-factor verification for today's focus_list_daily candidates
(both paths: dragon_weak_to_strong and breakout).

Three factors (from strategy doctrine, verified against raw Wudao fields,
NOT using Wudao's composite scores per L1 discipline - "others' judgments"
like wtsScore/sentimentSignal stay observation-only):

Factor 1 - auction volume >= 7% of yesterday's total volume:
  auction_market_scan gives bidAmountPercentile/bidAmountRatio, but these
  were found to be broken (stuck at -1/0) for the whole 2026-07-14 session
  even post-close (verified: generatedAt refreshed to 15:20 but values
  unchanged - this is a genuine data gap, not a caching/timing issue).
  Workaround: compute ratio ourselves using bidVolHands (auction volume in
  lots, from auction_market_scan) divided by the auction_volume_threshold
  we pre-computed and stored in focus_list_daily during screening
  (yesterday's total volume in lots * 7%, see screen_dragon_candidates.py
  and screen_breakout_candidates.py).

Factor 2 - opening price in expected zone:
  changeRate field (auction change %) from auction_market_scan.

Factor 3 - sustained accumulation through auction:
  limitBuyAmountAfter920 (verified working, real values present).

Type A script for now (manual run), will become Type B (Kimi Work,
scheduled ~9:26-9:30) later once verified stable across a few sessions.
"""
import os, json, requests, duckdb, sys
from datetime import date

KEY = os.environ.get("WUDAO_API_KEY")
MCP_URL = "https://stock.quicktiny.cn/api/mcp"
DB_PATH = "/Users/tx/market-data/market.duckdb"


def call_tool(name, arguments):
    resp = requests.post(MCP_URL,
        headers={"Authorization": "Bearer " + KEY, "Content-Type": "application/json"},
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/call",
              "params": {"name": name, "arguments": arguments}})
    result = resp.json()
    if "error" in result:
        raise RuntimeError(name + " call failed: " + str(result["error"]))
    sc = result.get("result", {}).get("structuredContent", {})
    return sc.get("data", sc)


def get_today_candidates(trade_date):
    con = duckdb.connect(DB_PATH, read_only=True)
    rows = con.execute(
        "SELECT code, name, path, auction_volume_threshold FROM focus_list_daily WHERE trade_date = ?",
        [trade_date]
    ).fetchall()
    con.close()
    return rows


def fetch_auction_data(codes):
    if not codes:
        return {}
    data = call_tool("auction_market_scan", {
        "codes": codes, "detailLevel": "raw", "format": "json"
    })
    rows = data.get("rows", [])
    result = {}
    for r in rows:
        result[r.get("code")] = r
    return result


def verify_candidate(code, name, path, threshold, auction_row):
    if auction_row is None:
        return {
            "code": code, "name": name, "path": path,
            "factor1": None, "factor2": None, "factor3": None,
            "all_pass": False, "note": "no auction data found for this code today"
        }

    bid_vol_hands = auction_row.get("bidVolHands")
    factor1 = None
    factor1_ratio = None
    if threshold and bid_vol_hands is not None and threshold > 0:
        factor1_ratio = bid_vol_hands / threshold
        factor1 = factor1_ratio >= 1.0
    else:
        factor1 = None

    change_rate = auction_row.get("changeRate")
    factor2 = change_rate is not None and change_rate > 0

    limit_buy_after_920 = auction_row.get("limitBuyAmountAfter920")
    factor3 = limit_buy_after_920 is not None and limit_buy_after_920 > 0

    all_pass = factor1 is True and factor2 is True and factor3 is True

    return {
        "code": code, "name": name, "path": path,
        "factor1": factor1, "factor1_ratio": round(factor1_ratio, 2) if factor1_ratio else None,
        "factor2": factor2, "changeRate": change_rate,
        "factor3": factor3, "limitBuyAmountAfter920": limit_buy_after_920,
        "all_pass": all_pass, "note": None
    }


def verify(trade_date):
    candidates = get_today_candidates(trade_date)
    print("candidates to verify:", len(candidates))
    if not candidates:
        return []

    codes = [c[0] for c in candidates]
    auction_data = fetch_auction_data(codes)

    results = []
    for code, name, path, threshold in candidates:
        auction_row = auction_data.get(code)
        result = verify_candidate(code, name, path, threshold, auction_row)
        results.append(result)

    return results


if __name__ == "__main__":
    # 计划日取法：focus_list_daily 里最新一批筛选结果的 trade_date（昨晚筛选=今天的
    # 盘中计划），而不是 date.today() —— 筛选写入的 trade_date 是"数据日"（上一交易
    # 日），日历今天永远查不到候选。可用命令行参数覆盖（复盘历史日用）。
    if len(sys.argv) > 1:
        plan_date = sys.argv[1]
    else:
        con = duckdb.connect(DB_PATH, read_only=True)
        row = con.execute("SELECT max(trade_date) FROM focus_list_daily").fetchone()
        con.close()
        if not row or row[0] is None:
            raise SystemExit("focus_list_daily 为空，无候选可验证。")
        plan_date = row[0].isoformat()
    print("Verifying candidates from screening date:", plan_date,
          "(auction data = today's live/latest)")
    results = verify(plan_date)
    print()
    for r in results:
        status = "PASS ALL 3" if r["all_pass"] else "not all pass"
        print(r["code"], r["name"], "(" + r["path"] + ")", "->", status)
        print("  factor1(volume):", r.get("factor1"), "ratio:", r.get("factor1_ratio"))
        print("  factor2(price):", r.get("factor2"), "changeRate:", r.get("changeRate"))
        print("  factor3(sustain):", r.get("factor3"), "limitBuyAfter920:", r.get("limitBuyAmountAfter920"))
        if r.get("note"):
            print("  note:", r["note"])
