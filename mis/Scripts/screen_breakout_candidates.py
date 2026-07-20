"""
screen_breakout_candidates.py
P0-1 Breakout (VCP) candidate screener — 悟道 pre-filter + local-kline VCP.

合并说明（2026-07-20）：本脚本现为唯一的 VCP 筛选实现，已合并并取代
~/hithink-scripts/daily_screen.py（原挂 Kimi Work 17:10 定时任务的本地 SQL 版）。
daily_screen.py 只是"55日新高 + 近期涨幅不过热"的动量过滤，没有真正的收缩/量能/
市值逻辑；本脚本保留其两点独有闸门（近期涨幅上限、688/北交所硬排除）并继续产出
screen_result.json，其余以本脚本更完整的 VCP 逻辑为准。

Pipeline:
1. stock_screener: 宽口径粗筛（市值 50-300亿、量比、站上MA20、近N日无涨停）
   -> 候选池（≤100）。市值口径当日若滞后，改用 valuation_snapshot 逐票取当日真实市值。
2. 硬排除科创板(688/689)与北交所/老三板(8/4字头、920)（源自 daily_screen.py）。
3. 本地 kline（v_daily_qfq）拉 qfq 日线做 VCP 形态识别：
   - lookback 窗口内找最近 3 个局部高点，算每段回撤%
   - 要求回撤依次收缩（波动收缩）
   - 要求窗口内无"二波"放量突破
   - 要求今日高点 > 前 lookback 高点（新突破）
   - 近期涨幅不过热闸门（源自 daily_screen.py，阈值可调，见 params）
4. 计算 trigger_price_low/high（真实价，非近似）。
5. 取前 MAX_CANDIDATES，写入 focus_list_daily(path='breakout')，同时写 screen_result.json。

参数读自 strategy_parameters(param_set='vcp_breakout', is_active=true)，不写死，
遵循 L5 参数版本化。近期涨幅闸门阈值默认 3日<10% / 5日<20% / 10日<30%，可在
vcp_breakout 参数集里加 recent_gain_max_{3,5,10}d_pct 覆盖（见 analyze_vcp）。

运行：`python screen_breakout_candidates.py [YYYY-MM-DD]`，不带日期则取 v_daily_qfq 最新日。
需环境变量 WUDAO_API_KEY。
"""
import os, json, requests, duckdb, sys

SCREEN_RESULT_JSON = "/Users/tx/market-data/screen_result.json"

KEY = os.environ.get("WUDAO_API_KEY")
MCP_URL = "https://stock.quicktiny.cn/api/mcp"
DB_PATH = "/Users/tx/market-data/market.duckdb"


def load_active_params(param_set):
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


def _is_excluded_board(code):
    """
    硬排除科创板(688/689)与北交所/老三板(8字头/4字头/920)；创业板(300/301)保留。
    源自 daily_screen.py（原 exchange!='BJ' + NOT ticker LIKE '688%'）。
    本地 v_daily_qfq 对北交所覆盖不全，688 波动/涨跌幅规则也与主板/创业板不同。
    """
    c = str(code)
    return c[:3] in ("688", "689", "920") or c[:1] in ("4", "8")


def _to_thscode(code):
    return code + (".SH" if str(code).startswith("6") else ".SZ")


def write_screen_result_json(trade_date, candidates):
    """
    继续产出 /Users/tx/market-data/screen_result.json，保持对 Kimi Work 汇报/下游的
    兼容。字段是旧 daily_screen.py schema（thscode/name/close/pct_1d/3d/5d/10d）的超集，
    额外附带 VCP 字段；旧读取方按原字段名仍可用。
    """
    out = []
    for c in candidates:
        out.append({
            "thscode": _to_thscode(c["code"]),
            "name": c["name"],
            "close": c["today_close"],
            "pct_1d": c.get("pct_1d"),
            "pct_3d": c.get("pct_3d"),
            "pct_5d": c.get("pct_5d"),
            "pct_10d": c.get("pct_10d"),
            "pullbacks": c["pullbacks"],
            "trigger_price_low": c["trigger_price_low"],
            "trigger_price_high": c["trigger_price_high"],
            "candidate_level": c["candidate_level"],
        })
    with open(SCREEN_RESULT_JSON, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"screen_result.json written: {len(out)} rows -> {SCREEN_RESULT_JSON}")


