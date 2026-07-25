#!/usr/bin/env python3
"""
r2_sync.py —— MIS 晚间重链上云的 R2 持久层通用工具（S1 建立，S3 扩展）。

作用：把本地那份大 DuckDB（market.duckdb）与对象存储之间做「下载 / 校验 / 上传」，
让 GitHub Actions 这类无状态云端每次「下载 DB → 跑链 → 传回 DB」，无需常驻服务器。
S3 起额外承载晚间链的「今日已成功」标记与当日台账（复刻 Mac watchdog 的角色）。

设计要点（对应总图 3.2 灾备强制要求）：
  1. 用通用 S3 客户端（boto3 + 自定义 endpoint_url），**不绑死 Cloudflare 专有 SDK**。
     换 Backblaze B2 / AWS S3 / Wasabi 只需改 R2_ENDPOINT + 两个密钥，代码一行不用动。
  2. R2 内保留最近 N 份带日期的历史 DB（默认 8，仿本地 iCloud 8 份策略），
     另维护一个 market_latest.duckdb 指针指向当前最新，云端下载只认 latest。
  3. 快照命名取自**数据自身的 trade_date**，不用墙上时钟（见 upload() 注释）。

凭据来源（值本身绝不写死在代码里）：
  - 云端 GitHub Actions：作为 env 注入（secrets）。
  - 本地：env 未设置时，从 ~/.env 读取 R2_ACCESS_KEY_ID / R2_SECRET_ACCESS_KEY / R2_ENDPOINT。
  可选 R2_BUCKET（默认 "mis-runtime"）、R2_PREFIX（默认 "db"）、R2_KEEP（默认 8）。

CLI：
  python r2_sync.py selftest                      # 小文件 put/get/delete，验证连通，不碰大 DB
  python r2_sync.py upload   <db> [trade_date]    # 上传为 db/market_<trade_date>.duckdb + 刷新 latest + 清理旧份
  python r2_sync.py download <db>                 # 下载 db/market_latest.duckdb 到本地路径
  python r2_sync.py validate <db> [--min-trade-date <YYYY-MM-DD>]
  python r2_sync.py trade-date <db>               # 打印 DB 的数据日（max(date) FROM v_daily_qfq）
  python r2_sync.py list                          # 列出 R2 内现有 DB 快照
  python r2_sync.py state-get <name>              # 读 db/state/<name>（不存在打印 null）
  python r2_sync.py state-put <name> <json_file>  # 写 db/state/<name>
  python r2_sync.py state-del <name>              # 删 db/state/<name>（人工强制重跑的逃生口）
  python r2_sync.py prune    <market_YYYY-MM-DD.duckdb>   # 删掉一份历史快照（一次性清理用）
"""

import json
import os
import re
import sys

DEFAULT_BUCKET = "mis-runtime"
DEFAULT_PREFIX = "db"
DEFAULT_KEEP = 8
LATEST_NAME = "market_latest.duckdb"
DATED_RE = re.compile(r"market_(\d{4}-\d{2}-\d{2})\.duckdb$")
STATE_PREFIX = "state"


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
        # R2 用 "auto"；换到 AWS S3 / Wasabi 等后端时 SigV4 的 credential scope 需要真实
        # region，写死 "auto" 会鉴权失败——灾备「只改 endpoint+密钥」的承诺要靠这个可覆盖。
        "region": os.environ.get("R2_REGION", "auto"),
    }


def _client(cfg):
    import boto3
    from botocore.config import Config
    return boto3.client(
        "s3",
        endpoint_url=cfg["endpoint"],
        aws_access_key_id=cfg["access_key"],
        aws_secret_access_key=cfg["secret_key"],
        region_name=cfg["region"],
        config=Config(signature_version="s3v4",
                      retries={"max_attempts": 3, "mode": "standard"}),
    )


def _key(cfg, name):
    return f"{cfg['prefix']}/{name}" if cfg["prefix"] else name


# ---------------------------------------------------------------- 状态标记（S3）
# 晚间链的成功标记与当日台账放 db/state/ 下。_list_dated 的匹配前缀是 db/market_，且
# DATED_RE 要求 market_YYYY-MM-DD.duckdb 结尾，所以「保留最近 N 份」的裁剪逻辑永远不会
# 把 state/ 下的对象算进删除候选。

def _state_key(cfg, name):
    return _key(cfg, f"{STATE_PREFIX}/{name}")


