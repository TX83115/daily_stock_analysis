
import duckdb
from datetime import date

DB_PATH = "/Users/tx/market-data/market.duckdb"
TOP_N = 20


def compute_window_rank(con, trade_date, window_days):
    distinct_days = con.execute(
        "SELECT COUNT(DISTINCT trade_date) FROM sector_summary_daily WHERE trade_date <= ?",
        [trade_date]
    ).fetchone()[0]

    if distinct_days < window_days:
        return {}, distinct_days

    window_start = con.execute(
        "SELECT MIN(trade_date) FROM (SELECT DISTINCT trade_date FROM sector_summary_daily WHERE trade_date <= ? ORDER BY trade_date DESC LIMIT ?)",
        [trade_date, window_days]
    ).fetchone()[0]

    rows = con.execute(
        "SELECT sector_code, AVG(fundflow) as avg_flow FROM sector_summary_daily WHERE trade_date <= ? AND trade_date >= ? GROUP BY sector_code ORDER BY avg_flow DESC",
        [trade_date, window_start]
    ).fetchall()

    rank_map = {row[0]: idx + 1 for idx, row in enumerate(rows)}
    return rank_map, distinct_days


def compute(trade_date):
    con = duckdb.connect(DB_PATH)

    today_rows = con.execute(
        "SELECT sector_code, sector_name, fundflow FROM sector_summary_daily WHERE trade_date = ? ORDER BY fundflow DESC",
        [trade_date]
    ).fetchall()

    if not today_rows:
        print(trade_date, ": no sector data, skipping")
        con.close()
        return 0

    rank_today_map = {row[0]: idx + 1 for idx, row in enumerate(today_rows)}

    rank_2d_map, days_have = compute_window_rank(con, trade_date, 2)
    rank_3d_map, _ = compute_window_rank(con, trade_date, 3)
    rank_5d_map, _ = compute_window_rank(con, trade_date, 5)

    con.execute("DELETE FROM fund_flow_daily WHERE trade_date = ?", [trade_date])

    count = 0
    for code, name, flow in today_rows:
        r_today = rank_today_map.get(code)
        r_2d = rank_2d_map.get(code)
        r_3d = rank_3d_map.get(code)
        r_5d = rank_5d_map.get(code)

        is_building = None
        if r_2d and r_3d and r_5d:
            in_top_n = (r_2d <= TOP_N) and (r_3d <= TOP_N) and (r_5d <= TOP_N)
            trend_increasing = (r_2d <= r_3d <= r_5d)
            is_building = in_top_n and trend_increasing

        con.execute(
            "INSERT INTO fund_flow_daily (trade_date, sector_code, sector_name, fundflow, rank_today, rank_2d, rank_3d, rank_5d, is_building_position) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [trade_date, code, name, flow, r_today, r_2d, r_3d, r_5d, is_building]
        )
        count += 1

    con.close()
    print("Distinct trading days so far:", days_have, "(need 5 for full rank_5d)")
    return count


if __name__ == "__main__":
    today = date.today().isoformat()
    n = compute(today)
    print(today, ": computed", n, "sector fund-flow ranks")
