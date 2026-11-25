#
# 用 eltdx 下载 A 股数据到本地缓存（~/.klang/）
#
# 只做数据更新，不影响 Klang 库的 import（import 只读本地）。
# 用法：
#   python3 tools/eltdx_updater.py            # 增量更新（只补最近数据）
#   python3 tools/eltdx_updater.py --all      # 全量下载（每只股票约 200 根K线）
#   python3 tools/eltdx_updater.py --codes sh.600000 sz.000001   # 只更新指定股票
#
import os
import sys
import json
import time
import argparse
from datetime import date

try:
    from eltdx import TdxClient
except ImportError:
    print("[eltdx] 缺少依赖：pip install eltdx")
    raise

DATA_PATH = os.path.expanduser("~/.klang")
STOCK_LIST = os.path.join(DATA_PATH, "klang_stock_list.csv")
DEFAULT_BARS = 200          # 与现有本地缓存口径一致（每只股票 200 根）
PAGE = 200                  # eltdx 单页最大 800，用 200 便于控制
SLEEP = 0.02               # 每只股票之间的间隔，避免打太快

PERIODS = {"day": "day", "week": "week", "month": "month"}

# 更新记录：由本脚本独占写入，网页只读。放在 ~/.klang/ 下与数据同目录。
UPDATE_RECORD = os.path.join(DATA_PATH, "update_record.json")
KIND_LABELS = {"day": "更新日 K", "all": "日/周/月全量", "list": "重拉股票列表"}
MAX_HISTORY = 20


def _now():
    return time.strftime("%Y-%m-%d %H:%M:%S")


def _empty_record():
    return {
        "schema": 1,
        "source": "eltdx（通达信）",
        "updated_at": None,
        "stock_count": 0,
        "list_updated": None,
        "day_count": 0, "week_count": 0, "month_count": 0,
        "last_date": None, "lag_days": None,
        "periods": {},
        "current": None,
        "history": [],
    }


def load_record():
    """读取更新记录；文件不存在或损坏时返回空结构，不影响更新。"""
    if not os.path.exists(UPDATE_RECORD):
        return _empty_record()
    try:
        with open(UPDATE_RECORD, encoding="utf-8") as f:
            data = json.load(f)
        rec = _empty_record()
        if isinstance(data, dict):
            rec.update(data)
        return rec
    except Exception:
        return _empty_record()


def write_record(rec):
    """原子写入，避免网页读到半截 JSON。"""
    tmp = UPDATE_RECORD + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(rec, f, ensure_ascii=False, indent=2)
    os.replace(tmp, UPDATE_RECORD)