def state_get(name):
    """读 db/state/<name>。对象不存在返回 None（不是异常）——首次运行、以及每个新交易日的
    第一次运行都走这条路径，不能让它变成 job 失败。"""
    from botocore.exceptions import ClientError
    cfg = _cfg()
    s3 = _client(cfg)
    try:
        body = s3.get_object(Bucket=cfg["bucket"], Key=_state_key(cfg, name))["Body"].read()
    except ClientError as e:
        if e.response.get("Error", {}).get("Code") in ("NoSuchKey", "NotFound", "404"):
            return None
        raise
    return json.loads(body.decode("utf-8"))


def state_put(name, obj):
    cfg = _cfg()
    key = _state_key(cfg, name)
    _client(cfg).put_object(
        Bucket=cfg["bucket"], Key=key,
        Body=json.dumps(obj, ensure_ascii=False, indent=2).encode("utf-8"),
        ContentType="application/json")
    print(f"OK: 已写入 s3://{cfg['bucket']}/{key}")
    return key


def state_del(name):
    """人工强制重跑的逃生口：删掉成功标记后，下一次触发会重跑整链。
    等价于 Mac 上 rm /Users/tx/market-data/.daily_update_success_marker。"""
    cfg = _cfg()
    _client(cfg).delete_object(Bucket=cfg["bucket"], Key=_state_key(cfg, name))
    print(f"OK: 已删除 state/{name}")


def latest_size():
    """latest 指针的字节数；**只有确实不存在**才返回 0，其他异常原样抛出。
    这个值是上传前「体积不得缩水」闸门的依据；早先版本用裸 except 吞掉一切异常，
    结果一次 HEAD 抖动或鉴权问题就把闸门静默变成 no-op（该 fail-closed 而非放行）。"""
    from botocore.exceptions import ClientError
    cfg = _cfg()
    try:
        return _client(cfg).head_object(Bucket=cfg["bucket"],
                                        Key=_key(cfg, LATEST_NAME))["ContentLength"]
    except ClientError as e:
        if e.response.get("Error", {}).get("Code") in ("NoSuchKey", "NotFound", "404"):
            return 0
        raise


def prune_key(name):
    """删掉一份带日期的历史快照（一次性清理 UTC/北京混淆留下的幽灵键用）。"""
    cfg = _cfg()
    if not DATED_RE.search(name):
        raise SystemExit(f"ERROR: prune 只接受 market_YYYY-MM-DD.duckdb 形式的键名，收到: {name}")
    _client(cfg).delete_object(Bucket=cfg["bucket"], Key=_key(cfg, name))
    print(f"OK: 已删除 {_key(cfg, name)}")


def db_trade_date(local_path):
    """DB 自身的数据日 = max(date) FROM v_daily_qfq —— 快照命名的唯一依据。
    墙上时钟在任何时区下都不等于数据日（周末、节假日、Fuyao 晚到跨到次日凌晨、STALE 夜的
    补跑，全都会错开）。"""
    import duckdb
    con = duckdb.connect(local_path, read_only=True)
    try:
        mx = con.execute("SELECT max(date) FROM v_daily_qfq").fetchone()[0]
    finally:
        con.close()
    if mx is None:
        raise SystemExit("ERROR: v_daily_qfq max(date) 为空，拒绝按 trade_date 命名快照")
    return mx.isoformat()


# ---------------------------------------------------------------- 校验

