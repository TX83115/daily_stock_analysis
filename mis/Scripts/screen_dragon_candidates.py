"""
screen_dragon_candidates.py (v4)
P0-1 Dragon-head next-day weak-to-strong candidate screener

v4 changes from v3:
- broken_up pool now gets theme attribution via reverse lookup:
  pull active themes from theme_intraday_capital, then theme_stocks
  for each theme to build code->theme map, until broken_up codes covered
  or theme pool exhausted. This closes the gap documented in v3
  (previously broken_up candidates had sub_sector=None).
- peer_competitors for broken_up now also uses theme_stocks full roster
  (not just the 2-3 sample stocks from primaryThemeStats).
- Quota is no longer a constraint (professional tier, 2000 calls/day,
  30/sec), so this function is intentionally not call-count-optimized.

Pipeline:
1. Get today's broken_limit_up pool (broken_up) and yesterday's ladder
   to compute broken_board list (excluding overlap with broken_up)
2. For broken_board: filter by sector front-rank via primaryThemeStats
3. For broken_up: reverse-lookup theme via theme_intraday_capital +
   theme_stocks, then also apply front-rank filter if theme found
4. Merge both pools, cap at 5 candidates total
5. Compute auction volume threshold = yesterday's total volume (shares/100) * 7%
6. Write results into focus_list_daily

Type: will become Type B script later. Type A for now.
"""
import os, json, requests, duckdb, time

KEY = os.environ.get("WUDAO_API_KEY")
MCP_URL = "https://stock.quicktiny.cn/api/mcp"
DB_PATH = "/Users/tx/market-data/market.duckdb"


def load_active_params(param_set):
    """L5 参数纪律：参数读 strategy_parameters 表，不硬编码（与 breakout 一致）。"""
    con = duckdb.connect(DB_PATH, read_only=True)
    row = con.execute(
        "SELECT params_json, version FROM strategy_parameters WHERE param_set = ? AND is_active = TRUE",
        [param_set]
    ).fetchone()
    con.close()
    if not row:
        raise RuntimeError("No active parameter set found for: " + param_set)
    params = json.loads(row[0])
    params["_version"] = row[1]
    return params


_P = load_active_params("dragon_weak_to_strong")
MAX_CANDIDATES = _P["max_candidates"]
FRONT_RANK_MIN_THEME_LIMITUP = _P["front_rank_min_theme_limitup"]
THEME_REVERSE_LOOKUP_MAX_THEMES = _P["theme_reverse_lookup_max_themes"]
print("using dragon_weak_to_strong params version:", _P["_version"])


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


def get_broken_limit_up(trade_date):
    data = call_tool("broken_limit_up", {"date": trade_date, "detailLevel": "raw", "format": "json"})
    return data.get("rows", [])


def get_limit_up_ladder(trade_date):
    data = call_tool("limit_up_ladder", {"date": trade_date, "maxRowsPerLevel": 50,
                                          "detailLevel": "raw", "format": "json"})
    return data


def find_broken_board(prior_date, target_date, broken_up_codes):
    prior_data = get_limit_up_ladder(prior_date)
    target_data = get_limit_up_ladder(target_date)

    prior_codes = set()
    for r in prior_data.get("rows", []):
        if r.get("level", 0) >= 2:
            prior_codes.add(r["code"])

    target_codes = set()
    for r in target_data.get("rows", []):
        target_codes.add(r["code"])

    broken_codes = prior_codes - target_codes - broken_up_codes

    prior_rows_map = {}
    for r in prior_data.get("rows", []):
        prior_rows_map[r["code"]] = r

    result = []
    for code in broken_codes:
        r = prior_rows_map[code]
        result.append(r)
    return result, target_data


def filter_front_rank(rows, ladder_data):
    theme_stats = {}
    for item in ladder_data.get("primaryThemeStats", []):
        theme_stats[item["theme"]] = item

    filtered = []
    for r in rows:
        theme = r.get("primaryTheme")
        stats = theme_stats.get(theme)
        if stats and stats.get("limitUpCount", 0) >= FRONT_RANK_MIN_THEME_LIMITUP:
            entry = dict(r)
            entry["theme_limitup_count"] = stats.get("limitUpCount")
            entry["theme_max_continue"] = stats.get("maxContinueNum")
            entry["sample_peers"] = stats.get("sampleStocks", [])
            filtered.append(entry)
    return filtered


def build_theme_reverse_map(trade_date, target_codes):
    """
    Reverse-lookup which theme each target code belongs to, by pulling
    active themes and their full stock rosters until all target codes
    are covered or theme pool is exhausted.
    Returns: dict code -> {theme_name, theme_code, roster (list of peer stocks)}
    """
    theme_data = call_tool("theme_intraday_capital", {
        "tradeDate": trade_date, "sortBy": "strength",
        "limit": 100, "detailLevel": "raw", "format": "json"
    })
    themes = theme_data.get("rows", [])[:THEME_REVERSE_LOOKUP_MAX_THEMES]

    remaining = set(target_codes)
    result_map = {}

    for t in themes:
        if not remaining:
            break
        theme_code = t.get("themeCode")
        theme_name = t.get("themeName")
        time.sleep(1.5)
        stocks_data = call_tool("theme_stocks", {
            "themeCode": theme_code, "tradeDate": trade_date.replace("-", ""),
            "limit": 300, "detailLevel": "raw", "format": "json"
        })
        rows = stocks_data.get("rows", stocks_data.get("items", []))

        roster = []
        codes_in_theme = set()
        for s in rows:
            c = s.get("code")
            codes_in_theme.add(c)
            roster.append({"code": c, "name": s.get("name"), "continueNum": s.get("continueNum")})

        hit = remaining & codes_in_theme
        for code in hit:
            result_map[code] = {
                "theme_name": theme_name,
                "theme_code": theme_code,
                "theme_limitup_count": t.get("limitUpCount"),
                "roster": roster
            }
        remaining = remaining - hit

    return result_map


