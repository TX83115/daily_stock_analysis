#!/usr/bin/env python3
"""
r2_sync.py —— MIS 晚间重链上云的 R2 持久层通用工具（S1）。

作用：把本地那份大 DuckDB（market.duckdb）与对象存储之间做「下载 / 校验 / 上传」，
让 GitHub Actions 这类无状态云端每次「下载 DB → 跑链 → 传回 DB」，无需常驻服务器。

设计要点（对应总图 3.2 灾备强制要求）：
  1. 用通用 S3 客户端（boto3 + 自定义 endpoint_url），**不绑死 Cloudflare 专有 SDK**。
     换 Backblaze B2 / AWS S3 / Wasabi 只需改 R2_ENDPOINT + 两个密钥，代码一行不用动。
  2. R2 内保留最近 N 份带日期的历史 DB（默认 8，仿本地 iCloud 8 份策略），
     另维护一个 market_latest.duckdb 指针指向当前最新，云端下载只认 latest。

凭据来源（值本身绝不写死在代码里）：
  - 云端 GitHub Actions：作为 env 注入（secrets）。
  - 本地：env 未设置时，从 ~/.env 读取 R2_ACCESS_KEY_ID / R2_SECRET_ACCESS_KEY / R2_ENDPOINT。
  可选 R2_BUCKET（默认 "mis-runtime"）、R2_PREFIX（默认 "db"）、R2_KEEP（默认 8）。

CLI：
  python r2_sync.py selftest                 # 小文件 put/get/delete，验证连通与桶名，不碰大 DB
  python r2_sync.py upload  <local_db_path>  # 上传为 db/market_<YYYY-MM-DD>.duckdb + 刷新 latest + 清理旧份
  python r2_sync.py download <local_db_path> # 下载 db/market_latest.duckdb 到本地路径
  python r2_sync.py validate <local_db_path> # 校验 DB 可连、v_daily_qfq 存在且有行
  python r2_sync.py list                     # 列出 R2 内现有 DB 快照
"""

import datetime
import os
import re
import sys

DEFAULT_BUCKET = "mis-runtime"
DEFAULT_PREFIX = "db"
DEFAULT_KEEP = 8
LATEST_NAME = "market_latest.duckdb"
DATED_RE = re.compile(r"market_(\d{4}-\d{2}-\d{2})\.duckdb$")


# ---------------------------------------------------------------- 凭据加载

def _load_env_file(keys, path=None):
    """env 里缺失的 key 从 ~/.env 补齐（云端有真 env 变量时此步为 no-op）。值不打印。"""
    path = path or os.path.expanduser("~/.env")
    if not os.path.isfile(path):
        return
    want = {k for k in keys if not os.environ.get(k)}
    if not want:
        return
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k = k.strip()
            if k in want:
                os.environ.setdefault(k, v.strip().strip("'\""))


def _cfg():
    _load_env_file(["R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_ENDPOINT",
                    "R2_BUCKET", "R2_PREFIX", "R2_KEEP"])
    missing = [k for k in ("R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_ENDPOINT")
               if not os.environ.get(k)]
    if missing:
        raise SystemExit(f"ERROR: 缺少 R2 凭据环境变量: {', '.join(missing)}"
                         "（云端应配为 GitHub secret；本地应在 ~/.env 中提供）")
    return {
        "endpoint": os.environ["R2_ENDPOINT"],
        "access_key": os.environ["R2_ACCESS_KEY_ID"],
        "secret_key": os.environ["R2_SECRET_ACCESS_KEY"],
        "bucket": os.environ.get("R2_BUCKET", DEFAULT_BUCKET),
        "prefix": os.environ.get("R2_PREFIX", DEFAULT_PREFIX).strip("/"),
        "keep": int(os.environ.get("R2_KEEP", DEFAULT_KEEP)),
    }


def _client(cfg):
    import boto3
    from botocore.config import Config
    return boto3.client(
        "s3",
        endpoint_url=cfg["endpoint"],
        aws_access_key_id=cfg["access_key"],
        aws_secret_access_key=cfg["secret_key"],
        region_name="auto",  # R2 用 "auto"
        config=Config(signature_version="s3v4",
                      retries={"max_attempts": 3, "mode": "standard"}),
    )


def _key(cfg, name):
    return f"{cfg['prefix']}/{name}" if cfg["prefix"] else name


# ---------------------------------------------------------------- 校验

def validate_db(local_path):
    """DB 完整性最小校验：能连、v_daily_qfq 视图存在且有行。返回行数。"""
    import duckdb
    if not os.path.isfile(local_path):
        raise SystemExit(f"ERROR: 本地 DB 不存在: {local_path}")
    con = duckdb.connect(local_path, read_only=True)
    try:
        n = con.execute("SELECT count(*) FROM v_daily_qfq").fetchone()[0]
    finally:
        con.close()
    if not n or n <= 0:
        raise SystemExit(f"ERROR: 校验失败，v_daily_qfq 行数={n}")
    print(f"OK: 校验通过 {local_path}  v_daily_qfq 行数={n:,}")
    return n


# ---------------------------------------------------------------- 上传 / 下载 / 清理