def _sample_last_date(folder):
    """抽样读各文件首行日期，取最大值作为该周期的最后数据日期。"""
    if not os.path.isdir(folder):
        return None
    names = [f for f in os.listdir(folder) if f.endswith(".json")]
    if not names:
        return None
    best = None
    step = max(1, len(names) // 20)
    for name in names[::step][:20]:
        try:
            with open(os.path.join(folder, name), encoding="utf-8") as f:
                obj = json.load(f)
            rows = obj[2] if isinstance(obj, list) and len(obj) >= 3 else []
            if rows and isinstance(rows[0], dict) and rows[0].get("date"):
                d = str(rows[0]["date"])[:10]
                if best is None or d > best:
                    best = d
        except Exception:
            continue
    return best


def scan_snapshot(rec):
    """扫描本地目录，刷新记录里的文件数、最后日期与滞后天数。"""
    for period, ext in PERIODS.items():
        folder = os.path.join(DATA_PATH, ext)
        files = 0
        if os.path.isdir(folder):
            files = sum(1 for f in os.listdir(folder) if f.endswith(".json"))
        rec["periods"].setdefault(period, {})
        rec["periods"][period].update(
            files=files, last_date=_sample_last_date(folder))
        rec[period + "_count"] = files
    rec["last_date"] = rec["periods"].get("day", {}).get("last_date")
    if rec["last_date"]:
        try:
            rec["lag_days"] = (date.today() - date.fromisoformat(rec["last_date"])).days
        except Exception:
            rec["lag_days"] = None
    return rec


def ensure_dirs():
    for sub in ("day", "week", "month"):
        os.makedirs(os.path.join(DATA_PATH, sub), exist_ok=True)


def connect():
    """自动探测可用服务器并连接。"""
    client = TdxClient.from_hosts(probe_hosts=True, probe_timeout=1.5)
    return client


def normalize_code(full_code):
    """sh600000 -> sh.600000；sz000001 -> sz.000001；北交所跳过。"""
    if not full_code or len(full_code) < 8:
        return None
    prefix, num = full_code[:2], full_code[2:]
    if prefix not in ("sh", "sz"):
        return None
    return prefix + "." + num


def fetch_stock_list(client):
    """拉取 A 股代码表，写入 klang_stock_list.csv（与现有格式一致）。"""
    codes = client.get_stock_codes_all()
    rows = []
    seen = set()
    for full in codes:
        code = normalize_code(full)
        if not code or code in seen:
            continue
        seen.add(code)
        # 名称从代码本身推不出，K线接口也不返回名称；
        # 保留已有本地名称，新股票先用代码占位（后续可从 F10 补）。
        rows.append((code, code, "50", "", ""))

    # 合并名称：eltdx 名称表 > 日K文件 > 旧 CSV
    names = {}
    for mkt, pre in ((0, "sz"), (1, "sh")):
        try:
            for sc in client.get_codes_all(mkt):
                if sc.name:
                    names.setdefault(pre + "." + sc.code, sc.name)
        except Exception:
            pass
    day_dir = os.path.join(DATA_PATH, "day")
    if os.path.isdir(day_dir):
        for fn in os.listdir(day_dir):
            if not fn.endswith(".json"):
                continue
            try:
                with open(os.path.join(day_dir, fn), encoding="utf-8") as f:
                    obj = json.load(f)
                if isinstance(obj, list) and len(obj) >= 2:
                    names.setdefault(obj[0], obj[1])
            except Exception:
                pass
    if os.path.exists(STOCK_LIST):
        with open(STOCK_LIST, encoding="utf-8") as f:
            for line in f.readlines()[1:]:
                parts = line.strip().split(",")
                if len(parts) >= 2:
                    names.setdefault(parts[0], parts[1])
    rows = [(c, names.get(c, c), s, t, g) for (c, _, s, t, g) in rows]

    # 按代码升序，保证顺序稳定（sh.600000 在最前，作为默认股票）
    rows.sort(key=lambda r: r[0])

    with open(STOCK_LIST, "w", encoding="utf-8") as f:
        f.write("code,name,SCR,tdxbk,tdxgn\n")
        for c, n, s, t, g in rows:
            f.write("%s,%s,%s,%s,%s\n" % (c, n, s, t, g))
    return rows


def bar_to_row(bar, volume_lots, turn, period="day"):
    """eltdx KlineBar -> 本地 dict 格式。

    注意 volume 单位：日K的 volume_lots 是「手」(×100=股)，
    周/月的 volume_lots 是「百手」(×10000=股)。用 amount/均价反推校验过。
    """
    factor = 100.0 if period == "day" else 10000.0
    return {
        "date": bar.time.date().isoformat(),
        "open": round(float(bar.open), 4),
        "close": round(float(bar.close), 4),
        "high": round(float(bar.high), 4),
        "low": round(float(bar.low), 4),
        "volume": float(volume_lots) * factor,
        "turn": round(float(turn), 4),
        "amount": round(float(bar.amount), 2),
    }


def fetch_bars(client, full_code, period, count=DEFAULT_BARS):
    """拉取单只股票某个周期的 K 线，返回本地格式的记录列表（最新在前）。"""
    series = client.get_kline(period, full_code[2:], start=0, count=count)
    bars = list(series.bars)
    if not bars:
        return []

    rows = []
    for b in bars:
        lots = float(getattr(b, "volume_lots", 0) or 0)
        turn = 0.0
        try:
            # get_turnover 只接受日K的手数口径，周/月按其单位换算后传入
            vol_for_turn = lots if period == "day" else lots * 100
            turn = client.get_turnover(full_code[2:], vol_for_turn, unit="hand")
        except Exception:
            pass
        rows.append(bar_to_row(b, lots, turn, period))
    # eltdx 返回按时间升序，本地文件是最新在前 -> 反转
    rows.reverse()
    return rows


def save_bars(code, name, period, rows):
    """写入 ~/.klang/<period>/<code><period>.json，保持 [code,name,rows] 结构。"""
    ext = PERIODS[period]
    path = os.path.join(DATA_PATH, ext, code + ext + ".json")
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump([code, name, rows], f, ensure_ascii=False)
    os.replace(tmp, path)


def existing_last_date(code, period):
    ext = PERIODS[period]
    path = os.path.join(DATA_PATH, ext, code + ext + ".json")
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            obj = json.load(f)
        rows = obj[2] if isinstance(obj, list) and len(obj) >= 3 else []
        return rows[0].get("date") if rows else None
    except Exception:
        return None


def update_one(client, code, name, periods, count, verbose=False):
    """更新一只股票，返回是否成功。"""
    full = code.replace(".", "")  # sh.600000 -> sh600000
    ok = True
    for period in periods:
        try:
            rows = fetch_bars(client, full, period, count)
            if rows:
                save_bars(code, name, period, rows)
            elif verbose:
                print("  %s %s 无数据" % (code, period))
        except Exception as e:
            ok = False
            if verbose:
                print("  %s %s 失败: %s" % (code, period, str(e)[:60]))
    return ok


def read_codes_from_csv():
    if not os.path.exists(STOCK_LIST):
        return []
    rows = []
    with open(STOCK_LIST, encoding="utf-8") as f:
        for line in f.readlines()[1:]:
            parts = line.strip().split(",")
            if len(parts) >= 2:
                rows.append((parts[0], parts[1]))
    return rows


def local_list_stat():
    """本地股票列表的数量与修改时间（未重拉列表时用于更新记录）。"""
    count, updated = 0, None
    if os.path.exists(STOCK_LIST):
        try:
            with open(STOCK_LIST, encoding="utf-8") as f:
                count = sum(1 for line in f.readlines()[1:] if line.strip())
            updated = time.strftime(
                "%Y-%m-%d %H:%M", time.localtime(os.path.getmtime(STOCK_LIST)))
        except Exception:
            pass
    return count, updated


def update_all(Kl=None, incremental=True, only_codes=None, do_list=False,
               count=DEFAULT_BARS, limit=None):
    """主入口：更新股票列表和数据。

    Kl 参数仅为兼容 Klang.Kl.downloadall/updateall 调用，可忽略。
    """
    ensure_dirs()
    kind = "day" if incremental else "all"
    if do_list:
        kind = "list"
    rec = load_record()
    task = {
        "kind": kind, "label": KIND_LABELS.get(kind, kind),
        "started": _now(), "finished": None, "result": "running",
        "total": 0, "done": 0, "ok": 0, "failed": 0, "message": "准备中",
    }
    rec["current"] = task
    rec["history"] = [dict(task)] + (rec.get("history") or [])[:MAX_HISTORY - 1]
    write_record(rec)

    client = connect()
    try:
        if do_list or not os.path.exists(STOCK_LIST):
            print("[1/2] 拉取股票列表...")
            fetched = fetch_stock_list(client)
            # fetch_stock_list 返回 (code,name,SCR,tdxbk,tdxgn)，统一裁成 (code,name)
            rows = [(r[0], r[1]) for r in fetched]
            print("    共 %d 只（沪 %d / 深 %d）" % (
                len(rows),
                sum(1 for r in rows if r[0].startswith("sh")),
                sum(1 for r in rows if r[0].startswith("sz")),
            ))
            rec["stock_count"] = len(rows)
            rec["list_updated"] = _now()
            write_record(rec)
        else:
            rows = read_codes_from_csv()
            print("[1/2] 使用本地股票列表：%d 只" % len(rows))
            rec["stock_count"], rec["list_updated"] = local_list_stat()
            write_record(rec)

        if only_codes:
            wanted = set(only_codes)
            rows = [(c, n) for c, n in rows if c in wanted]

        if limit:
            rows = rows[:limit]

        periods = ["day"] if incremental else ["day", "week", "month"]
        print("[2/2] 更新 %s（%s）..." % (
            len(rows), "增量日K" if incremental else "日/周/月全量"))
        task.update(total=len(rows), message="更新中")
        write_record(rec)

        ok_count = 0
        t0 = time.time()
        for i, (code, name) in enumerate(rows, 1):
            if update_one(client, code, name, periods, count, verbose=(limit is not None)):
                ok_count += 1
            if i % 100 == 0:
                msg = "已处理 %d/%d，耗时 %.1fs" % (i, len(rows), time.time() - t0)
                print("    " + msg)
                task.update(done=i, message=msg)
                write_record(rec)
            time.sleep(SLEEP)

        elapsed = time.time() - t0
        msg = "完成：%d/%d 成功，耗时 %.1fs" % (ok_count, len(rows), elapsed)
        print(msg)
        task.update(finished=_now(), done=len(rows), ok=ok_count,
                    failed=len(rows) - ok_count, message=msg,
                    result="success" if ok_count else "failed")
        rec["history"][0] = dict(task)
        rec["updated_at"] = _now()
        scan_snapshot(rec)
        write_record(rec)
        if Kl is not None:
            # 刷新内存中的股票列表
            from Klang.data_klang import init_stock_list
            Kl.stocklist = init_stock_list(Kl)
    except Exception as exc:
        task.update(finished=_now(), result="failed", message="异常：%s" % exc)
        rec["history"][0] = dict(task)
        rec["updated_at"] = _now()
        write_record(rec)
        raise
    finally:
        try:
            client.close()
        except Exception:
            pass


def main():
    ap = argparse.ArgumentParser(description="用 eltdx 更新 Klang 本地数据")
    ap.add_argument("--all", action="store_true", help="全量下载日/周/月K线")
    ap.add_argument("--list", action="store_true", help="强制重新下载股票列表")
    ap.add_argument("--codes", nargs="+", help="只更新指定代码，如 sh.600000 sz.000001")
    ap.add_argument("--count", type=int, default=DEFAULT_BARS, help="每只股票K线根数（默认200）")
    ap.add_argument("--limit", type=int, help="只处理前 N 只（调试用）")
    args = ap.parse_args()

    update_all(incremental=not args.all, only_codes=args.codes,
               do_list=args.list, count=args.count, limit=args.limit)


if __name__ == "__main__":
    main()