def rank_broken_up_by_quality(rows, theme_map):
    scored = []
    for r in rows:
        suc_rate = r.get("limitUpSucRate")
        open_num = r.get("openNum", 999)
        if suc_rate is None:
            continue
        score = suc_rate - (open_num * 0.01)
        entry = dict(r)
        entry["quality_score"] = score
        theme_info = theme_map.get(r["code"])
        if theme_info:
            entry["primaryTheme"] = theme_info["theme_name"]
            entry["sample_peers"] = theme_info["roster"]
            entry["theme_limitup_count"] = theme_info["theme_limitup_count"]
        else:
            entry["primaryTheme"] = None
            entry["sample_peers"] = []
            entry["theme_limitup_count"] = None
        scored.append(entry)
    scored.sort(key=lambda x: (x["primaryTheme"] is None, -x["quality_score"]))
    return scored


def compute_auction_threshold(con, code, trade_date):
    if code.startswith("6"):
        ths_code = code + ".SH"
    else:
        ths_code = code + ".SZ"
    row = con.execute(
        "SELECT volume FROM v_daily_qfq WHERE thscode = ? AND date = ?",
        [ths_code, trade_date]
    ).fetchone()
    if not row or row[0] is None:
        return None
    shares = row[0]
    lots = shares / 100
    threshold = lots * 0.07
    return int(threshold)


def screen(data_date, prev_date):
    """
    data_date = 最新已收盘交易日（数据日，也是落库 trade_date，代表"为下一交易日做的
    计划"）；prev_date = 再前一个交易日，仅用于 broken_board 的梯队对比。

    取数日修复（2026-07-21）：原实现把炸板数据日错设为 yesterday(rows[1])、落库日设为
    today(rows[0])，人为拆成两天，导致"昨日炸板→今日弱转强"实际取到的是上上个交易日的
    炸板池（周一晚筛选却用周五的炸板）。现对齐 breakout / verify_auction 口径：炸板数据、
    题材反查、竞价阈值、落库 trade_date 全部用 data_date(最新交易日)，broken_board 比较
    prev_date→data_date。必须在日K同步后运行（daily_update.sh 链内），否则 rows[0] 仍是
    上一交易日。
    """
    broken_up = get_broken_limit_up(data_date)
    broken_up_codes = set()
    for r in broken_up:
        broken_up_codes.add(r["code"])

    broken_board_raw, ladder_data = find_broken_board(prev_date, data_date, broken_up_codes)
    broken_board_filtered = filter_front_rank(broken_board_raw, ladder_data)

    theme_map = build_theme_reverse_map(data_date, broken_up_codes)
    broken_up_with_theme = rank_broken_up_by_quality(broken_up, theme_map)

    matched_count = sum(1 for r in broken_up_with_theme if r.get("primaryTheme"))
    print("broken_up theme coverage:", matched_count, "/", len(broken_up_with_theme))

    candidates = []
    for r in broken_board_filtered:
        candidates.append({
            "code": r["code"], "name": r.get("name"),
            "prior_weakness_type": "broken_board",
            "sub_sector": r.get("primaryTheme"),
            "peer_competitors": json.dumps(r.get("sample_peers", []), ensure_ascii=False),
        })

    for r in broken_up_with_theme:
        candidates.append({
            "code": r["code"], "name": r.get("name"),
            "prior_weakness_type": "broken_up",
            "sub_sector": r.get("primaryTheme"),
            "peer_competitors": json.dumps(r.get("sample_peers", []), ensure_ascii=False) if r.get("sample_peers") else None,
        })

    candidates = candidates[:MAX_CANDIDATES]

    con = duckdb.connect(DB_PATH)
    con.execute("DELETE FROM focus_list_daily WHERE trade_date = ? AND path = ?", [data_date, "dragon_weak_to_strong"])

    for c in candidates:
        threshold = compute_auction_threshold(con, c["code"], data_date)
        trade_id_reason = "weakness_type=" + c["prior_weakness_type"]
        con.execute(
            "INSERT INTO focus_list_daily (trade_date, code, name, path, reason, prior_weakness_type, sub_sector, peer_competitors, auction_volume_threshold) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [data_date, c["code"], c["name"], "dragon_weak_to_strong", trade_id_reason,
             c["prior_weakness_type"], c["sub_sector"], c["peer_competitors"], threshold]
        )
    con.close()

    return candidates


if __name__ == "__main__":
    # 交易日从本地 v_daily_qfq 动态解析。data_date=最新交易日(需日K已同步，故本脚本应在
    # daily_update.sh 的 auto-sync 之后运行)，prev_date=再前一交易日(仅供 broken_board 对比)。
    con = duckdb.connect(DB_PATH, read_only=True)
    rows = con.execute(
        "SELECT DISTINCT date FROM v_daily_qfq ORDER BY date DESC LIMIT 2"
    ).fetchall()
    con.close()
    if len(rows) < 2:
        raise RuntimeError("Need at least 2 trading dates in v_daily_qfq")

    data_date = rows[0][0].isoformat()
    prev_date = rows[1][0].isoformat()

    print("Using trading dates -> data_date:", data_date, "prev_date:", prev_date)

    result = screen(data_date, prev_date)
    print()
    print("candidates found:", len(result))
    for c in result:
        print(" ", c["code"], c["name"], "-", c["prior_weakness_type"], "-", c["sub_sector"])
