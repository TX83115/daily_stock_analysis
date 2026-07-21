"""
feishu_push.py
飞书群自定义机器人 webhook 推送助手（MIS 盘中/盘前报告通道）。

webhook URL 从仓库 .env 的 FEISHU_WEBHOOK_URL 读取（用户 2026-07-21 配置，
Kimi 已测通）。无签名校验（.env 无 FEISHU_WEBHOOK_SECRET）。
既可 import 使用（push_text），也可 CLI：
  python feishu_push.py "标题" "正文"      # 或 echo 正文 | python feishu_push.py "标题"
推送失败不抛异常，返回 False 并打印原因——通道故障绝不阻断上游任务（仓库稳定性护栏：
单一通知渠道失败不拖垮主流程）。
"""
import os, sys, json

ENV_PATH = "/Users/tx/Documents/GitHub/daily_stock_analysis/.env"


def _load_webhook_url():
    url = os.environ.get("FEISHU_WEBHOOK_URL")
    if url:
        return url
    try:
        with open(ENV_PATH) as f:
            for line in f:
                s = line.strip()
                if s.startswith("FEISHU_WEBHOOK_URL="):
                    v = s.split("=", 1)[1].strip().strip('"').strip("'")
                    if v and not v.startswith("your_"):
                        return v
    except OSError:
        pass
    return None


def push_text(text, title=None):
    """推送纯文本（带可选标题行）。返回 True/False，不抛异常。"""
    import requests
    url = _load_webhook_url()
    if not url:
        print("[feishu_push] FEISHU_WEBHOOK_URL 未配置，跳过推送")
        return False
    body = (f"{title}\n{'-' * 24}\n{text}" if title else text)
    try:
        r = requests.post(url, json={"msg_type": "text", "content": {"text": body}},
                          timeout=15)
        data = r.json()
        if data.get("code") == 0 or data.get("StatusCode") == 0:
            return True
        print(f"[feishu_push] 飞书返回异常: {str(data)[:150]}")
        return False
    except Exception as e:
        print(f"[feishu_push] 推送失败: {type(e).__name__}: {str(e)[:100]}")
        return False


if __name__ == "__main__":
    title = sys.argv[1] if len(sys.argv) > 1 else None
    if len(sys.argv) > 2:
        text = sys.argv[2]
    else:
        text = sys.stdin.read()
    ok = push_text(text.strip(), title=title)
    print("推送成功" if ok else "推送失败/未配置")
    sys.exit(0 if ok else 1)
