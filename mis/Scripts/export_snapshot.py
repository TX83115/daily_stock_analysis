"""
export_snapshot.py —— 导出 MIS 早间报告所需的小表快照（云端 GitHub Actions 消费用）。

背景：晨间三件套（08:30 晨报 / 08:50 操作清单 / 09:27 竞价报告）计划迁到 GitHub Actions
云端跑，以摆脱"依赖本地 MacBook 在那一刻醒着"。但操作清单/竞价报告要读 focus_list_daily，
这张表是每晚 18:12 链在本地用 660MB 历史库 + 悟道算出来的，云端无法重算。故本脚本在 18:12
链末尾把这几张小表导出成 parquet 快照，由 publish_snapshot.sh 推送到一个【私有】GitHub 仓库，
次日早间 workflow 从私有仓库读取。

隐私：TX83115/daily_stock_analysis 是公开仓库，focus_list_daily 含每日交易候选股，绝不能进
公开仓库——所以快照走独立私有仓库（用户 2026-07-22 确认方案）。本脚本只负责【导出到目录】，
不涉及任何推送/密钥；推送由 publish_snapshot.sh 负责。

导出内容（全部很小，几十~几百行）：
  focus_list_daily     —— 最近 N 个交易日的双路径候选（操作清单/竞价报告核心输入）
  strategy_parameters  —— 当前生效的策略参数/阈值
  daily_recap          —— 最近的信号级复盘（昨日盘后小结，晨间上下文）
  sentiment_daily      —— 最近的情绪/天气基线（晨间上下文）
另写 manifest.json：导出时间、focus 最新交易日、本地日K最新日、各表行数——供云端校验新鲜度
（避免云端用到过期快照生成误导性清单）。

用法：
  python export_snapshot.py [输出目录]
  # 输出目录默认 $SNAPSHOT_DIR，再默认 ~/hithink-scripts/mis-snapshot-staging/snapshot
  # 接入私有仓库后，输出目录指向私有仓库本地 clone 的 snapshot/ 子目录即可。
失败策略：focus_list_daily 为空则非零退出（这是核心数据，空快照没有意义，宁可让 18:12 链告警）。
"""
import os
import sys
import json
import datetime
import duckdb

DB_PATH = "/Users/tx/market-data/market.duckdb"
DEFAULT_DIR = os.path.expanduser("~/hithink-scripts/mis-snapshot-staging/snapshot")

# 表名 -> 取数 SQL（只导出必要行，控制快照体积）
TABLES = {
    # 最近 10 个交易日的候选，足够覆盖任何"最新交易日"取数，且仍然极小
    "focus_list_daily": """
        SELECT * FROM focus_list_daily
        WHERE trade_date >= (SELECT max(trade_date) FROM focus_list_daily) - INTERVAL 20 DAY
    """,
    # 策略参数：只导出当前生效版本
    "strategy_parameters": "SELECT * FROM strategy_parameters WHERE is_active = true",
    # 复盘/情绪：各取最近 5 个交易日
    "daily_recap": """
        SELECT * FROM daily_recap
        WHERE trade_date >= (SELECT max(trade_date) FROM daily_recap) - INTERVAL 15 DAY
    """,
    "sentiment_daily": """
        SELECT * FROM sentiment_daily
        WHERE trade_date >= (SELECT max(trade_date) FROM sentiment_daily) - INTERVAL 15 DAY
    """,
}


def main():
    out_dir = (sys.argv[1] if len(sys.argv) > 1 else os.environ.get("SNAPSHOT_DIR")) or DEFAULT_DIR
    os.makedirs(out_dir, exist_ok=True)

    con = duckdb.connect(DB_PATH, read_only=True)
    manifest = {
        "exported_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "source_db": DB_PATH,
        "tables": {},
    }

    # 本地日K最新交易日（云端据此判断快照是否为最新交易日产出）
    try:
        manifest["kline_max_date"] = str(con.execute("SELECT max(date) FROM v_daily_qfq").fetchone()[0])
    except Exception as e:
        manifest["kline_max_date"] = None
        print(f"WARN: 读取日K最新日失败: {e}", file=sys.stderr)

    focus_rows = 0
    for tbl, sql in TABLES.items():
        try:
            n = con.execute(f"SELECT count(*) FROM ({sql}) t").fetchone()[0]
        except Exception as e:
            print(f"WARN: 表 {tbl} 取数失败，跳过: {e}", file=sys.stderr)
            manifest["tables"][tbl] = {"rows": None, "error": str(e)[:120]}
            continue
        out_path = os.path.join(out_dir, f"{tbl}.parquet")
        # 用参数化路径避免注入；COPY 目标路径需字符串字面量，此处路径来自本地固定拼接，安全
        con.execute(f"COPY ({sql}) TO '{out_path}' (FORMAT PARQUET)")
        manifest["tables"][tbl] = {"rows": n}
        if tbl == "focus_list_daily":
            focus_rows = n
            fmax = con.execute("SELECT max(trade_date) FROM focus_list_daily").fetchone()[0]
            manifest["focus_latest_date"] = str(fmax)
        print(f"  导出 {tbl}: {n} 行 -> {out_path}")

    con.close()

    with open(os.path.join(out_dir, "manifest.json"), "w") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    print(f"  manifest.json -> {out_dir}/manifest.json")
    print(f"  focus_latest_date={manifest.get('focus_latest_date')} kline_max_date={manifest.get('kline_max_date')}")

    if focus_rows == 0:
        print("ERROR: focus_list_daily 导出为 0 行，核心数据缺失，快照无意义", file=sys.stderr)
        sys.exit(1)

    print(f">>> 快照导出完成 -> {out_dir}")


if __name__ == "__main__":
    main()