def _list_dated(s3, cfg):
    """返回 [(date_str, key), ...]，按日期升序，仅含带日期的历史快照（不含 latest）。"""
    out = []
    token = None
    base = _key(cfg, "market_")
    while True:
        kw = {"Bucket": cfg["bucket"], "Prefix": base}
        if token:
            kw["ContinuationToken"] = token
        resp = s3.list_objects_v2(**kw)
        for obj in resp.get("Contents", []):
            m = DATED_RE.search(obj["Key"])
            if m:
                out.append((m.group(1), obj["Key"]))
        if resp.get("IsTruncated"):
            token = resp.get("NextContinuationToken")
        else:
            break
    out.sort(key=lambda t: t[0])
    return out


def upload(local_path):
    cfg = _cfg()
    if not os.path.isfile(local_path):
        raise SystemExit(f"ERROR: 本地 DB 不存在: {local_path}")
    local_size = os.path.getsize(local_path)
    s3 = _client(cfg)

    today = datetime.date.today().isoformat()
    dated_key = _key(cfg, f"market_{today}.duckdb")
    latest_key = _key(cfg, LATEST_NAME)

    print(f">>> 上传 {local_path} ({local_size:,} bytes) → s3://{cfg['bucket']}/{dated_key}")
    s3.upload_file(local_path, cfg["bucket"], dated_key)  # 自动分片 + 重试

    # 大小回读校验：确认上传对象与本地一致，避免半截文件冒充成功
    remote_size = s3.head_object(Bucket=cfg["bucket"], Key=dated_key)["ContentLength"]
    if remote_size != local_size:
        raise SystemExit(f"ERROR: 上传大小不一致 本地={local_size} 远端={remote_size}")
    print(f"    大小回读一致：{remote_size:,} bytes")

    # 服务端 copy 刷新 latest 指针（不再重传 683MB）
    s3.copy_object(Bucket=cfg["bucket"],
                   CopySource={"Bucket": cfg["bucket"], "Key": dated_key},
                   Key=latest_key)
    print(f"    latest 指针已更新 → {latest_key}")

    # 保留最近 keep 份带日期快照，删更旧的
    dated = _list_dated(s3, cfg)
    to_delete = dated[:-cfg["keep"]] if len(dated) > cfg["keep"] else []
    for d, key in to_delete:
        s3.delete_object(Bucket=cfg["bucket"], Key=key)
        print(f"    清理旧快照：{key} ({d})")
    kept = [d for d, _ in dated[-cfg["keep"]:]]
    print(f">>> 完成。当前保留 {len(kept)} 份：{', '.join(kept)}")


def download(local_path):
    cfg = _cfg()
    s3 = _client(cfg)
    latest_key = _key(cfg, LATEST_NAME)
    os.makedirs(os.path.dirname(os.path.abspath(local_path)), exist_ok=True)
    print(f">>> 下载 s3://{cfg['bucket']}/{latest_key} → {local_path}")
    s3.download_file(cfg["bucket"], latest_key, local_path)
    size = os.path.getsize(local_path)
    print(f"    完成：{size:,} bytes")


def list_snapshots():
    cfg = _cfg()
    s3 = _client(cfg)
    dated = _list_dated(s3, cfg)
    latest_key = _key(cfg, LATEST_NAME)
    try:
        h = s3.head_object(Bucket=cfg["bucket"], Key=latest_key)
        latest = f"{h['ContentLength']:,} bytes  (LastModified {h['LastModified']})"
    except Exception:
        latest = "（不存在）"
    print(f"bucket = {cfg['bucket']}  prefix = {cfg['prefix']}")
    print(f"latest = {latest}")
    print(f"历史快照 {len(dated)} 份：")
    for d, key in dated:
        print(f"  {d}  {key}")


def selftest():
    """小文件 put/get/delete 往返，验证凭据/endpoint/桶名，不触碰大 DB。"""
    cfg = _cfg()
    s3 = _client(cfg)
    key = _key(cfg, "_selftest_r2_sync.txt")
    payload = b"mis r2_sync selftest\n"
    print(f">>> selftest bucket=s3://{cfg['bucket']}/{key}")
    s3.put_object(Bucket=cfg["bucket"], Key=key, Body=payload)
    got = s3.get_object(Bucket=cfg["bucket"], Key=key)["Body"].read()
    assert got == payload, "get 内容与 put 不一致"
    s3.delete_object(Bucket=cfg["bucket"], Key=key)
    print("OK: put/get/delete 均通过，R2 连通正常。")


# ---------------------------------------------------------------- CLI

def main(argv):
    if not argv:
        print(__doc__)
        return 1
    cmd = argv[0]
    if cmd == "selftest":
        selftest()
    elif cmd == "list":
        list_snapshots()
    elif cmd in ("upload", "download", "validate"):
        if len(argv) < 2:
            raise SystemExit(f"ERROR: {cmd} 需要 <local_db_path>")
        {"upload": upload, "download": download, "validate": validate_db}[cmd](argv[1])
    else:
        raise SystemExit(f"ERROR: 未知命令 {cmd}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
