"""
score_news.py
Kimi API 对 news_daily 电报做结构化打分 -> news_score_daily（P4b 消息面分析层）。

上游：fetch_cls_news.py 采集的财联社 A/B 级电报（news_daily 表）。
下游：
- 8:30 晨报：按 importance 排序取要闻；
- 战法 §13 空间表第5项「消息强度」自动预填（政策级/A类事件 vs 已兑现一次性）；
- 战法 §17「今日主催化」匹配；
- L2 catalyst：affected_sectors 聚合后为 dragon 候选板块做佐证。

打分 schema（每条）：importance 1-10 / direction 利多|利空|中性 / affected_sectors[] /
affected_stocks[{code,name,logic}] / catalyst_type 政策|业绩|事件|资金|行业|宏观 /
confidence 0-1 / reasoning ≤60字。设计出处：Kimi 07-19《MIS建设方案》PDF 双通道思路
（财联社官方 A/B 级做粗筛 = 第一通道；本脚本 LLM 结构化打分 = 第二通道）。

幂等：按 content_hash 只给未打分的行打分，反复跑不重复计费。
模型：默认 moonshot-v1-8k（与 broker_research 同款、已验证可用），
可用环境变量 KIMI_SCORE_MODEL 覆盖。批 10 条/次调用，控制上下文与成本。

用法：
  python score_news.py                 # 给全部未打分的 A/B 级电报打分
  python score_news.py --limit 20      # 最多打 20 条
  python score_news.py --date 2026-07-21   # 只打某天的
需环境变量 KIMI_API_KEY。
"""
import os, json, argparse, duckdb
from datetime import datetime

DB_PATH = "/Users/tx/market-data/market.duckdb"
KIMI_API_KEY = os.environ.get("KIMI_API_KEY")
KIMI_BASE_URL = "https://api.moonshot.ai/v1"
KIMI_MODEL = os.environ.get("KIMI_SCORE_MODEL", "moonshot-v1-8k")
BATCH = 10

DDL = """
CREATE TABLE IF NOT EXISTS news_score_daily (
    content_hash     VARCHAR PRIMARY KEY,   -- 对应 news_daily.content_hash
    importance       INTEGER,               -- 1-10
    direction        VARCHAR,               -- 利多/利空/中性
    affected_sectors VARCHAR,               -- JSON 数组
    affected_stocks  VARCHAR,               -- JSON 数组 [{code,name,logic}]
    catalyst_type    VARCHAR,               -- 政策/业绩/事件/资金/行业/宏观
    confidence       DOUBLE,                -- 0-1
    reasoning        VARCHAR,
    model            VARCHAR,
    scored_at        TIMESTAMP
)
"""

SYSTEM_PROMPT = """你是A股市场情报分析引擎。对输入的每条财联社电报快讯打分，输出严格JSON。
输出格式：{"scores":[{"idx":0,"importance":7,"direction":"利多","affected_sectors":["半导体"],
"affected_stocks":[{"code":"600519","name":"贵州茅台","logic":"直接受益"}],
"catalyst_type":"政策","confidence":0.8,"reasoning":"不超过60字"}]}
规则：
- idx 对应输入编号，每条输入必须有且仅有一条输出。
- importance: 9-10=降准降息/重大政策/战争级事件；7-8=行业级政策/龙头重大公告；
  5-6=值得关注的行业动态；3-4=常规公告/例行数据；1-2=噪音。
- direction 判断对A股相关板块的方向；无明确方向填"中性"。
- affected_sectors 用A股常用板块名（如 半导体/算力/军工/白酒）；无则空数组。
- affected_stocks 只填电报明确提及或强逻辑关联的A股标的；不确定代码就只填name；无则空数组。
- catalyst_type 从 政策/业绩/事件/资金/行业/宏观 中选一个。
- 只输出JSON，不要任何其他文字。"""


def load_unscored(con, limit, date_filter):
    q = """
        SELECT n.content_hash, n.content, n.level
        FROM news_daily n
        LEFT JOIN news_score_daily s ON s.content_hash = n.content_hash
        WHERE s.content_hash IS NULL AND n.level IN ('A', 'B')
    """
    params = []
    if date_filter:
        q += " AND n.publish_date = ?"
        params.append(date_filter)
    q += " ORDER BY n.publish_time DESC LIMIT ?"
    params.append(limit)
    return con.execute(q, params).fetchall()


