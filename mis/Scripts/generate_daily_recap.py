import duckdb
import sys
from datetime import date

DB_PATH = "/Users/tx/market-data/market.duckdb"

def normalize_date(d: str) -> str:
    d = d.replace("-", "")
    return f"{d[0:4]}-{d[4:6]}-{d[6:8]}"

def ensure_table(con):
    con.execute("""CREATE TABLE IF NOT EXISTS daily_recap (
        trade_date DATE, summary_text VARCHAR,
        generated_at TIMESTAMP DEFAULT current_timestamp)""")

def generate_recap(target_date: str):
    td = normalize_date(target_date)

    with duckdb.connect(DB_PATH) as con:
        ensure_table(con)

        sd = con.execute("SELECT * FROM sentiment_daily WHERE trade_date = ?", [td]).fetchdf()
        bb = con.execute("SELECT * FROM board_break_summary_daily WHERE trade_date = ?", [td]).fetchdf()

        if sd.empty:
            raise RuntimeError(f"sentiment_daily里没有{td}这天的数据，先跑fetch_sentiment_baseline.py")
        if bb.empty:
            raise RuntimeError(f"board_break_summary_daily里没有{td}这天的数据，先跑fetch_board_break.py")

        s = sd.iloc[0]
        b = bb.iloc[0]

        high_broken = con.execute("""
            SELECT code, name, prev_streak, pct_chg FROM board_break_detail_daily
            WHERE trade_date = ? AND prev_streak >= 3 AND sealed_again = false
            ORDER BY prev_streak DESC, pct_chg ASC
        """, [td]).fetchdf()

        high_broken_str = "、".join(
            f"{r['name']}({r['prev_streak']}板→{r['pct_chg']}%)" for _, r in high_broken.iterrows()
        ) if not high_broken.empty else "无"

        text = (
            f"【{td}（{s['day_of_week']}）四点复盘小结】\n"
            f"涨跌停：今日封住涨停{int(s['sealed_up'])}家，触板{int(s['touched_up'])}家，炸板{int(s['broken_up'])}家，"
            f"封板率{s['seal_rate_up']*100:.1f}%；封住跌停{int(s['sealed_down'])}家，触及{int(s['touched_down'])}家，"
            f"跌停封板率{s['seal_rate_down']*100:.1f}%。最高连板{int(s['max_board_level'])}板。"
            f"晋级率：1进2 {s['promo_1to2']}%，2进3 {s['promo_2to3']}%，3进4 {s['promo_3to4']}%，高位晋级{s['promo_high']}%。\n"
            f"断板分析（相对{str(b['prev_date'])[:10]}的{int(b['total_prev_limit_ups'])}只涨停）："
            f"续板{int(b['sealed_again_count'])}只，断板{int(b['broken_count'])}只，断板率{b['break_rate']*100:.1f}%，"
            f"断板股平均涨跌幅{b['avg_broken_pct_chg']}%。"
            f"状态分布：跌停{int(b['status_limit_down'])}只、深跌{int(b['status_hard_break'])}只、"
            f"小幅跌{int(b['status_mild_break'])}只、高开低走{int(b['status_high_open_low_close'])}只、"
            f"平盘{int(b['status_flat'])}只、红盘弱续{int(b['status_red_close'])}只。"
            f"高标杀{int(b['high_board_broken_count'])}只：{high_broken_str}。\n"
            f"情绪信号（悟道工具判定）：{b['sentiment_signal']}。"
        )

        print(text)

        con.execute("DELETE FROM daily_recap WHERE trade_date = ?", [td])
        con.execute("INSERT INTO daily_recap (trade_date, summary_text) VALUES (?, ?)", [td, text])

    print(f"\n[{td}] 复盘小结已存入daily_recap表")

if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else str(date.today())
    generate_recap(target)