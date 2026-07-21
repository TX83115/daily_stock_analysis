"""
intraday_brief.py
盘中简报器 + 5分钟级条件警报器（P6，理想交易日送达层）。

两种模式（同一脚本，Kimi cron 合并排程）：
- --mode brief：盘中时点简报（9:45/10:00/10:30/11:00/11:30/13:15/14:00/14:30/15:00）。
  简明输出：大盘宽度/涨跌停封板率、天气较上一时点的变化（无变化就明说"不变"）、
  强题材 Top5、focus list 逐票现价涨跌。目标是帮用户跟上盘中趋势、建立盘感，
  不做任何操作建议（战法铁律：盘中不做临场分析决策）。
- --mode alert：条件警报（建议 5 分钟一跑）。**只在触发时推送，无事完全静默**
  （用户 2026-07-21 明确：必须是警报，没有触发就不要发）。规则：
  ① focus 股炸板（盘中触涨停价后回落）
  ② focus 股大跌 ≤-5% 或触及跌停
  ③ 市场急剧恶化：封板率较上一快照骤降 >15pp，或涨停家数腰斩
  警报永远只针对"观察/纪律提醒"（如：绝不能临场买入），不给操作建议。

数据源分工（总图定案）：个股现价→腾讯免费接口（省悟道配额）；
宽度/涨跌停/题材→悟道 market_overview / limit_stats / theme_intraday_capital。
快照状态存 /Users/tx/market-data/intraday_state.json 供相邻时点对比。

用法：
  python intraday_brief.py --mode brief [--dry-run]
  python intraday_brief.py --mode alert [--dry-run] [--force]   # force=忽略盘中时段检查
需环境变量 WUDAO_API_KEY；推送走 feishu_push（未配置则本地打印）。
"""
import os, sys, json, time, argparse, requests, duckdb
from datetime import datetime

# 直连国内接口（同 mis_daily.py 的系统代理补丁）
for _v in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
    os.environ.pop(_v, None)
import requests.utils as _ru
_ru.getproxies = lambda: {}

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from feishu_push import push_text

KEY = os.environ.get("WUDAO_API_KEY")
MCP_URL = "https://stock.quicktiny.cn/api/mcp"
DB_PATH = "/Users/tx/market-data/market.duckdb"
STATE_FILE = "/Users/tx/market-data/intraday_state.json"
MIN_INTERVAL_S = 1.25
_last_call_at = [0.0]


