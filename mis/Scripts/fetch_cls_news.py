"""
fetch_cls_news.py
悟道 cls_news（财联社电报）采集入库 -> 本地 DuckDB news_daily（P4 消息面数据底座）。

用途（下游消费方）：
- 8:30 晨报：读 news_daily 最近 N 小时的 A/B 级电报（隔夜到现在），汇总外围+A股要闻。
- 战法 §13 空间表第5项「消息强度」：按候选股 stockCode / 板块关键词查当日相关电报，
  把"人工定性"升级为"库中取数自动预填"。
- 战法 §17 盘中计划「今日主催化」：按事件日历命中项在库中匹配。

设计要点：
- 只入 A/B 级（A=重大突发、B=重要）。C 级是常规噪音，PDF 与战法 §3 都主张只对重要
  消息做深度分析；需要时用 --level all 覆盖。
- 去重累积：按 content 的 md5 做主键，反复跑不重复、自然累积（cls_news 无分页，靠
  hoursAgo / 时间窗多次拉也不会重复入库）。不做 DELETE 整表重写，避免跨天窗口互相覆盖。
- 隔夜覆盖：默认 --hours 18，覆盖"昨日盘后 ~ 今早"的隔夜时段。

用法：
  python fetch_cls_news.py                 # 拉最近18小时 A/B 级，去重入库
  python fetch_cls_news.py --hours 4       # 只拉最近4小时（盘中节点用）
  python fetch_cls_news.py --level all     # 含 C 级
  python fetch_cls_news.py --date 2026-07-20   # 补某个日历日全天

需环境变量 WUDAO_API_KEY。
"""
import os, json, time, hashlib, argparse, requests, duckdb
from datetime import datetime

KEY = os.environ.get("WUDAO_API_KEY")
MCP_URL = "https://stock.quicktiny.cn/api/mcp"
DB_PATH = "/Users/tx/market-data/market.duckdb"
MIN_INTERVAL_S = 1.25
_last_call_at = [0.0]

DDL = """
CREATE TABLE IF NOT EXISTS news_daily (
    content_hash  VARCHAR PRIMARY KEY,   -- md5(content)，去重
    publish_time  TIMESTAMP,             -- 电报发布时间（fullTime）
    publish_date  DATE,                  -- 发布日历日
    level         VARCHAR,               -- A=重大突发 / B=重要 / C=常规
    content       VARCHAR,
    subjects      VARCHAR,               -- 关联标的，JSON 原样存
    ref           VARCHAR,
    fetched_at    TIMESTAMP
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
            if attempt < _retries:
                time.sleep(5 * (2 ** attempt))
                continue
            raise
        result = resp.json()
        err = result.get("error")
        if err:
            if err.get("code") == -32028 and attempt < _retries:
                time.sleep((err.get("data", {}).get("retryAfterMs", 60000)) / 1000.0 + 1)
                continue
            raise RuntimeError(name + " call failed: " + str(err))
        sc = result.get("result", {}).get("structuredContent", {})
        return sc.get("data", sc)


def _parse_time(item):
    """cls_news 的 fullTime 优先；解析失败则用 time 字段，都失败返回 None。"""
    for k in ("fullTime", "time"):
        v = item.get(k)
        if not v:
            continue
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%m-%d %H:%M:%S", "%H:%M:%S"):
            try:
                dt = datetime.strptime(str(v), fmt)
                if dt.year == 1900:  # 只有时间没有日期，补今天
                    now = datetime.now()
                    dt = dt.replace(year=now.year, month=now.month, day=now.day)
                return dt
            except ValueError:
                continue
    return None


def fetch(args):
    call_args = {"level": args.level, "limit": 100, "detailLevel": "raw", "format": "json"}
    if args.date:
        call_args["date"] = args.date
    else:
        call_args["hoursAgo"] = args.hours
    data = call_tool("cls_news", call_args)
    return data.get("rows", data.get("items", []))


def main():
    if not KEY:
        raise SystemExit("WUDAO_API_KEY 未设置（环境变量或 ~/.env）。")
    ap = argparse.ArgumentParser()
    ap.add_argument("--hours", type=int, default=18, help="最近N小时（默认18，覆盖隔夜）")
    ap.add_argument("--date", help="改按日历日全天采集 YYYY-MM-DD（与 --hours 互斥）")
    ap.add_argument("--level", default="AB", help="消息级别 A/B/AB/all（默认 AB，只入重要）")
    args = ap.parse_args()

    rows = fetch(args)
    con = duckdb.connect(DB_PATH)
    con.execute(DDL)
    existing = set(r[0] for r in con.execute("SELECT content_hash FROM news_daily").fetchall())

    now = datetime.now()
    new_rows, skipped = [], 0
    for it in rows:
        content = it.get("content") or ""
        if not content:
            continue
        h = hashlib.md5(content.encode("utf-8")).hexdigest()
        if h in existing:
            skipped += 1
            continue
        existing.add(h)
        pt = _parse_time(it)
        subj = it.get("subjects")
        new_rows.append([
            h, pt, pt.date() if pt else None, it.get("level"),
            content, json.dumps(subj, ensure_ascii=False) if subj is not None else None,
            it.get("ref"), now])

    if new_rows:
        con.executemany(
            "INSERT INTO news_daily VALUES (?, ?, ?, ?, ?, ?, ?, ?)", new_rows)
    total = con.execute("SELECT count(*) FROM news_daily").fetchone()[0]
    # 按级别统计本次入库
    by_level = {}
    for r in new_rows:
        by_level[r[3]] = by_level.get(r[3], 0) + 1
    con.close()
    print(f"cls_news 拉取 {len(rows)} 条，新入库 {len(new_rows)}（{by_level}），"
          f"去重跳过 {skipped}；news_daily 累计 {total} 条。")


if __name__ == "__main__":
    main()
