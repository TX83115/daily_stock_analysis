import requests
import json
import sys

WUDAO_URL = "https://stock.quicktiny.cn/api/mcp"
API_KEY = "lb_95edefd519bcfd361b1d008c205f07ff13488e696aa85914433ee589c695679c"

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

target_date = sys.argv[1] if len(sys.argv) > 1 else "2026-07-06"

result = call_tool("board_break_analysis", {
    "tradeDate": target_date,
    "focus": "all",
    "limit": 300,
    "detailLevel": "raw",
    "format": "json"
})

sc = result.get("structuredContent", {})
data = sc.get("data", {})
raw = sc.get("rawData", {})
items = raw.get("items", [])
rows = data.get("rows", [])

print("=== rawData.items条数 ===", len(items))
print("=== rawData.items[0]完整内容 ===")
print(json.dumps(items[0], ensure_ascii=False, indent=2))
print("=== rawData.items[0]的key列表 ===", list(items[0].keys()))
print("=== data.rows[0]的key列表（对比用） ===", list(rows[0].keys()) if rows else "rows为空")
print("=== rawData本身除了items还有别的key吗 ===", list(raw.keys()))