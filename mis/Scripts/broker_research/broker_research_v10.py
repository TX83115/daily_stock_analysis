#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
研报知识库 v18 —— 自动扫描文件夹版
------------------------------------------
这是Phase 7要接进Kimi Work调度的版本。不再需要手动改SCREENSHOT_PDF
这一行——脚本会自动扫描 WATCH_FOLDER 里所有形如"2026-07-10.pdf"这种
日期命名的文件，逐个处理。已经完整处理过的日期会被自动跳过（不重新
调用OCR、不重新调用Kimi、不重复写Notion），可以放心每天定时跑这一个
脚本，不用管日期。

用法：
- 每天把GoFullPage截图存成"YYYY-MM-DD.pdf"扔进 WATCH_FOLDER
- 跑这个脚本，它会自动处理所有还没完成的日期
- 接入Kimi Work调度时，直接把这个脚本作为独立的一步加进去即可
"""

import os
import re
import json
import time
from pathlib import Path
from datetime import datetime

import requests
import pdfplumber
from openai import OpenAI

# ========== 配置区 ==========

WATCH_FOLDER = "/Users/tx/Downloads/研报"
CHUNK_LIMIT = None  # None = 每天不限制处理份数

# 永久忽略的日期：这些日期不再处理、不再提醒（例如本地无进度记录但Notion已有记录，
# 经人工确认无需补跑的日期）。按 "YYYY-MM-DD" 格式添加。
IGNORE_DATES = {"2026-07-15"}

KIMI_API_KEY = os.environ.get("KIMI_API_KEY", "在这里粘贴你的Kimi API Key")
KIMI_BASE_URL = "https://api.moonshot.ai/v1"
KIMI_EXTRACT_MODEL = "moonshot-v1-8k"

NOTION_TOKEN = os.environ.get("NOTION_TOKEN", "在这里粘贴你的Notion Integration Token")
NOTION_DATA_SOURCE_ID = "f81a3564-d061-4fa8-b02a-2697a6ce83fe"
DIGEST_DATA_SOURCE_ID = "d9e3a8e6-55ed-4b7f-bab9-cdc493243bd3"
NOTION_VERSION = "2025-09-03"

TARGET_DPI = 150
CROP_LEFT_RATIO = 0.24
CROP_RIGHT_RATIO = 0.76

PROMPT_TEMPLATE_PATH = str(Path(__file__).parent / "kimi_extraction_prompt.md")

DEFAULT_HALF_LIFE = {"A公司背景": 180, "B行业动态": 30, "C短期催化": 3}
VALID_CATEGORIES = {"A公司背景", "B行业动态", "C短期催化"}
GIBBERISH_PATTERN = re.compile(r"^[A-Za-z0-9]{15,}$")
FILENAME_SUFFIX_PATTERN = re.compile(r"\.(pdf|pf|pd|puf|0of|ndf|doc|xif|nnf|prd)\s*$", re.IGNORECASE)
DATE_FILE_PATTERN = re.compile(r"^(\d{4}-\d{2}-\d{2})\.pdf$")

MAX_RETRIES = 3
RETRY_DELAY_SECONDS = 8

client = OpenAI(api_key=KIMI_API_KEY, base_url=KIMI_BASE_URL)


def with_retry(fn, *args, description="操作", **kwargs):
    last_err = None
    for attempt in range(MAX_RETRIES + 1):
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            last_err = e
            if attempt < MAX_RETRIES:
                print(f"  ⚠️ {description}失败（第{attempt + 1}次，{e}），{RETRY_DELAY_SECONDS}秒后重试...")
                time.sleep(RETRY_DELAY_SECONDS)
    raise last_err


def find_date_files(folder: str):
    """扫描文件夹，找出所有形如 2026-07-10.pdf 这种日期命名的文件（按日期升序）。"""
    results = []
    for p in Path(folder).glob("*.pdf"):
        m = DATE_FILE_PATTERN.match(p.name)
        if m:
            results.append((m.group(1), p))
    results.sort(key=lambda x: x[0])
    return results


def resize_and_crop_pdf(src_path: str) -> str:
    print("  正在降分辨率、裁边...")
    pdf = pdfplumber.open(src_path)
    images = []
    for page in pdf.pages:
        im = page.to_image(resolution=TARGET_DPI).original.convert("RGB")
        w, h = im.size
        left = int(w * CROP_LEFT_RATIO)
        right = int(w * CROP_RIGHT_RATIO)
        images.append(im.crop((left, 0, right, h)))
    out_path = str(Path(src_path).with_name(Path(src_path).stem + "_processed.pdf"))
    images[0].save(out_path, save_all=True, append_images=images[1:])
    return out_path


def _do_ocr(pdf_path: str) -> str:
    file_object = client.files.create(file=Path(pdf_path), purpose="file-extract")
    content_json = client.files.content(file_id=file_object.id).text
    client.files.delete(file_id=file_object.id)
    data = json.loads(content_json)
    return data["content"]


def get_ocr_text(screenshot_pdf: Path, ocr_debug_path: Path) -> str:
    if ocr_debug_path.exists():
        return ocr_debug_path.read_text(encoding="utf-8")
    processed_pdf = resize_and_crop_pdf(str(screenshot_pdf))
    print("  正在OCR识别（大文件可能需要一两分钟）...")
    full_text = with_retry(_do_ocr, processed_pdf, description="OCR识别")
    ocr_debug_path.write_text(full_text, encoding="utf-8")
    print(f"  OCR完成，共 {len(full_text)} 字")
    return full_text


def strip_leading_noise(chunk: str) -> str:
    lines = chunk.split("\n")
    cutoff = 0
    for i, line in enumerate(lines[:6]):
        stripped = line.strip()
        if "译文" in stripped or FILENAME_SUFFIX_PATTERN.search(stripped):
            cutoff = i + 1
    while cutoff < len(lines) and len(lines[cutoff].strip()) < 8:
        cutoff += 1
    cleaned = "\n".join(lines[cutoff:]).strip()
    return cleaned if cleaned else chunk


def split_into_chunks(full_text: str, debug_dir: Path):
    parts = full_text.split("收起")
    raw_chunks = [p.strip() for p in parts[:-1] if p.strip()]
    tail = parts[-1].strip()
    rich_chunks = [raw_chunks[0]] + [strip_leading_noise(c) for c in raw_chunks[1:]] if raw_chunks else []
    for i, chunk in enumerate(rich_chunks):
        (debug_dir / f"chunk_{i:02d}.txt").write_text(chunk, encoding="utf-8")
    return rich_chunks, tail


def load_state(state_path: Path) -> dict:
    if state_path.exists():
        return json.loads(state_path.read_text(encoding="utf-8"))
    return {}


def save_state(state_path: Path, state: dict):
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def _txt(record, key, default=""):
    val = record.get(key, default)
    return val if isinstance(val, str) else default


def _lst(record, key):
    val = record.get(key, [])
    if isinstance(val, list):
        return [str(x).strip() for x in val if x and str(x).strip()]
    if isinstance(val, str) and val.strip():
        return [val.strip()]
    return []


def _num(record, key, default):
    val = record.get(key, default)
    if val is None:
        return default
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def is_suspicious_title(title: str, existing_tags: dict) -> bool:
    if not title or not title.strip():
        return True
    t = title.strip()
    if GIBBERISH_PATTERN.match(t):
        return True
    for k in ("主题标签", "A股映射板块", "机构", "涉及标的"):
        if t in existing_tags.get(k, []):
            return True
    return False


def _fetch_existing_tags() -> dict:
    url = f"https://api.notion.com/v1/data_sources/{NOTION_DATA_SOURCE_ID}"
    headers = {"Authorization": f"Bearer {NOTION_TOKEN}", "Notion-Version": NOTION_VERSION}
    resp = requests.get(url, headers=headers, timeout=60)
    resp.raise_for_status()
    schema = resp.json().get("properties", {})

    def opts(field):
        try:
            field_type = schema[field]["type"]
            return [o["name"] for o in schema[field][field_type]["options"]]
        except KeyError:
            return []

    return {
        "主题标签": opts("主题标签"),
        "A股映射板块": opts("A股映射板块"),
        "机构": opts("机构"),
        "涉及标的": opts("涉及标的"),
    }


def get_existing_tags() -> dict:
    return with_retry(_fetch_existing_tags, description="拉取Notion已有标签")


def build_prompt(report_text: str, existing_tags: dict) -> str:
    template = Path(PROMPT_TEMPLATE_PATH).read_text(encoding="utf-8")
    return (
        template
        .replace("{{EXISTING_THEME_TAGS}}", "、".join(existing_tags["主题标签"]))
        .replace("{{EXISTING_SECTOR_TAGS}}", "、".join(existing_tags["A股映射板块"]))
        .replace("{{EXISTING_BANK_TAGS}}", "、".join(existing_tags["机构"]))
        .replace("{{EXISTING_TICKER_TAGS}}", "、".join(existing_tags["涉及标的"]))
        .replace("{{REPORT_TEXT}}", report_text)
    )


def _do_call_kimi_extract(prompt: str) -> dict:
    completion = client.chat.completions.create(
        model=KIMI_EXTRACT_MODEL,
        messages=[
            {"role": "system", "content": "你是一个严格按JSON格式输出的信息提取助手。"},
            {"role": "user", "content": prompt},
        ],
        temperature=0.2,
        max_tokens=2048,
    )
    content = completion.choices[0].message.content
    content = re.sub(r"^```json\s*|\s*```$", "", content.strip())
    return json.loads(content)


def call_kimi_extract(prompt: str) -> dict:
    return with_retry(_do_call_kimi_extract, prompt, description="Kimi结构化提取")


def _notion_json_headers():
    return {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }


def _post_notion(url: str, payload: dict):
    resp = requests.post(url, headers=_notion_json_headers(), json=payload, timeout=60)
    if resp.status_code >= 400:
        print(f"  ⚠️ Notion API报错详情：{resp.text[:800]}")
    resp.raise_for_status()
    return resp


def post_notion(url: str, payload: dict):
    return with_retry(_post_notion, url, payload, description="Notion写入")


def _patch_notion(url: str, payload: dict):
    resp = requests.patch(url, headers=_notion_json_headers(), json=payload, timeout=60)
    if resp.status_code >= 400:
        print(f"  ⚠️ Notion API报错详情：{resp.text[:800]}")
    resp.raise_for_status()
    return resp


def patch_notion(url: str, payload: dict):
    return with_retry(_patch_notion, url, payload, description="Notion追加内容")


def check_for_existing_records(date_str: str) -> int:
    url = f"https://api.notion.com/v1/data_sources/{NOTION_DATA_SOURCE_ID}/query"
    payload = {"filter": {"property": "入库日期", "date": {"equals": date_str}}, "page_size": 1}
    resp = with_retry(requests.post, url, headers=_notion_json_headers(), json=payload, timeout=60,
                       description="检查是否已有当天记录")
    resp.raise_for_status()
    return len(resp.json().get("results", []))


def create_notion_page(record: dict) -> dict:
    category = _txt(record, "类别")
    if category not in VALID_CATEGORIES:
        category = "B行业动态"
    half_life = _num(record, "半衰期天数", DEFAULT_HALF_LIFE.get(category, 30))

    body_text = _txt(record, "要点摘要")
    reason = _txt(record, "半衰期理由")
    full_body_for_page = body_text + (f"\n\n（半衰期调整理由：{reason}）" if reason else "")

    properties = {
        "标题": {"title": [{"text": {"content": _txt(record, "标题", "未命名研报") or "未命名研报"}}]},
        "原始代码": {"rich_text": [{"text": {"content": _txt(record, "原始代码")}}]},
        "涉及标的": {"multi_select": [{"name": t} for t in _lst(record, "涉及标的")]},
        "覆盖市场": {"multi_select": [{"name": t} for t in _lst(record, "覆盖市场")]},
        "A股映射板块": {"multi_select": [{"name": t} for t in _lst(record, "A股映射板块")]},
        "细分板块": {"multi_select": [{"name": t} for t in _lst(record, "细分板块")]},
        "主题标签": {"multi_select": [{"name": t} for t in _lst(record, "主题标签")]},
        "类别": {"select": {"name": category}},
        "半衰期天数": {"number": half_life},
        "处理状态": {"select": {"name": "待复核"}},
        "分析师": {"rich_text": [{"text": {"content": _txt(record, "分析师")}}]},
        "点名个股代码": {"rich_text": [{"text": {"content": ", ".join(_lst(record, "点名个股"))}}]},
    }
    date_val = _txt(record, "发布日期")
    if date_val:
        properties["发布日期"] = {"date": {"start": date_val}}
    properties["入库日期"] = {"date": {"start": datetime.now().strftime("%Y-%m-%d")}}
    bank_val = _txt(record, "机构")
    if bank_val:
        properties["机构"] = {"select": {"name": bank_val}}
    catalyst_type = _txt(record, "催化剂类型")
    if catalyst_type:
        properties["催化剂类型"] = {"select": {"name": catalyst_type}}
    catalyst_timeliness = _txt(record, "催化剂时效")
    if catalyst_timeliness:
        properties["催化剂时效"] = {"select": {"name": catalyst_timeliness}}

    payload = {
        "parent": {"data_source_id": NOTION_DATA_SOURCE_ID},
        "properties": properties,
        "children": [{
            "object": "block", "type": "paragraph",
            "paragraph": {"rich_text": [{"type": "text", "text": {"content": full_body_for_page[:2000]}}]},
        }],
    }
    resp = post_notion("https://api.notion.com/v1/pages", payload)
    page_url = resp.json().get("url", "")

    one_liner = _txt(record, "一句话结论") or (body_text[:60] + "…" if body_text else "")
    tags = "、".join(_lst(record, "主题标签")[:5])
    scope = "、".join(_lst(record, "A股映射板块") or _lst(record, "覆盖市场"))

    return {
        "title": _txt(record, "标题"),
        "bank": bank_val,
        "one_liner": one_liner,
        "tags": tags,
        "scope": scope,
        "summary": body_text,
        "url": page_url,
    }


def process_one_chunk(chunk_text: str, existing_tags: dict) -> dict:
    try:
        prompt = build_prompt(chunk_text, existing_tags)
        record = call_kimi_extract(prompt)

        title = _txt(record, "标题")
        suspicious = False
        if is_suspicious_title(title, existing_tags):
            record["标题"] = f"⚠️待核对：{title[:20] if title else '未命名'}"
            suspicious = True

        entry = create_notion_page(record)
        return {
            "status": "ok",
            "entry": entry,
            "suspicious": suspicious,
            "new_tags": {k: _lst(record, k) for k in ("主题标签", "A股映射板块", "机构", "涉及标的")},
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


def build_digest_report_blocks(entry: dict) -> list:
    blocks = [{
        "object": "block", "type": "heading_3",
        "heading_3": {"rich_text": [{"type": "text", "text": {"content": f"{entry['title']} — {entry['bank']}"}}]},
    }]
    body_rich_text = [{
        "type": "text",
        "text": {"content": f"{entry['one_liner']}\n标签：{entry['tags']} ｜ 范围：{entry['scope']}\n\n"},
    }]
    if entry["summary"]:
        body_rich_text.append({"type": "text", "text": {"content": entry["summary"][:1800]}})
    blocks.append({"object": "block", "type": "paragraph", "paragraph": {"rich_text": body_rich_text}})

    if entry["url"]:
        blocks.append({
            "object": "block", "type": "paragraph",
            "paragraph": {"rich_text": [{
                "type": "text",
                "text": {"content": "查看完整结构化记录 →", "link": {"url": entry["url"]}},
            }]},
        })
    blocks.append({"object": "block", "type": "divider", "divider": {}})
    return blocks


def upsert_daily_digest(digest_entries: list, date_str: str):
    if not digest_entries:
        return
    query_url = f"https://api.notion.com/v1/data_sources/{DIGEST_DATA_SOURCE_ID}/query"
    resp = with_retry(
        requests.post, query_url, headers=_notion_json_headers(),
        json={"filter": {"property": "日期", "date": {"equals": date_str}}}, timeout=60,
        description="查询今日已有速览",
    )
    if resp.status_code == 200:
        for r in resp.json().get("results", []):
            patch_notion(f"https://api.notion.com/v1/pages/{r['id']}", {"archived": True})

    children = [{
        "object": "block", "type": "paragraph",
        "paragraph": {"rich_text": [{"type": "text", "text": {"content": f"今日处理：{len(digest_entries)} 份研报"}}]},
    }]
    for entry in digest_entries:
        children.extend(build_digest_report_blocks(entry))

    first_batch, rest = children[:100], children[100:]
    payload = {
        "parent": {"data_source_id": DIGEST_DATA_SOURCE_ID},
        "properties": {
            "标题": {"title": [{"text": {"content": f"{date_str} 研报速览"}}]},
            "日期": {"date": {"start": date_str}},
            "研报数量": {"number": len(digest_entries)},
        },
        "children": first_batch,
    }
    resp2 = post_notion("https://api.notion.com/v1/pages", payload)
    page_id = resp2.json()["id"]
    print(f"  已更新速览：{date_str}（共{len(digest_entries)}份）")

    while rest:
        batch, rest = rest[:100], rest[100:]
        patch_notion(f"https://api.notion.com/v1/blocks/{page_id}/children", {"children": batch})


def process_one_date(date_str: str, screenshot_pdf: Path):
    debug_dir = Path(WATCH_FOLDER) / f"{date_str}_debug"
    debug_dir.mkdir(parents=True, exist_ok=True)
    ocr_debug_path = debug_dir / "ocr_full.txt"
    state_path = debug_dir / "state.json"

    full_text = get_ocr_text(screenshot_pdf, ocr_debug_path)
    rich_chunks, tail = split_into_chunks(full_text, debug_dir)
    to_process_all = rich_chunks if CHUNK_LIMIT is None else rich_chunks[:CHUNK_LIMIT]

    state = load_state(state_path)

    all_done = bool(state) and all(
        state.get(str(i), {}).get("status") == "ok" for i in range(len(to_process_all))
    )
    if all_done:
        print(f"  {date_str} 已全部处理完成，跳过。")
        return

    if not state:
        existing_count = check_for_existing_records(date_str)
        if existing_count > 0:
            print(f"  ⚠️ 警告：本地没有 {date_str} 的处理进度记录，但Notion里已经有这一天的记录了。"
                  f"直接往下跑可能会产生重复记录，已跳过这一天，请人工核实。")
            return

    print(f"  共 {len(to_process_all)} 份研报，其中已成功 "
          f"{sum(1 for i in range(len(to_process_all)) if state.get(str(i), {}).get('status') == 'ok')} 份")

    existing_tags = get_existing_tags()
    suspicious = []

    for idx in range(len(to_process_all)):
        if state.get(str(idx), {}).get("status") == "ok":
            continue
        chunk_text = to_process_all[idx]
        print(f"  处理第 {idx + 1}/{len(to_process_all)} 份（长度 {len(chunk_text)} 字）...")
        result = process_one_chunk(chunk_text, existing_tags)
        state[str(idx)] = result
        save_state(state_path, state)

        if result["status"] == "ok":
            print(f"    已写入：{result['entry']['title']}")
            if result.get("suspicious"):
                suspicious.append(idx + 1)
            for k, values in result["new_tags"].items():
                for v in values:
                    if v not in existing_tags.get(k, []):
                        existing_tags.setdefault(k, []).append(v)
        else:
            print(f"    处理失败（已记录，下次会自动重试）：{result['message']}")

    digest_entries = [
        state[str(i)]["entry"] for i in range(len(to_process_all))
        if state.get(str(i), {}).get("status") == "ok"
    ]
    upsert_daily_digest(digest_entries, date_str)

    failed_count = len(to_process_all) - len(digest_entries)
    if failed_count:
        print(f"  ⚠️ {date_str} 仍有 {failed_count} 份处理失败，下次跑会自动只重试这些")
    if suspicious:
        print(f"  ⚠️ {date_str} 第 {suspicious} 份标题异常，建议去Notion核对")


def main():
    date_files = find_date_files(WATCH_FOLDER)
    if not date_files:
        print(f"在 {WATCH_FOLDER} 里没有发现日期格式的截图PDF（形如 2026-07-10.pdf）。")
        return

    print(f"发现 {len(date_files)} 个日期文件：{', '.join(d for d, _ in date_files)}\n")
    for date_str, path in date_files:
        if date_str in IGNORE_DATES:
            print(f"=== {date_str} 在忽略列表中，跳过 ===\n")
            continue
        print(f"=== 处理 {date_str} ===")
        try:
            process_one_date(date_str, path)
        except Exception as e:
            print(f"  ⚠️ {date_str} 处理过程中出现未预期的错误：{e}")
        print()

    print("全部日期处理完成。")


if __name__ == "__main__":
    main()