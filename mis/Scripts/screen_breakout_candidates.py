"""
screen_breakout_candidates.py
P0-1 Breakout (VCP-style) candidate screener, rewritten on Wudao data.

Replaces the logic previously embedded in mis_daily.py (a temporary script
from the DSA split two weeks ago, running on akshare + Excel output).
mis_daily.py itself is NOT touched or retired - it continues running via
Kimi Work as a parallel reference source for cross-validation (dual-source
check), not part of the main decision chain.

Pipeline:
1. stock_screener: broad filter (market cap, volume ratio, above MA20,
   no recent limit-up) -> candidate pool (up to 100)
2. kline (batched, 20 codes/call): pull 100-day qfq daily bars for
   each candidate
3. VCP pattern check (reimplemented locally, not copied from mis_daily.py):
   - find up to 3 most recent local peaks in a lookback window
   - pullback % from each peak to subsequent low
   - require pullbacks decreasing (contracting volatility)
   - require no "second wave" breakout within the pattern window
   - require today's high > prior lookback high (fresh breakout)
4. Compute trigger_price_low (actual last pullback low, real price)
   and trigger_price_high (today's close) - both real values from kline,
   no approximation needed (this was the gap that blocked reusing
   mis_daily.py's output directly).
5. Cap at MAX_CANDIDATES, write into focus_list_daily with path='breakout'

Parameters are read from strategy_parameters table (param_set='vcp_breakout',
is_active=true), NOT hardcoded, per L5 parameter versioning discipline.

Type A script for now (manual run), will become Type B (Kimi Work) later.
"""
import os, json, requests, duckdb

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
    if len(bars) < 60:
        return None

    lookback = params["vcp_lookback_days"]
    recent_20 = bars[-20:]
    price_range_pct = (max(b["high"] for b in recent_20) - min(b["low"] for b in recent_20)) / \
                       (sum(b["close"] for b in recent_20) / len(recent_20)) * 100

    today = bars[-1]
    today_high = today.get("high")
    prior_high = max(b["high"] for b in bars[-(lookback + 1):-1])
    if today_high <= prior_high:
        return None

    today_close = today.get("close")
    prev_close = bars[-2].get("close")
    change_pct = (today_close - prev_close) / prev_close * 100
    if change_pct < params["close_pct_chg_min"]:
        return None

    peaks, is_decreasing = find_peaks_and_pullbacks(bars, lookback)
    if not peaks or not is_decreasing:
        return None
    if params["vcp_pullback_must_decrease"] and not is_decreasing:
        return None
    if peaks[0]["pullback_pct"] >= params["vcp_max_last_pullback_pct"]:
        return None

    if check_second_wave(bars, params):
        return None

    return {
        "code": code, "name": name,
        "today_close": today_close,
        "change_pct": round(change_pct, 2),
        "price_range_20d_pct": round(price_range_pct, 2),
        "pullbacks": [round(p["pullback_pct"], 2) for p in peaks],
        "trigger_price_low": round(peaks[0]["low_price"], 2),
        "trigger_price_high": round(today_close, 2),
        "candidate_level": "core" if peaks[0]["pullback_pct"] < 7 else "watch"
    }


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

    screener_rows = run_screener(params, trade_date)
    print("stock_screener candidates:", len(screener_rows))

    codes = [r["code"] for r in screener_rows]
    name_map = {r["code"]: r.get("name") for r in screener_rows}

    klines = batch_kline(codes, days=params["vcp_lookback_days"] + 60, max_rows=150)
    print("kline data retrieved for:", len(klines), "codes")

    candidates = []
    for code in codes:
        bars = klines.get(code)
        if not bars:
            continue
        result = analyze_vcp(code, name_map.get(code), bars, params)
        if result:
            candidates.append(result)

    print("VCP pattern matches:", len(candidates))

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

    return candidates


if __name__ == "__main__":
    # 交易日改为取本地 v_daily_qfq 的最新日期，而非 date.today()。
    # 原因：VCP 分析和竞价阈值都依赖本地 kline，其"最后一根"就是 v_daily_qfq 最新日；
    # 若用 date.today() 让 screener 过滤在更新的一天、而本地 kline 却停在更早一天，
    # 会造成 screener 日与 kline 日错位（且遇周末/节假日会取到无数据日）。
    con = duckdb.connect(DB_PATH, read_only=True)
    latest = con.execute("SELECT max(date) FROM v_daily_qfq").fetchone()[0]
    con.close()
    today = latest.isoformat()
    print("Using trade_date (latest in v_daily_qfq):", today)
    result = screen(today)
    print()
    print("final candidates:", len(result))
    for c in result:
        print(" ", c["code"], c["name"], "-", c["candidate_level"],
              "- pullbacks:", c["pullbacks"], "- trigger:", c["trigger_price_low"], "~", c["trigger_price_high"])