def _cap_available(trade_date):
    """
    探测 stock_screener 在某交易日上 marketCap 过滤/字段是否可用。

    已验证（2026-07-20）：stock_screener 的 totalMarketCapYi/circMarketCapYi 字段和
    marketCapMinYi/MaxYi 过滤，在最近几个交易日会整体缺失（字段静默消失，任何市值
    过滤条件静默命中 0 行）。但同属悟道的 valuation_snapshot 工具（读 daily_basic）
    在同一批交易日上市值数据是新鲜的 —— 说明底层数据并不缺，只是 stock_screener
    自己的市值字段/过滤联表滞后。因此不做"回退到更早交易日"这种降级，而是改用
    valuation_snapshot 对候选票做当日市值过滤（见 _filter_by_valuation_snapshot）。
    """
    data = call_tool("stock_screener", {
        "codes": ["600519"], "date": trade_date,
        "marketCapMinYi": 1, "detailLevel": "raw", "format": "json"})
    return len(data.get("rows", [])) > 0


def _valuation_market_cap_yi(item, market_cap_type):
    """valuation_snapshot 返回的 totalMv/circMv 单位是万元，换算成亿元。"""
    key = "circMv" if market_cap_type == "circ" else "totalMv"
    v = item.get(key)
    return v / 10000.0 if v is not None else None


def _filter_by_valuation_snapshot(rows, trade_date, cap_min_yi, cap_max_yi, market_cap_type):
    """
    用 valuation_snapshot（逐票查询，单批最多20只）对候选池做当日市值过滤。
    这是 stock_screener 市值字段滞后时的正式取数路径，不是"用旧数据将就"的降级。
    """
    codes = [r["code"] for r in rows]
    cap_by_code = {}
    for i in range(0, len(codes), 20):
        batch = codes[i:i + 20]
        data = call_tool("valuation_snapshot", {
            "codes": batch, "date": trade_date, "detailLevel": "raw", "format": "json"})
        for item in data.get("items", data.get("rows", [])):
            code = item.get("stock", {}).get("code") or item.get("code")
            if code:
                cap_by_code[code] = _valuation_market_cap_yi(item, market_cap_type)

    kept = []
    for r in rows:
        cap = cap_by_code.get(r["code"])
        if cap is None:
            continue  # valuation_snapshot 也取不到该票市值，视为未通过过滤
        if cap_min_yi is not None and cap < cap_min_yi:
            continue
        if cap_max_yi is not None and cap > cap_max_yi:
            continue
        kept.append(r)
    return kept


def _cap_by_code_local(trade_date, market_cap_type):
    """
    P1 本地优先：从 valuation_daily（fetch_valuation_daily.py 每日快照）读市值。
    返回 {code: cap_yi}；该日未入库则返回空 dict（调用方回退实时接口）。
    """
    col = "circ_mv_yi" if market_cap_type == "circ" else "total_mv_yi"
    con = duckdb.connect(DB_PATH, read_only=True)
    rows = con.execute(
        f"SELECT code, {col} FROM valuation_daily WHERE trade_date = ?", [trade_date]).fetchall()
    con.close()
    return {r[0]: r[1] for r in rows if r[1] is not None}


