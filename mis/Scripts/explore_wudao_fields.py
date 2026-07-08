import requests
import json

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

if __name__ == "__main__":
    result = call_tool("limit_up_filter", {
        "date": "2026-07-03", "detailLevel": "standard", "format": "json",
        "limit": 100, "page": 1, "sortBy": "continue_num", "sortOrder": "desc"})

    with open("mis/scripts/_debug_limit_up_filter.json", "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print("已写入 mis/scripts/_debug_limit_up_filter.json，去Cursor左边文件列表里打开这个文件")