def score_batch(client, items):
    """items: [(hash, content, level)] -> list of score dicts aligned by idx."""
    user_lines = []
    for i, (_, content, level) in enumerate(items):
        user_lines.append(f"[{i}] (官方级别:{level}) {content[:500]}")
    resp = client.chat.completions.create(
        model=KIMI_MODEL,
        messages=[{"role": "system", "content": SYSTEM_PROMPT},
                  {"role": "user", "content": "\n".join(user_lines)}],
        response_format={"type": "json_object"},
        temperature=0.2,
    )
    data = json.loads(resp.choices[0].message.content)
    by_idx = {}
    for s in data.get("scores", []):
        if isinstance(s.get("idx"), int):
            by_idx[s["idx"]] = s
    return by_idx


def main():
    if not KIMI_API_KEY:
        raise SystemExit("KIMI_API_KEY 未设置（在 ~/.zshrc）。")
    from openai import OpenAI
    client = OpenAI(api_key=KIMI_API_KEY, base_url=KIMI_BASE_URL)

    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=100, help="本次最多打分条数")
    ap.add_argument("--date", help="只打某个发布日 YYYY-MM-DD")
    args = ap.parse_args()

    con = duckdb.connect(DB_PATH)
    con.execute(DDL)
    todo = load_unscored(con, args.limit, args.date)
    if not todo:
        print("无未打分的 A/B 级电报。")
        con.close()
        return

    def row_from_score(h, s):
        return [h, int(s.get("importance", 0)) or None, s.get("direction"),
                json.dumps(s.get("affected_sectors", []), ensure_ascii=False),
                json.dumps(s.get("affected_stocks", []), ensure_ascii=False),
                s.get("catalyst_type"), float(s.get("confidence", 0)) or None,
                (s.get("reasoning") or "")[:200], KIMI_MODEL, now]

    def rejected_row(h, reason):
        # 审核拒绝/反复失败的条目：落一行占位（importance=NULL, model 标记原因），
        # 使其退出"未打分"集合，避免每次运行都重试同一批被拒内容。
        return [h, None, None, None, None, None, None, reason[:200], "rejected", now]

    scored, failed = 0, 0
    now = datetime.now()
    for i in range(0, len(todo), BATCH):
        batch = todo[i:i + BATCH]
        rows = []
        try:
            by_idx = score_batch(client, batch)
        except Exception as e:
            print(f"  [批次失败→逐条降级] {type(e).__name__}: {str(e)[:80]}")
            by_idx = {}
        # 批内缺失或整批失败的条目 → 逐条打分（单条更稳，且把审核污染隔离到单条）
        for j, (h, content, level) in enumerate(batch):
            s = by_idx.get(j)
            if not s:
                try:
                    solo = score_batch(client, [(h, content, level)])
                    s = solo.get(0)
                except Exception as e:
                    rows.append(rejected_row(h, f"{type(e).__name__}:{str(e)[:100]}"))
                    failed += 1
                    continue
            if s:
                rows.append(row_from_score(h, s))
                scored += 1
            else:
                rows.append(rejected_row(h, "no_score_returned"))
                failed += 1
        if rows:
            con.executemany("INSERT INTO news_score_daily VALUES (?,?,?,?,?,?,?,?,?,?)", rows)
        print(f"  批次 {i // BATCH + 1}: 成功 {sum(1 for r in rows if r[8] != 'rejected')}/{len(batch)}")

    total = con.execute("SELECT count(*) FROM news_score_daily").fetchone()[0]
    # 高分速览
    top = con.execute("""
        SELECT s.importance, s.direction, substr(n.content, 1, 40)
        FROM news_score_daily s JOIN news_daily n USING (content_hash)
        ORDER BY s.scored_at DESC, s.importance DESC LIMIT 5""").fetchall()
    con.close()
    print(f"本次打分 {scored} 条（失败 {failed}），news_score_daily 累计 {total} 条。")
    for t in top:
        print(f"  [{t[0]}分·{t[1]}] {t[2]}")


if __name__ == "__main__":
    main()