def run_screener(params, trade_date):
    # 技术/价格类过滤条件（不依赖市值因子）
    tech_args = {
        "date": trade_date,
        "closePctChgMin": params["close_pct_chg_min"],
        "volumeRatioMin": params["volume_ratio_min"],
        "volumeAvgDays": params["volume_avg_days"],
        "aboveMa": params["above_ma"],
        "limitUpCountNdDays": params["limit_up_count_nd_days"],
        "limitUpCountNdMax": params["limit_up_count_nd_max"],
        "excludeST": True,
        "limit": params["screener_limit"],
        "detailLevel": "raw",
        "format": "json",
    }
    cap_args = {
        "marketCapType": params["market_cap_type"],
        "marketCapMinYi": params["market_cap_min_yi"],
        "marketCapMaxYi": params["market_cap_max_yi"],
    }

    # P1 本地优先：valuation_daily 已有该日快照 -> 技术过滤后直接本地过市值。
    # 本地缺市值的个别代码（快照瞬时缺失/新股）用 valuation_snapshot 小批量补齐，
    # 不静默排除。
    local_caps = _cap_by_code_local(trade_date, params["market_cap_type"])
    if local_caps:
        tech_rows = call_tool("stock_screener", tech_args).get("rows", [])
        missing = [r["code"] for r in tech_rows if r["code"] not in local_caps]
        if missing:
            key = "circMv" if params["market_cap_type"] == "circ" else "totalMv"
            for i in range(0, len(missing), 20):
                data = call_tool("valuation_snapshot", {
                    "codes": missing[i:i + 20], "date": trade_date,
                    "detailLevel": "raw", "format": "json"})
                for item in data.get("items", []):
                    c = item.get("stock", {}).get("code")
                    v = item.get(key)
                    if c and v is not None:
                        local_caps[c] = v / 1e4
            print(f"市值过滤: 本地缺 {len(missing)} 只，已实时补查")
        lo, hi = params["market_cap_min_yi"], params["market_cap_max_yi"]
        filtered = [r for r in tech_rows
                    if r["code"] in local_caps and lo <= local_caps[r["code"]] <= hi]
        print(f"市值过滤: 本地 valuation_daily({trade_date})；"
              f"技术候选={len(tech_rows)} -> 市值通过={len(filtered)}")
        return filtered

    # 本地无该日快照 -> 原有实时路径。
    # 正常路径：stock_screener 自身市值字段当日可用，单次调用带全部过滤条件。
    if _cap_available(trade_date):
        data = call_tool("stock_screener", {**tech_args, **cap_args})
        return data.get("rows", [])

    # stock_screener 市值联表滞后：先跑技术过滤拿候选池，再用 valuation_snapshot
    # 查这批候选当日（trade_date）的真实市值做过滤 —— 数据仍是当日的，不是旧数据。
    tech_rows = call_tool("stock_screener", tech_args).get("rows", [])
    if not tech_rows:
        return []
    filtered = _filter_by_valuation_snapshot(
        tech_rows, trade_date,
        params["market_cap_min_yi"], params["market_cap_max_yi"], params["market_cap_type"])
    print(f"WARN: {trade_date} stock_screener 市值字段滞后，改用 valuation_snapshot 逐票核验当日市值；"
          f"技术候选={len(tech_rows)} -> 市值通过={len(filtered)}")
    return filtered


def batch_kline(codes, days, max_rows):
    """
    Historical kline retrieval, now sourced from local DuckDB (v_daily_qfq)
    instead of the Wudao kline tool.

    Design change 2026-07-14 (per user's architectural observation):
    v_daily_qfq is a locally-maintained view (fed by marketdb/Fuyao,
    independent of Wudao) covering 5527 stocks from 2016 to present,
    updated daily. Since this local table already exists and is kept
    current by an unrelated pipeline, there is no need to call Wudao's
    kline tool for historical VCP analysis at all - doing so introduced
    a batch-size/response-truncation problem (kline tool silently caps
    total rows returned across a batch call, observed failing at
    batch_size=3+ with days=100). Querying local DuckDB has no such limit
    and is faster. Wudao kline is no longer used in this script's data path.

    codes here are plain 6-digit codes (no exchange suffix); v_daily_qfq
    stores thscode with .SZ/.SH suffix, so we convert before querying.
    """
    con = duckdb.connect(DB_PATH, read_only=True)
    all_klines = {}
    for code in codes:
        if code.startswith("6"):
            ths_code = code + ".SH"
        else:
            ths_code = code + ".SZ"
        rows = con.execute(
            "SELECT date, open, high, low, close, volume FROM v_daily_qfq "
            "WHERE thscode = ? ORDER BY date DESC LIMIT ?",
            [ths_code, days]
        ).fetchall()
        if not rows:
            continue
        rows = list(reversed(rows))
        series = []
        for r in rows:
            series.append({
                "date": r[0].strftime("%Y%m%d"),
                "open": r[1], "high": r[2], "low": r[3], "close": r[4],
                "volume": r[5]
            })
        all_klines[code] = series
    con.close()
    return all_klines


def find_peaks_and_pullbacks(bars, lookback_days):
    recent = bars[-lookback_days:] if len(bars) > lookback_days else bars
    if len(recent) < 20:
        return [], False

    highs = [b.get("high") for b in recent]
    lows = [b.get("low") for b in recent]

    peaks = []
    for i in range(2, len(recent) - 2):
        if (highs[i] > highs[i - 1] and highs[i] > highs[i - 2] and
            highs[i] > highs[i + 1] and highs[i] > highs[i + 2]):
            peak_price = highs[i]
            subsequent_low = min(lows[i:])
            pullback_pct = (peak_price - subsequent_low) / peak_price * 100
            peaks.append({"idx": i, "peak_price": peak_price,
                          "low_price": subsequent_low, "pullback_pct": pullback_pct})

    peaks = sorted(peaks, key=lambda x: x["idx"], reverse=True)[:3]
    if len(peaks) < 3:
        return [], False

    pullback_pcts = [p["pullback_pct"] for p in peaks]
    is_decreasing = pullback_pcts[0] > pullback_pcts[1] > pullback_pcts[2]
    return peaks, is_decreasing