def call_tool(name, arguments, _retries=2):
    for attempt in range(_retries + 1):
        wait = MIN_INTERVAL_S - (time.time() - _last_call_at[0])
        if wait > 0:
            time.sleep(wait)
        _last_call_at[0] = time.time()
        try:
            resp = requests.post(MCP_URL,
                headers={"Authorization": "Bearer " + (KEY or ""), "Content-Type": "application/json"},
                json={"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                      "params": {"name": name, "arguments": arguments}}, timeout=45)
            resp.raise_for_status()
        except requests.exceptions.RequestException:
            if attempt < _retries:
                time.sleep(4 * (attempt + 1))
                continue
            raise
        result = resp.json()
        err = result.get("error")
        if err:
            if err.get("code") == -32028 and attempt < _retries:
                time.sleep((err.get("data", {}).get("retryAfterMs", 60000)) / 1000.0 + 1)
                continue
            raise RuntimeError(name + ": " + str(err)[:120])
        sc = result.get("result", {}).get("structuredContent", {})
        return sc.get("data", sc)


def in_session(now=None):
    now = now or datetime.now()
    if now.weekday() >= 5:
        return False
    hm = now.hour * 100 + now.minute
    return (925 <= hm <= 1135) or (1255 <= hm <= 1505)


def load_focus():
    """focus_list 最新一批（=今天的盘中计划），返回 [(code,name,path)]。"""
    con = duckdb.connect(DB_PATH, read_only=True)
    row = con.execute("SELECT max(trade_date) FROM focus_list_daily").fetchone()
    if not row or row[0] is None:
        con.close()
        return None, []
    d = row[0]
    rows = con.execute(
        "SELECT code, name, path FROM focus_list_daily WHERE trade_date = ?", [d]).fetchall()
    con.close()
    return d, rows


def tencent_quotes(codes):
    """腾讯免费行情，一次请求全部。返回 {code: {...}}；失败返回 {}。"""
    if not codes:
        return {}
    syms = ",".join(("sh" if c.startswith("6") else "sz") + c for c in codes)
    try:
        r = requests.get(f"https://qt.gtimg.cn/q={syms}", timeout=10)
        r.encoding = "gbk"
    except Exception as e:
        print(f"[tencent] 行情获取失败: {e}")
        return {}
    out = {}
    for line in r.text.strip().split(";"):
        line = line.strip()
        if "=" not in line or "~" not in line:
            continue
        f = line.split("=", 1)[1].strip('"').split("~")
        if len(f) < 49:
            continue
        code = f[2]
        def fl(i):
            try:
                return float(f[i])
            except (ValueError, IndexError):
                return None
        out[code] = {"name": f[1], "price": fl(3), "prev_close": fl(4),
                     "pct": fl(32), "high": fl(33), "low": fl(34),
                     "limit_up": fl(47), "limit_down": fl(48)}
    return out


def load_state():
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def save_state(st):
    st["updated_at"] = datetime.now().isoformat(timespec="seconds")
    with open(STATE_FILE, "w") as f:
        json.dump(st, f, ensure_ascii=False, indent=1)


def get_market_pulse():
    """悟道两连击：宽度 + 涨跌停统计。返回 dict（字段尽量鲁棒提取）。"""
    pulse = {}
    try:
        mo = call_tool("market_overview", {"detailLevel": "standard", "format": "json"})
        for k in ("upCount", "riseCount", "up", "advance"):
            if isinstance(mo.get(k), (int, float)):
                pulse["up_count"] = int(mo[k]); break
        for k in ("downCount", "fallCount", "down", "decline"):
            if isinstance(mo.get(k), (int, float)):
                pulse["down_count"] = int(mo[k]); break
        for k in ("temperature", "marketTemperature", "sentimentScore"):
            if mo.get(k) is not None:
                pulse["temperature"] = mo[k]; break
    except Exception as e:
        print(f"[market_overview] {e}")
    try:
        ls = call_tool("limit_stats", {"detailLevel": "standard", "format": "json"})
        pulse["sealed_up"] = ls.get("sealedLimitUp")
        pulse["broken_up"] = ls.get("brokenLimitUp")
        sr = ls.get("limitUpSealRate")
        # 悟道返回 0-1 比例,统一归一为百分数(万一上游改口径返回>1.5就原样用)
        pulse["seal_rate"] = round(sr * 100, 1) if isinstance(sr, (int, float)) and sr <= 1.5 else sr
        pulse["limit_down"] = ls.get("sealedLimitDown")
    except Exception as e:
        print(f"[limit_stats] {e}")
    return pulse


def weather_delta(pulse, prev):
    """与上一快照对比出'天气变化'一句话。信息不足时明说。"""
    if not prev or "seal_rate" not in prev or pulse.get("seal_rate") is None:
        return "天气：首个快照，无对比基准"
    msgs = []
    try:
        d_rate = float(pulse["seal_rate"]) - float(prev["seal_rate"])
        if d_rate <= -10:
            msgs.append(f"封板率骤降{abs(d_rate):.0f}pp(恶化)")
        elif d_rate >= 10:
            msgs.append(f"封板率回升{d_rate:.0f}pp(转强)")
    except (TypeError, ValueError):
        pass
    try:
        if pulse.get("up_count") is not None and prev.get("up_count") is not None:
            d_up = pulse["up_count"] - prev["up_count"]
            if abs(d_up) >= 800:
                msgs.append(f"上涨家数{'+' if d_up > 0 else ''}{d_up}(急变)")
    except TypeError:
        pass
    return "天气变化：" + "、".join(msgs) if msgs else "天气：较上一时点不变"


def mode_brief(args):
    now = datetime.now()
    pulse = get_market_pulse()
    prev = load_state().get("pulse", {})
    weather = weather_delta(pulse, prev)

    themes = []
    try:
        td = call_tool("theme_intraday_capital", {"sortBy": "strength", "limit": 5,
                                                  "detailLevel": "standard", "format": "json"})
        for t in td.get("rows", [])[:5]:
            themes.append(t.get("themeName") or t.get("name") or "?")
    except Exception as e:
        print(f"[theme] {e}")

    fdate, focus = load_focus()
    quotes = tencent_quotes([c for c, _, _ in focus])

    lines = [f"⏱ {now:%H:%M} 盘中简报"]
    up, down = pulse.get("up_count"), pulse.get("down_count")
    if up is not None or down is not None:
        lines.append(f"宽度: 涨{up if up is not None else '?'}/跌{down if down is not None else '?'}"
                     + (f" 温度{pulse['temperature']}" if pulse.get("temperature") is not None else ""))
    if pulse.get("sealed_up") is not None:
        lines.append(f"涨停{pulse['sealed_up']} 炸板{pulse.get('broken_up', '?')} "
                     f"封板率{pulse.get('seal_rate', '?')}% 跌停{pulse.get('limit_down', '?')}")
    lines.append(weather)
    if themes:
        lines.append("强题材: " + " / ".join(themes))
    if focus:
        lines.append(f"— focus({fdate}) —")
        for c, n, p in focus:
            q = quotes.get(c)
            tag = "突破" if p == "breakout" else "龙头"
            if q and q.get("pct") is not None:
                mark = ""
                if q.get("limit_up") and q.get("high") and q["high"] >= q["limit_up"] and q["price"] < q["limit_up"] * 0.998:
                    mark = " ⚠️炸板"
                lines.append(f"{n}({c})[{tag}] {q['pct']:+.1f}%{mark}")
            else:
                lines.append(f"{n}({c})[{tag}] 无行情")
    else:
        lines.append("focus list 为空")
    lines.append("(纪律: 盘中只对表, 不做计划外操作)")
    text = "\n".join(lines)

    st = load_state()
    st["pulse"] = pulse
    save_state(st)

    if args.dry_run:
        print(text)
    else:
        ok = push_text(text, title="MIS 盘中简报")
        print("已推送" if ok else text)


def mode_alert(args):
    now = datetime.now()
    if not args.force and not in_session(now):
        return  # 非盘中静默退出，零调用零推送
    alerts = []
    st = load_state()
    prev = st.get("alert_pulse", {})

    fdate, focus = load_focus()
    quotes = tencent_quotes([c for c, _, _ in focus])
    for c, n, p in focus:
        q = quotes.get(c)
        if not q or q.get("price") is None:
            continue
        if q.get("limit_up") and q.get("high") and q["high"] >= q["limit_up"] and q["price"] < q["limit_up"] * 0.998:
            alerts.append(f"⚠️ {n}({c}) 炸板：触{q['limit_up']}后回落至{q['price']}")
        if q.get("pct") is not None and q["pct"] <= -5:
            alerts.append(f"⚠️ {n}({c}) 大跌 {q['pct']:+.1f}%")
        if q.get("limit_down") and q["price"] <= q["limit_down"] * 1.002:
            alerts.append(f"🔴 {n}({c}) 触及跌停")

    pulse = {}
    try:
        ls = call_tool("limit_stats", {"detailLevel": "standard", "format": "json"})
        sr = ls.get("limitUpSealRate")
        sr = round(sr * 100, 1) if isinstance(sr, (int, float)) and sr <= 1.5 else sr
        pulse = {"seal_rate": sr, "sealed_up": ls.get("sealedLimitUp")}
        if prev.get("seal_rate") is not None and pulse.get("seal_rate") is not None:
            if float(prev["seal_rate"]) - float(pulse["seal_rate"]) > 15:
                alerts.append(f"⚠️ 封板率骤降 {prev['seal_rate']}%→{pulse['seal_rate']}%（情绪急剧恶化）")
        if prev.get("sealed_up") and pulse.get("sealed_up") is not None:
            if pulse["sealed_up"] < prev["sealed_up"] * 0.5:
                alerts.append(f"⚠️ 涨停家数腰斩 {prev['sealed_up']}→{pulse['sealed_up']}")
    except Exception as e:
        print(f"[limit_stats] {e}")

    st["alert_pulse"] = pulse or prev
    save_state(st)

    if not alerts:
        print(f"{now:%H:%M} 无触发，不推送")
        return
    text = "\n".join(alerts) + "\n(纪律提醒: 警报≠操作信号, 离场须指认约束翻转项)"
    if args.dry_run:
        print(text)
    else:
        ok = push_text(text, title=f"🚨 MIS 警报 {now:%H:%M}")
        print("警报已推送" if ok else text)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["brief", "alert"], required=True)
    ap.add_argument("--dry-run", action="store_true", help="只打印不推送")
    ap.add_argument("--force", action="store_true", help="alert 模式忽略盘中时段检查")
    args = ap.parse_args()
    if not KEY:
        raise SystemExit("WUDAO_API_KEY 未设置。")
    if args.mode == "brief":
        mode_brief(args)
    else:
        mode_alert(args)


if __name__ == "__main__":
    main()