def validate_db(local_path, min_trade_date=None):
    """DB 完整性校验。S3 在 S1 的「v_daily_qfq 有行」之上追加：
      ① max(date) 非空；
      ② raw_kline_daily 有行（日K底表，auto-sync 的写入目标）；
      ③ strategy_parameters 有 is_active 行 —— screen_dragon_candidates.py 在 import 期
         （模块级读取活跃参数）就用它，缺了会在任何网络调用之前崩，S1 的 validate 查不出来；
      ④ min_trade_date：DB 的 max(date) 不得早于给定下界（上次成功标记的 trade_date）。
         这是「R2 标记与 DB 分裂」的检测点：若 latest 被回退，或有人还原了旧 DB 而标记仍
         宣称更新的日期，这里立刻 fail-closed，而不是把回退的 DB 当当日基线传上去。
    返回 (行数, trade_date)。
    """
    import duckdb
    if not os.path.isfile(local_path):
        raise SystemExit(f"ERROR: 本地 DB 不存在: {local_path}")
    con = duckdb.connect(local_path, read_only=True)
    try:
        n = con.execute("SELECT count(*) FROM v_daily_qfq").fetchone()[0]
        mx = con.execute("SELECT max(date) FROM v_daily_qfq").fetchone()[0]
        n_raw = con.execute("SELECT count(*) FROM raw_kline_daily").fetchone()[0]
        n_sp = con.execute(
            "SELECT count(*) FROM strategy_parameters WHERE is_active").fetchone()[0]
    finally:
        con.close()
    if not n or n <= 0:
        raise SystemExit(f"ERROR: 校验失败，v_daily_qfq 行数={n}")
    if mx is None:
        raise SystemExit("ERROR: 校验失败，v_daily_qfq max(date) 为空")
    if not n_raw or n_raw <= 0:
        raise SystemExit(f"ERROR: 校验失败，raw_kline_daily 行数={n_raw}")
    if not n_sp or n_sp <= 0:
        raise SystemExit("ERROR: 校验失败，strategy_parameters 无 is_active 行"
                         "（两条筛选脚本会在 import 期崩溃）")
    mx_s = mx.isoformat()
    # '-' / '' / None 一律视为无约束（首次运行时没有历史成功记录）
    if min_trade_date and min_trade_date not in ("-", ""):
        if mx_s < min_trade_date:
            raise SystemExit(
                f"ERROR: DB 数据日回退：max(date)={mx_s} < 下界 {min_trade_date}。"
                "R2 标记与 DB 不一致（latest 被回退 / 还原了旧 DB？），拒绝继续，以免把回退的"
                "DB 当当日基线上传。人工确认后可 state-del last_success.json。")
    print(f"OK: 校验通过 {local_path}  v_daily_qfq 行数={n:,} max(date)={mx_s}  "
          f"raw_kline_daily={n_raw:,}  active params={n_sp}")
    return n, mx_s


# ---------------------------------------------------------------- 上传 / 下载 / 清理

def _list_dated(s3, cfg):
    """返回 [(date_str, key), ...]，按日期升序，仅含带日期的历史快照（不含 latest / state）。"""
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


def upload(local_path, date_override=None):
    cfg = _cfg()
    if not os.path.isfile(local_path):
        raise SystemExit(f"ERROR: 本地 DB 不存在: {local_path}")
    local_size = os.path.getsize(local_path)
    s3 = _client(cfg)

    # 【S3 改动】快照名取自数据自身的 trade_date，不用 date.today()。
    # 实证：2026-07-24 那一晚同一份 715,665,408 字节的库，Mac(北京，当时已是 07-25 01:21)
    # 存成 market_2026-07-25、runner(UTC) 存成 market_2026-07-24，桶里出现两个名字指同一份
    # 数据；而按名字排序时「07-25」看起来更新，实际它是更旧的那次上传 —— 保留 N 份的裁剪
    # dated[:-keep] 依赖这个排序，长期会误判。改用 trade_date 后名字与内容永远一致。
    tag = date_override or db_trade_date(local_path)
    dated_key = _key(cfg, f"market_{tag}.duckdb")
    latest_key = _key(cfg, LATEST_NAME)

    print(f">>> 上传 {local_path} ({local_size:,} bytes) → s3://{cfg['bucket']}/{dated_key}")
    s3.upload_file(local_path, cfg["bucket"], dated_key)  # 自动分片 + 重试

    # 大小回读校验：确认上传对象与本地一致，避免半截文件冒充成功
    remote_size = s3.head_object(Bucket=cfg["bucket"], Key=dated_key)["ContentLength"]
    if remote_size != local_size:
        raise SystemExit(f"ERROR: 上传大小不一致 本地={local_size} 远端={remote_size}")
    print(f"    大小回读一致：{remote_size:,} bytes")

    # 服务端 copy 刷新 latest 指针（不再重传 700MB），并回读断言，避免坏指针
    s3.copy_object(Bucket=cfg["bucket"],
                   CopySource={"Bucket": cfg["bucket"], "Key": dated_key},
                   Key=latest_key)
    latest_bytes = s3.head_object(Bucket=cfg["bucket"], Key=latest_key)["ContentLength"]
    if latest_bytes != local_size:
        raise SystemExit(f"ERROR: latest 指针大小异常 期望={local_size} 实际={latest_bytes}")
    print(f"    latest 指针已更新并回读一致 → {latest_key}")

    # 【到此为止「已上云」这件事已经成立】保留策略只是运维动作，它失败不能反过来把一次
    # 已完成且校验过的上传判成失败——否则调用方会以为没传，下次重跑筛选（那是破坏性的）。
    try:
        dated = _list_dated(s3, cfg)
        to_delete = dated[:-cfg["keep"]] if len(dated) > cfg["keep"] else []
        for d, key in to_delete:
            s3.delete_object(Bucket=cfg["bucket"], Key=key)
            print(f"    清理旧快照：{key} ({d})")
        kept = [d for d, _ in dated[-cfg["keep"]:]]
        print(f">>> 完成。当前保留 {len(kept)} 份：{', '.join(kept)}")
    except Exception as e:                                    # noqa: BLE001
        print(f"WARN: 上传已成功，但旧快照清理失败（不影响本次上传）: {e}")