def check_second_wave(bars, params):
    window = params["second_wave_check_days"]
    if len(bars) < window + 10:
        return False
    check_bars = bars[-(window + 1):-1]
    if len(check_bars) < 10:
        return False

    volumes = [b.get("volume", b.get("amount", 0)) for b in check_bars]

    for i in range(10, len(check_bars)):
        day = check_bars[i]
        prev = check_bars[i - 1]
        prev_close = prev.get("close")
        day_close = day.get("close")
        if not prev_close or prev_close == 0:
            continue
        change_pct = (day_close - prev_close) / prev_close * 100
        if change_pct < params["second_wave_change_min_pct"]:
            continue

        recent_high = max(b.get("high", 0) for b in check_bars[max(0, i - 19):i])
        if day.get("high", 0) <= recent_high:
            continue

        ma10_window = volumes[max(0, i - 10):i]
        if len(ma10_window) < 10:
            continue
        ma10_vol = sum(ma10_window) / len(ma10_window)
        if ma10_vol == 0:
            continue
        vol_ratio = volumes[i] / ma10_vol
        if vol_ratio >= params["second_wave_volume_ratio_min"]:
            return True
    return False


def analyze_vcp(code, name, bars, params):
    """
    返回 (candidate_dict | None, reason)。reason 标注"死在哪一步"，用于 screen() 汇总
    每步淘汰数的漏斗诊断（源自 principle #2 对"死在哪一步"诊断的偏好）。
    """
    if len(bars) < 60:
        return None, "too_short"

    lookback = params["vcp_lookback_days"]
    recent_20 = bars[-20:]
    price_range_pct = (max(b["high"] for b in recent_20) - min(b["low"] for b in recent_20)) / \
                       (sum(b["close"] for b in recent_20) / len(recent_20)) * 100

    today = bars[-1]
    today_high = today.get("high")
    prior_high = max(b["high"] for b in bars[-(lookback + 1):-1])
    if today_high <= prior_high:
        return None, "not_fresh_high"

    today_close = today.get("close")
    prev_close = bars[-2].get("close")
    change_pct = (today_close - prev_close) / prev_close * 100
    if change_pct < params["close_pct_chg_min"]:
        return None, "change_pct_low"

    # 近期涨幅不过热闸门（源自 daily_screen.py）。阈值可调：默认 3日<10% / 5日<20% /
    # 10日<30%，在 strategy_parameters 的 vcp_breakout 里加 recent_gain_max_{3,5,10}d_pct
    # 即可覆盖并纳入版本管理。作用：滤掉已连续大涨、追高风险高的票。
    def _pct_ago(n):
        if len(bars) > n and bars[-1 - n].get("close"):
            return (today_close - bars[-1 - n]["close"]) / bars[-1 - n]["close"] * 100
        return None
    pct_3d, pct_5d, pct_10d = _pct_ago(3), _pct_ago(5), _pct_ago(10)
    max_3d = params.get("recent_gain_max_3d_pct", 10.0)
    max_5d = params.get("recent_gain_max_5d_pct", 20.0)
    max_10d = params.get("recent_gain_max_10d_pct", 30.0)
    if (pct_3d is not None and pct_3d >= max_3d) or \
       (pct_5d is not None and pct_5d >= max_5d) or \
       (pct_10d is not None and pct_10d >= max_10d):
        return None, "overextended"

    peaks, is_decreasing = find_peaks_and_pullbacks(bars, lookback)
    if not peaks:
        return None, "peaks_lt_3"
    if params["vcp_pullback_must_decrease"] and not is_decreasing:
        return None, "not_decreasing"
    if peaks[0]["pullback_pct"] >= params["vcp_max_last_pullback_pct"]:
        return None, "last_pullback_too_big"

    if check_second_wave(bars, params):
        return None, "second_wave"

    return {
        "code": code, "name": name,
        "today_close": today_close,
        "change_pct": round(change_pct, 2),
        "pct_1d": round(change_pct, 2),
        "pct_3d": round(pct_3d, 2) if pct_3d is not None else None,
        "pct_5d": round(pct_5d, 2) if pct_5d is not None else None,
        "pct_10d": round(pct_10d, 2) if pct_10d is not None else None,
        "price_range_20d_pct": round(price_range_pct, 2),
        "pullbacks": [round(p["pullback_pct"], 2) for p in peaks],
        "trigger_price_low": round(peaks[0]["low_price"], 2),
        "trigger_price_high": round(today_close, 2),
        "candidate_level": "core" if peaks[0]["pullback_pct"] < 7 else "watch"
    }, "ok"


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
    return int(lots * 0.07)


