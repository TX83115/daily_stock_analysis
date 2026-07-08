#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
研报知识库自动化提取脚本 v9
------------------------------------------
v9变化（相比v8，重要修复）：
- 修复严重误伤问题：v7/v8的水印识别用了"仅供知识星球【猫哥的研报圈】
  会员使用"这句话里的全部字符做锚点，但其中"的、报、会、用、研、供、球"
  这些字在正常财经研报里极其常见，导致大段正文被误判成水印删除
  （中文报告受伤尤其严重，很多被腰斩到几十个字，误判成"疑似扫描版"）
- 改为只用"猫""哥"这两个真正稀有、几乎不会出现在研报正文里的字做锚点，
  必须在40字小窗口内同时出现"猫"和"哥"才判定为水印，局部剔除，
  不再殃及无辜的正文
- 移除了v8里基于词频统计的兜底过滤器（同样有误伤常见字的风险）
"""

import os
import re
import json
from pathlib import Path
from datetime import datetime
from collections import Counter

import requests
import pdfplumber

# ========== 配置区 ==========

WATCH_FOLDER = "/Users/tx/Downloads/研报"
STATE_FILE = str(Path(WATCH_FOLDER) / ".processed.json")

# 设为True时：只提取文字打印诊断信息，不调用Kimi、不调用Notion，完全免费
DIAGNOSE_ONLY = True

# 设为True才会把PDF本体上传挂到Notion记录上（目前该功能不稳定，默认关闭）
UPLOAD_PDF_TO_NOTION = False

KIMI_API_KEY = os.environ.get("KIMI_API_KEY", "在这里粘贴你的Kimi API Key")
KIMI_BASE_URL = "https://api.moonshot.cn/v1"
KIMI_MODEL = "moonshot-v1-32k"

NOTION_TOKEN = os.environ.get("NOTION_TOKEN", "在这里粘贴你的Notion Integration Token")
NOTION_DATA_SOURCE_ID = "f81a3564-d061-4fa8-b02a-2697a6ce83fe"  # 研报知识库
DIGEST_DATA_SOURCE_ID = "d9e3a8e6-55ed-4b7f-bab9-cdc493243bd3"  # 研报速览
NOTION_VERSION = "2025-09-03"

MAX_CHARS_TO_KIMI = 20000
MIN_USABLE_CHARS = 300  # 清洗后正文低于这个字数，判定为疑似扫描/图片版PDF，跳过不调用Kimi
INTERLEAVE_AVG_RUN_THRESHOLD = 2.5  # 连续同语言片段平均长度低于此值，判定为文字层交错损坏

PROMPT_TEMPLATE_PATH = str(Path(__file__).parent / "kimi_extraction_prompt.md")

# ========== 以下正常不需要改动 ==========

DEFAULT_HALF_LIFE = {"A公司背景": 180, "B行业动态": 30, "C短期催化": 3}
VALID_CATEGORIES = {"A公司背景", "B行业动态", "C短期催化"}

STOP_MARKERS = [
    "Analyst Certification", "分析师声明",
    "Important Disclosures", "重要声明",
    "Appendix A-1",
]

BANK_ALIASES = {
    "Nomura": ["nomura", "野村"],
    "Morgan Stanley": ["morgan stanley", "大摩", "摩根士丹利"],
    "Goldman Sachs": ["goldman sachs", "高盛"],
    "JPMorgan": ["jpmorgan", "j.p. morgan", "摩根大通"],
    "UBS": ["ubs", "瑞银"],
    "Citi": ["citi", "花旗"],
    "CICC": ["中金公司", "中金"],
    "CITIC": ["中信证券", "中信"],
    "Bank of America": ["bank of america", "bofa", "美银"],
    "HSBC": ["hsbc", "汇丰"],
    "CLSA": ["clsa", "里昂"],
    "Jefferies": ["jefferies", "杰富瑞"],
    "Deutsche Bank": ["deutsche bank", "德意志银行"],
}

DATE_PATTERNS = [
    re.compile(r"\d{4}-\d{2}-\d{2}"),
    re.compile(r"\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\s+\d{4}", re.IGNORECASE),
    re.compile(r"\d{4}年\d{1,2}月\d{1,2}日"),
]

GIBBERISH_PATTERN = re.compile(r"^[A-Za-z0-9]{15,}$")
CID_PATTERN = re.compile(r"\(cid:\d+\)")
SCRIPT_RUN_PATTERN = re.compile(r"[\u4e00-\u9fff]+|[A-Za-z]+")

# 只用真正稀有、不会出现在正常研报正文里的字做水印锚点
RARE_WATERMARK_CHARS = ("猫", "哥")
WATERMARK_CLUSTER_WINDOW = 40


def load_state() -> dict:
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_state(state: dict):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def clean_page_text(page) -> str:
    """第一道过滤：按'同页整行完全重复4次以上'识别水印戳记并剔除。
    要求整行文字逐字符完全相同，正常正文几乎不会触发。"""
    raw = page.extract_text() or ""
    lines = raw.split("\n")
    counts = Counter(line.strip() for line in lines if line.strip())
    repeated = {line for line, c in counts.items() if c >= 4 and len(line) <= 40}
    cleaned_lines = [line for line in lines if line.strip() not in repeated]
    return "\n".join(cleaned_lines)


def strip_known_watermark(text: str) -> str:
    """第二道过滤：只用"猫""哥"这两个真正稀有的字做锚点。
    必须在一个小窗口内同时出现这两个字，才判定该局部片段是水印，
    仅剔除该片段，不触碰其他正文（即使正文里偶尔单独出现"猫"或"哥"
    也不会被误伤，因为要求两个字同时出现在窗口内）。"""
    positions = [i for i, ch in enumerate(text) if ch in RARE_WATERMARK_CHARS]
    if len(positions) < 2:
        return text

    intervals = []
    for p in positions:
        start, end = max(0, p - WATERMARK_CLUSTER_WINDOW), min(len(text), p + WATERMARK_CLUSTER_WINDOW)
        if intervals and start <= intervals[-1][1]:
            intervals[-1][1] = max(intervals[-1][1], end)
        else:
            intervals.append([start, end])

    to_remove = []
    for start, end in intervals:
        segment = text[start:end]
        if "猫" in segment and "哥" in segment:
            to_remove.append((start, end))

    if not to_remove:
        return text

    result = []
    last = 0
    for start, end in to_remove:
        result.append(text[last:start])
        last = end
    result.append(text[last:])
    return "".join(result)


def looks_interleaved(text: str, sample_len: int = 3000) -> bool:
    """检测中英文字符是否逐字符交替出现（双层文字重叠损坏的典型特征）。"""
    sample = text[:sample_len]
    runs = SCRIPT_RUN_PATTERN.findall(sample)
    if len(runs) < 20:
        return False
    avg_run_len = sum(len(r) for r in runs) / len(runs)
    return avg_run_len < INTERLEAVE_AVG_RUN_THRESHOLD


def get_first_page_text(pdf_path: str) -> str:
    with pdfplumber.open(pdf_path) as pdf:
        if not pdf.pages:
            return ""
        return clean_page_text(pdf.pages[0])


def detect_bank(text: str) -> str:
    lower = text.lower()
    for canonical, aliases in BANK_ALIASES.items():
        for alias in aliases:
            if alias.lower() in lower:
                return canonical
    return "unknown"


def detect_date_str(text: str) -> str:
    for pattern in DATE_PATTERNS:
        m = pattern.search(text)
        if m:
            return m.group(0)
    return "unknown"


def cjk_ratio(text: str) -> float:
    if not text:
        return 0.0
    cjk_count = sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff")
    total = sum(1 for ch in text if not ch.isspace())
    return cjk_count / total if total else 0.0


def group_and_filter_duplicates(pdf_files):
    fingerprints = {}
    for p in pdf_files:
        text = get_first_page_text(str(p))
        bank = detect_bank(text)
        date_str = detect_date_str(text)
        ratio = cjk_ratio(text)
        key = (bank, date_str)
        fingerprints.setdefault(key, []).append((p, ratio))

    to_process = []
    skipped = {}
    for key, group in fingerprints.items():
        if key[0] == "unknown" or len(group) == 1:
            to_process.extend(p for p, _ in group)
            continue
        group_sorted = sorted(group, key=lambda x: x[1])
        kept_path, _ = group_sorted[0]
        to_process.append(kept_path)
        for p, _ in group_sorted[1:]:
            skipped[p.name] = f"疑似为《{kept_path.name}》的中文翻译版，已跳过"

    return to_process, skipped


def extract_pdf_text(pdf_path: str) -> str:
    text_parts = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            page_text = clean_page_text(page)
            hit_marker = next((m for m in STOP_MARKERS if m in page_text), None)
            if hit_marker:
                text_parts.append(page_text.split(hit_marker)[0])
                break
            text_parts.append(page_text)
    full_text = "\n".join(text_parts)
    full_text = strip_known_watermark(full_text)
    full_text = CID_PATTERN.sub("", full_text)
    return full_text[:MAX_CHARS_TO_KIMI]


def get_existing_tags() -> dict:
    url = f"https://api.notion.com/v1/data_sources/{NOTION_DATA_SOURCE_ID}"
    headers = {"Authorization": f"Bearer {NOTION_TOKEN}", "Notion-Version": NOTION_VERSION}
    resp = requests.get(url, headers=headers)
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


def call_kimi(prompt: str) -> dict:
    url = f"{KIMI_BASE_URL}/chat/completions"
    headers = {"Authorization": f"Bearer {KIMI_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": KIMI_MODEL,
        "messages": [
            {"role": "system", "content": "你是一个严格按JSON格式输出的信息提取助手。"},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.2,
        "max_tokens": 4096,
    }
    resp = requests.post(url, headers=headers, json=payload, timeout=120)
    resp.raise_for_status()
    content = resp.json()["choices"][0]["message"]["content"]
    content = re.sub(r"^```json\s*|\s*```$", "", content.strip())
    return json.loads(content)


def _notion_auth_headers():
    return {"Authorization": f"Bearer {NOTION_TOKEN}", "Notion-Version": NOTION_VERSION}


def _notion_json_headers():
    return {**_notion_auth_headers(), "Content-Type": "application/json"}


def upload_pdf_to_notion(pdf_path: Path):
    try:
        create_resp = requests.post(
            "https://api.notion.com/v1/file_uploads",
            headers=_notion_json_headers(),
            json={"filename": pdf_path.name, "content_type": "application/pdf"},
        )
        create_resp.raise_for_status()
        upload_id = create_resp.json()["id"]

        with open(pdf_path, "rb") as f:
            send_resp = requests.post(
                f"https://api.notion.com/v1/file_uploads/{upload_id}/send",
                headers=_notion_auth_headers(),
                files={"file": (pdf_path.name, f, "application/pdf")},
            )
        send_resp.raise_for_status()
        return upload_id
    except requests.exceptions.HTTPError as e:
        detail = ""
        try:
            detail = e.response.text[:300]
        except Exception:
            pass
        print(f"  ⚠️ PDF上传Notion失败：{e}  详情：{detail}")
        return None
    except Exception as e:
        print(f"  ⚠️ PDF上传Notion失败：{e}")
        return None


def create_notion_page(record: dict, pdf_path: Path) -> dict:
    category = _txt(record, "类别")
    if category not in VALID_CATEGORIES:
        category = "B行业动态"
    half_life = _num(record, "半衰期天数", DEFAULT_HALF_LIFE.get(category, 30))

    body_text = _txt(record, "要点摘要")
    reason = _txt(record, "半衰期理由")
    if reason:
        body_text += f"\n\n（半衰期调整理由：{reason}）"

    properties = {
        "标题": {"title": [{"text": {"content": _txt(record, "标题", "未命名研报") or "未命名研报"}}]},
        "原始代码": {"rich_text": [{"text": {"content": _txt(record, "原始代码")}}]},
        "涉及标的": {"multi_select": [{"name": t} for t in _lst(record, "涉及标的")]},
        "覆盖市场": {"multi_select": [{"name": t} for t in _lst(record, "覆盖市场")]},
        "A股映射板块": {"multi_select": [{"name": t} for t in _lst(record, "A股映射板块")]},
        "主题标签": {"multi_select": [{"name": t} for t in _lst(record, "主题标签")]},
        "类别": {"select": {"name": category}},
        "半衰期天数": {"number": half_life},
        "处理状态": {"select": {"name": "待复核"}},
        "分析师": {"rich_text": [{"text": {"content": _txt(record, "分析师")}}]},
    }
    date_val = _txt(record, "发布日期")
    if date_val:
        properties["发布日期"] = {"date": {"start": date_val}}
    bank_val = _txt(record, "机构")
    if bank_val:
        properties["机构"] = {"select": {"name": bank_val}}

    if UPLOAD_PDF_TO_NOTION:
        upload_id = upload_pdf_to_notion(pdf_path)
        if upload_id:
            properties["原始PDF"] = {"files": [{"type": "file_upload", "file_upload": {"id": upload_id}, "name": pdf_path.name}]}

    payload = {
        "parent": {"data_source_id": NOTION_DATA_SOURCE_ID},
        "properties": properties,
        "children": [{
            "object": "block", "type": "paragraph",
            "paragraph": {"rich_text": [{"type": "text", "text": {"content": body_text[:2000]}}]},
        }],
    }
    resp = requests.post("https://api.notion.com/v1/pages", headers=_notion_json_headers(), json=payload)
    resp.raise_for_status()
    page_url = resp.json().get("url", "")
    print(f"  已写入主记录：{_txt(record, '标题')}")

    catalyst_lines = []
    catalysts = record.get("催化事件", [])
    if not isinstance(catalysts, list):
        catalysts = []
    for event in catalysts:
        if not isinstance(event, dict):
            continue
        event_props = {
            "标题": {"title": [{"text": {"content": f"催化提醒：{_txt(event, '标题')}"}}]},
            "A股映射板块": {"multi_select": [{"name": t} for t in _lst(event, "A股映射板块")]},
            "类别": {"select": {"name": "C短期催化"}},
            "半衰期天数": {"number": 3},
            "处理状态": {"select": {"name": "待复核"}},
        }
        if date_val:
            event_props["发布日期"] = {"date": {"start": date_val}}
        expiry = _txt(event, "失效日期")
        if expiry:
            event_props["失效日期"] = {"date": {"start": expiry}}
        if bank_val:
            event_props["机构"] = {"select": {"name": bank_val}}

        event_payload = {
            "parent": {"data_source_id": NOTION_DATA_SOURCE_ID},
            "properties": event_props,
            "children": [{
                "object": "block", "type": "paragraph",
                "paragraph": {"rich_text": [{"type": "text", "text": {"content": _txt(event, "说明")}}]},
            }],
        }
        r2 = requests.post("https://api.notion.com/v1/pages", headers=_notion_json_headers(), json=event_payload)
        r2.raise_for_status()
        catalyst_lines.append(f"- **{date_val}** {_txt(event,'标题')}（{bank_val}）：{_txt(event,'说明')}")
        print(f"  已写入催化记录：{_txt(event, '标题')}")

    one_liner = _txt(record, "一句话结论") or (body_text[:60] + "…" if body_text else "")
    tags = "、".join(_lst(record, "主题标签")[:5])
    scope = "、".join(_lst(record, "A股映射板块") or _lst(record, "覆盖市场"))
    digest_line = (
        f"**{_txt(record,'标题')}** — {bank_val}\n"
        f"{one_liner}\n"
        f"标签：{tags} ｜ 范围：{scope}\n"
        f"[查看完整记录]({page_url})"
    )

    return {"digest_line": digest_line, "catalyst_lines": catalyst_lines}


def upsert_daily_digest(state: dict):
    today_str = datetime.now().strftime("%Y-%m-%d")
    lines, catalyst_lines, count = [], [], 0
    for info in state.values():
        if info.get("status") == "ok" and str(info.get("processed_at", "")).startswith(today_str):
            count += 1
            if info.get("digest_line"):
                lines.append(info["digest_line"])
            catalyst_lines.extend(info.get("catalyst_lines", []))

    if count == 0:
        return

    query_url = f"https://api.notion.com/v1/data_sources/{DIGEST_DATA_SOURCE_ID}/query"
    resp = requests.post(query_url, headers=_notion_json_headers(),
                          json={"filter": {"property": "日期", "date": {"equals": today_str}}})
    if resp.status_code == 200:
        for r in resp.json().get("results", []):
            requests.patch(f"https://api.notion.com/v1/pages/{r['id']}",
                            headers=_notion_json_headers(), json={"archived": True})
    else:
        print(f"  查询今日速览时出错（不影响主流程）：{resp.status_code} {resp.text[:200]}")

    children = [{
        "object": "block", "type": "paragraph",
        "paragraph": {"rich_text": [{"type": "text", "text": {"content": f"今日处理：{count} 份研报"}}]},
    }]
    for line in lines:
        children.append({
            "object": "block", "type": "paragraph",
            "paragraph": {"rich_text": [{"type": "text", "text": {"content": line[:2000]}}]},
        })
    if catalyst_lines:
        children.append({
            "object": "block", "type": "heading_2",
            "heading_2": {"rich_text": [{"type": "text", "text": {"content": "本周催化提醒"}}]},
        })
        for cl in catalyst_lines:
            children.append({
                "object": "block", "type": "paragraph",
                "paragraph": {"rich_text": [{"type": "text", "text": {"content": cl[:2000]}}]},
            })

    payload = {
        "parent": {"data_source_id": DIGEST_DATA_SOURCE_ID},
        "properties": {
            "标题": {"title": [{"text": {"content": f"{today_str} 研报速览"}}]},
            "日期": {"date": {"start": today_str}},
            "研报数量": {"number": count},
        },
        "children": children,
    }
    resp2 = requests.post("https://api.notion.com/v1/pages", headers=_notion_json_headers(), json=payload)
    resp2.raise_for_status()
    print(f"已更新今日速览：{today_str}（共{count}份）")


def main():
    all_pdfs = sorted(Path(WATCH_FOLDER).glob("*.pdf"))

    if DIAGNOSE_ONLY:
        print("=== 诊断模式：只提取文字，不调用Kimi/Notion，完全免费 ===")
        for pdf_path in all_pdfs:
            text = extract_pdf_text(str(pdf_path))
            preview = text[:80].replace("\n", " ")
            flags = []
            if looks_interleaved(text):
                flags.append("⚠️ 疑似中英文字层交错损坏")
            if len(text.strip()) < MIN_USABLE_CHARS:
                flags.append("⚠️ 疑似扫描/图片版")
            flag_str = "  " + " / ".join(flags) if flags else ""
            print(f"{pdf_path.name}\n  提取到 {len(text)} 字{flag_str}，开头预览：{preview!r}\n")
        return

    state = load_state()
    existing_tags = get_existing_tags()

    def is_pending(name):
        entry = state.get(name)
        if entry is None:
            return True
        return str(entry.get("status", "")).startswith("error")

    pending_pdfs = [p for p in all_pdfs if is_pending(p.name)]

    if not pending_pdfs:
        print("没有新文件需要处理。")
        return

    to_process, skipped = group_and_filter_duplicates(pending_pdfs)

    for name, reason in skipped.items():
        print(f"跳过：{name} —— {reason}")
        state[name] = {"processed_at": datetime.now().isoformat(), "status": f"skipped_duplicate: {reason}"}
    if skipped:
        save_state(state)

    print(f"发现 {len(to_process)} 份待处理研报（已自动跳过 {len(skipped)} 份疑似翻译重复）。")

    suspicious = []
    needs_ocr = []
    interleaved = []
    for pdf_path in to_process:
        print(f"处理：{pdf_path.name}")
        try:
            text = extract_pdf_text(str(pdf_path))
            print(f"  提取到正文约 {len(text)} 字（已过滤水印噪音）")

            if looks_interleaved(text):
                print(f"  ⚠️ 正文疑似中英文字层交错损坏，跳过不调用Kimi，建议改用英文原版")
                state[pdf_path.name] = {"processed_at": datetime.now().isoformat(), "status": "text_interleaved"}
                save_state(state)
                interleaved.append(pdf_path.name)
                continue

            if len(text.strip()) < MIN_USABLE_CHARS:
                print(f"  ⚠️ 正文过少，疑似扫描/图片版PDF，跳过不调用Kimi，请人工核对原始文件")
                state[pdf_path.name] = {"processed_at": datetime.now().isoformat(), "status": "needs_ocr"}
                save_state(state)
                needs_ocr.append(pdf_path.name)
                continue

            prompt = build_prompt(text, existing_tags)
            record = call_kimi(prompt)

            title = _txt(record, "标题")
            if is_suspicious_title(title, existing_tags):
                print(f"  ⚠️ 标题疑似异常（原始返回：{title!r}），已用文件名兜底，请去Notion核对")
                record["标题"] = f"⚠️待核对：{pdf_path.stem}"
                suspicious.append(pdf_path.name)

            result = create_notion_page(record, pdf_path)
            state[pdf_path.name] = {
                "processed_at": datetime.now().isoformat(),
                "status": "ok",
                "digest_line": result["digest_line"],
                "catalyst_lines": result["catalyst_lines"],
            }
            for k in ("主题标签", "A股映射板块", "机构", "涉及标的"):
                for v in _lst(record, k):
                    if v not in existing_tags.get(k, []):
                        existing_tags.setdefault(k, []).append(v)
        except Exception as e:
            print(f"  处理失败：{e}")
            state[pdf_path.name] = {"processed_at": datetime.now().isoformat(), "status": f"error: {e}"}
        save_state(state)

    upsert_daily_digest(state)

    if suspicious:
        print(f"\n⚠️ 以下 {len(suspicious)} 份文件标题被判定异常，建议去Notion核对：")
        for name in suspicious:
            print(f"  - {name}")

    if needs_ocr:
        print(f"\n⚠️ 以下 {len(needs_ocr)} 份文件疑似扫描/图片版，未调用Kimi，建议人工核对：")
        for name in needs_ocr:
            print(f"  - {name}")

    if interleaved:
        print(f"\n⚠️ 以下 {len(interleaved)} 份文件疑似中英文字层交错损坏，未调用Kimi，建议改用英文原版：")
        for name in interleaved:
            print(f"  - {name}")

    print("全部处理完成。")


if __name__ == "__main__":
    main()