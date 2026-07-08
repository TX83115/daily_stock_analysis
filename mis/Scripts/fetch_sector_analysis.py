import requests
import duckdb
import json
import sys
from datetime import date

WUDAO_URL = "https://stock.quicktiny.cn/api/mcp"
API_KEY = "lb_95edefd519bcfd361b1d008c205f07ff13488e696aa85914433ee589c695679c"
DB_PATH = "/Users/tx/market-data/market.duckdb"

def call_tool(tool_name, arguments):
    resp = requests.post(
        WUDAO_URL,
        headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/call",
              "params": {"name": tool_name, "arguments": arguments}},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    if "error" in data:
        raise RuntimeError(data["error"])
    return data["result"]

def fetch_and_store(target_date: str):
    # sector_analysis没有日期参数，只能拉"当前"数据——这就是必须今晚抢救的原因
    try:
        result = call_tool("sector_analysis", {"detailLevel": "raw", "format": "json"})
    except Exception as e:
        print(f"带参数调用失败（{e}），改用空参数重试...")
        result = call_tool("sector_analysis", {})

    sc = result.get("structuredContent", {})
    data = sc.get("data", {})

    print("=== 最外层key ===", list(result.keys()))
    print("=== structuredContent里的key ===", list(sc.keys()))
    print("=== data里的key ===", list(data.keys()) if isinstance(data, dict) else type(data))
    preview = json.dumps(data, ensure_ascii=False)
    print("=== data前1500字预览（肉眼确认日期和内容） ===")
    print(preview[:1500])

    with duckdb.connect(DB_PATH) as con:
        con.execute("""CREATE TABLE IF NOT EXISTS sector_analysis_baseline (
            trade_date DATE, raw_json VARCHAR,
            fetched_at TIMESTAMP DEFAULT current_timestamp, source VARCHAR DEFAULT 'wudao')""")
        con.execute("DELETE FROM sector_analysis_baseline WHERE trade_date = ?", [target_date])
        con.execute("INSERT INTO sector_analysis_baseline (trade_date, raw_json) VALUES (?, ?)",
                    [target_date, json.dumps(result, ensure_ascii=False)])

    print(f"\n[{target_date}] sector_analysis 原始JSON已抢救存档（sector_analysis_baseline表）")

if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else str(date.today())
    fetch_and_store(target)