def screen(trade_date):
    params = load_active_params("vcp_breakout")
    print("using vcp_breakout params version:", params["_version"])
    print("recent-gain guard (可调): 3d<%s%% 5d<%s%% 10d<%s%%" % (
        params.get("recent_gain_max_3d_pct", 10.0),
        params.get("recent_gain_max_5d_pct", 20.0),
        params.get("recent_gain_max_10d_pct", 30.0)))

    screener_rows = run_screener(params, trade_date)
    print("stock_screener candidates:", len(screener_rows))

    # 硬排除科创板/北交所（源自 daily_screen.py）
    kept_rows = [r for r in screener_rows if not _is_excluded_board(r["code"])]
    if len(kept_rows) != len(screener_rows):
        print("excluded 科创板/北交所:", len(screener_rows) - len(kept_rows),
              "-> pool:", len(kept_rows))
    codes = [r["code"] for r in kept_rows]
    name_map = {r["code"]: r.get("name") for r in kept_rows}

    klines = batch_kline(codes, days=params["vcp_lookback_days"] + 60, max_rows=150)
    print("kline data retrieved for:", len(klines), "codes")

    candidates = []
    reject_funnel = {}
    for code in codes:
        bars = klines.get(code)
        if not bars:
            reject_funnel["no_kline"] = reject_funnel.get("no_kline", 0) + 1
            continue
        result, reason = analyze_vcp(code, name_map.get(code), bars, params)
        reject_funnel[reason] = reject_funnel.get(reason, 0) + 1
        if result:
            candidates.append(result)

    print("VCP pattern matches:", len(candidates))
    # "死在哪一步"漏斗：每步淘汰数（含 ok=通过），用于判断 0 候选是真无票还是卡在某步
    print("VCP reject funnel:", {k: reject_funnel[k] for k in sorted(reject_funnel)})

    candidates.sort(key=lambda x: x["pullbacks"][0])
    candidates = candidates[:params["max_candidates"]]

    con = duckdb.connect(DB_PATH)
    con.execute("DELETE FROM focus_list_daily WHERE trade_date = ? AND path = ?", [trade_date, "breakout"])

    for c in candidates:
        threshold = compute_auction_threshold(con, c["code"], trade_date)
        reason = "vcp_level=" + c["candidate_level"] + " pullbacks=" + str(c["pullbacks"])
        con.execute(
            "INSERT INTO focus_list_daily (trade_date, code, name, path, reason, trigger_price_low, trigger_price_high, auction_volume_threshold) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [trade_date, c["code"], c["name"], "breakout", reason,
             c["trigger_price_low"], c["trigger_price_high"], threshold]
        )
    con.close()

    # 兼容产出：同时写 screen_result.json（供 Kimi Work 汇报/下游读取）
    write_screen_result_json(trade_date, candidates)

    return candidates


if __name__ == "__main__":
    # 交易日：优先命令行参数（如 2026-07-17），否则取本地 v_daily_qfq 最新日。
    # 不用 date.today()：VCP 分析和竞价阈值都依赖本地 kline，其"最后一根"就是
    # v_daily_qfq 最新日；若 screener 过滤在更新的一天、而本地 kline 停在更早一天，
    # 会造成 screener 日与 kline 日错位（且遇周末/节假日会取到无数据日）。
    if not KEY:
        raise SystemExit("WUDAO_API_KEY 未设置。本脚本依赖悟道 stock_screener/valuation_snapshot，"
                         "请在环境变量或 ~/.env 中提供 WUDAO_API_KEY 后再运行。")
    if len(sys.argv) > 1:
        today = sys.argv[1]
    else:
        con = duckdb.connect(DB_PATH, read_only=True)
        latest = con.execute("SELECT max(date) FROM v_daily_qfq").fetchone()[0]
        con.close()
        today = latest.isoformat()
    print("Using trade_date:", today)
    result = screen(today)
    print()
    print("final candidates:", len(result))
    for c in result:
        print(" ", c["code"], c["name"], "-", c["candidate_level"],
              "- pullbacks:", c["pullbacks"], "- trigger:", c["trigger_price_low"], "~", c["trigger_price_high"])