def download(local_path):
    """下载 latest 指针。latest 缺失时回退到最新的带日期快照——换供应商/新建桶后 latest
    还没建立时，这是唯一能自愈的路径（Mac 按设计A 不写 R2，没有回退就无法冷启动）。"""
    from botocore.exceptions import ClientError
    cfg = _cfg()
    s3 = _client(cfg)
    latest_key = _key(cfg, LATEST_NAME)
    os.makedirs(os.path.dirname(os.path.abspath(local_path)), exist_ok=True)
    print(f">>> 下载 s3://{cfg['bucket']}/{latest_key} → {local_path}")
    try:
        s3.download_file(cfg["bucket"], latest_key, local_path)
    except ClientError as e:
        if e.response.get("Error", {}).get("Code") not in ("NoSuchKey", "NotFound", "404"):
            raise
        dated = _list_dated(s3, cfg)
        if not dated:
            raise SystemExit(
                "ERROR: 桶内既无 market_latest.duckdb 也无任何 market_<date>.duckdb。"
                "这是空桶/新供应商的冷启动状态，需先从 Mac 播种一份："
                "python mis/Scripts/r2_sync.py upload /Users/tx/market-data/market.duckdb")
        d, key = dated[-1]
        print(f"    WARN: latest 缺失，回退到最新带日期快照 {key} ({d})")
        s3.download_file(cfg["bucket"], key, local_path)
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
    print(f"bucket = {cfg['bucket']}  prefix = {cfg['prefix']}  keep = {cfg['keep']}")
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

def _need(argv, n, cmd):
    if len(argv) < n:
        raise SystemExit(f"ERROR: {cmd} 参数不足")


def main(argv):
    if not argv:
        print(__doc__)
        return 1
    cmd = argv[0]
    if cmd == "selftest":
        selftest()
    elif cmd == "list":
        list_snapshots()
    elif cmd == "download":
        _need(argv, 2, cmd)
        download(argv[1])
    elif cmd == "validate":
        _need(argv, 2, cmd)
        # 兼容 workflow 里的写法：validate <db> --min-trade-date <YYYY-MM-DD>
        # flag 带了名字却没给值时**硬失败**：这道闸是「R2 标记与 DB 分裂」的唯一检测点，
        # 静默降级成无约束等于让它不存在（S3 对抗审查里被判 critical 的正是这种 fail-open）。
        bound = None
        if "--min-trade-date" in argv:
            i = argv.index("--min-trade-date")
            if i + 1 >= len(argv):
                raise SystemExit("ERROR: --min-trade-date 缺少取值")
            bound = argv[i + 1]
        elif len(argv) > 2:
            bound = argv[2]
        validate_db(argv[1], bound)
    elif cmd == "upload":
        _need(argv, 2, cmd)
        upload(argv[1], argv[2] if len(argv) > 2 else None)
    elif cmd == "trade-date":
        _need(argv, 2, cmd)
        print(db_trade_date(argv[1]))
    elif cmd == "state-get":
        _need(argv, 2, cmd)
        print(json.dumps(state_get(argv[1]), ensure_ascii=False, indent=2))
    elif cmd == "state-put":
        _need(argv, 3, cmd)
        with open(argv[2], encoding="utf-8") as fh:
            state_put(argv[1], json.load(fh))
    elif cmd == "state-del":
        _need(argv, 2, cmd)
        state_del(argv[1])
    elif cmd == "prune":
        _need(argv, 2, cmd)
        prune_key(argv[1])
    else:
        raise SystemExit(f"ERROR: 未知命令 {cmd}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
