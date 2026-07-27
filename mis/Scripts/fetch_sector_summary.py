"""
fetch_sector_summary.py
每日抓取板块两类数据:
1. theme_intraday_capital (limit=100,实际约返回50条) -> sector_summary_daily
2. sector_analysis (source=kpl) -> sector_market_stats_daily

数据源说明:theme_intraday_capital 是悟道官方推荐的板块资金流"主入口",
concept_ranking 已被官方标注为隐藏/废弃,不再使用。

A类脚本:手动跑,Terminal已加载~/.zshrc,直接os.environ.get读取
"""
import os, json, duckdb, requests
from datetime import date

KEY = os.environ.get('WUDAO_API_KEY')
DB_PATH = '/Users/tx/market-data/market.duckdb'
MCP_URL = 'https://stock.quicktiny.cn/api/mcp'


def call_tool(name, arguments):
    resp = requests.post(MCP_URL,
        headers={'Authorization': f'Bearer {KEY}', 'Content-Type': 'application/json'},
        json={'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call',
              'params': {'name': name, 'arguments': arguments}})
    result = resp.json()
    if 'error' in result:
        raise RuntimeError(f'{name} call failed: {result["error"]}')
    sc = result.get('result', {}).get('structuredContent', {})
    return sc.get('data', sc), result


def fetch_theme_intraday_capital(trade_date):
    data, _ = call_tool('theme_intraday_capital', {
        'sortBy': 'strength', 'limit': 100, 'detailLevel': 'raw', 'format': 'json'
    })
    rows = data.get('rows', [])
    snapshot_time = data.get('snapshotTime', '')
    total = data.get('total')
    returned = data.get('returned')

    con = duckdb.connect(DB_PATH)
    con.execute("DELETE FROM sector_summary_daily WHERE trade_date = ?", [trade_date])

    for idx, r in enumerate(rows, start=1):
        con.execute('''
        INSERT INTO sector_summary_daily
        (trade_date, sector_code, sector_name, rank, pct_chg, fundflow,
         strength, big_order_net_amount, amount, volume_ratio, turnover_rate, snapshot_time, source)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', [trade_date, r.get('themeCode'), r.get('themeName'), idx,
              r.get('pctChg'), r.get('mainNetAmount'),
              r.get('strength'), r.get('bigOrderNetAmount'), r.get('amount'),
              r.get('volumeRatio'), r.get('turnoverRate'), snapshot_time,
              'theme_intraday_capital'])
    con.close()
    return len(rows), total, returned, snapshot_time


def fetch_sector_analysis(trade_date):
    data, raw = call_tool('sector_analysis', {
        'source': 'kpl', 'detailLevel': 'standard', 'format': 'json'
    })
    stats = data.get('stats', {})
    meta = data.get('meta', {})
    headline = data.get('headline', '')

    con = duckdb.connect(DB_PATH)
    con.execute('''
    INSERT OR REPLACE INTO sector_market_stats_daily
    (trade_date, period_days, strength_period_days, sector_count, recent_median,
     period_median, recent_mean, period_mean, headline, raw_json)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', [trade_date, meta.get('period'), meta.get('strengthPeriod'), meta.get('sectorCount'),
          stats.get('recentMedian'), stats.get('periodMedian'), stats.get('recentMean'),
          stats.get('periodMean'), headline, json.dumps(raw, ensure_ascii=False)])
    con.close()
    return headline


if __name__ == '__main__':
    today = date.today().isoformat()
    print(f'Fetching sector data for {today}...')

    n, total, returned, snap = fetch_theme_intraday_capital(today)
    print(f'theme_intraday_capital: inserted {n} rows (total={total}, returned={returned}, snapshot={snap})')

    h = fetch_sector_analysis(today)
    print(f'sector_analysis: {h}')

    print('Done')
