import json
from pathlib import Path

STATE_FILE = Path("/Users/tx/Downloads/研报/.processed.json")
state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
before = len(state)
state = {
    k: v for k, v in state.items()
    if v.get("status") != "needs_ocr" and "内容缺失" not in v.get("digest_line", "")
}
STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"清理前 {before} 条，清理后 {len(state)} 条，已移除误判记录，下次运行会重新处理这些文件。")