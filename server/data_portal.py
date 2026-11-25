"""数据门户后端：只提供 eltdx 能拿到的数据与本地缓存状态。

设计边界（用户约定）：
- 股票列表、K 线、实时行情全部来自 eltdx（本地缓存是 eltdx 下载的）。
- 自选股列表是「本地偏好」，eltdx 不存储，所以用本地 JSON 保存代码；
  但自选股的行情仍然实时走 eltdx.get_quote()。
- 板块/概念本地 CSV 全空、eltdx 的 F10 接口慢且不稳定，暂不展示。
- 更新进度：eltdx 没有进度回调，这里解析 eltdx_updater.py 的 stdout 转发给网页。
"""

import csv
import json
import os
import subprocess
import sys
import threading
import time
from datetime import date

DATA_DIR = os.path.expanduser("~/.klang")
STOCK_LIST = os.path.join(DATA_DIR, "klang_stock_list.csv")
WATCHLIST = os.path.join(DATA_DIR, "watchlist.json")
UPDATE_RECORD = os.path.join(DATA_DIR, "update_record.json")
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
UPDATER = os.path.join(REPO_ROOT, "tools", "eltdx_updater.py")
PERIOD_DIRS = {"day": "day", "week": "week", "month": "month"}

# 更新任务状态：同一时刻只允许一个更新在跑
_update_lock = threading.Lock()
_update_state = {"running": False, "phase": "", "done": 0, "total": 0,
                 "ok": 0, "message": "", "started": 0, "finished": 0}


# ---------------------------------------------------------------------------
# 本地数据状态
# ---------------------------------------------------------------------------
def _file_count(folder):
    if not os.path.isdir(folder):
        return 0
    return sum(1 for f in os.listdir(folder) if f.endswith(".json"))


def _last_date(folder):
    """抽样读几只股票 K 线首行的日期，取出现最多的日期作为最后数据日期。"""
    if not os.path.isdir(folder):
        return None
    names = [f for f in os.listdir(folder) if f.endswith(".json")]
    if not names:
        return None
    counter = {}
    step = max(1, len(names) // 20)
    for name in names[::step][:20]:
        try:
            with open(os.path.join(folder, name), encoding="utf-8") as f:
                obj = json.load(f)
            rows = obj[2] if isinstance(obj, list) and len(obj) >= 3 else []
            if rows and isinstance(rows[0], dict) and rows[0].get("date"):
                d = rows[0]["date"][:10]
                counter[d] = counter.get(d, 0) + 1
        except Exception:
            continue
    return max(counter, key=counter.get) if counter else None


def _fallback_status():
    """更新记录尚未生成时的临时状态（只读扫描，不写记录文件）。"""
    result = {
        "stock_count": 0, "list_updated": None,
        "day_count": 0, "week_count": 0, "month_count": 0,
        "last_date": None, "lag_days": None,
        "source": "eltdx（通达信）",
    }
    if os.path.exists(STOCK_LIST):
        result["list_updated"] = time.strftime(
            "%Y-%m-%d %H:%M", time.localtime(os.path.getmtime(STOCK_LIST)))
        try:
            with open(STOCK_LIST, encoding="utf-8") as f:
                rows = list(csv.reader(f))
            result["stock_count"] = sum(1 for r in rows[1:] if r and r[0].strip())
        except Exception:
            pass
    for period, folder in PERIOD_DIRS.items():
        path = os.path.join(DATA_DIR, folder)
        result[period + "_count"] = _file_count(path)
        if period == "day":
            result["last_date"] = _last_date(path)
    if result["last_date"]:
        try:
            result["lag_days"] = (date.today() - date.fromisoformat(result["last_date"])).days
        except Exception:
            pass
    return result


def status():
    """网页显示的数据总览 = eltdx_updater.py 写入的 update_record.json。

    记录文件由更新程序独占写入，网页只读；文件尚未生成时用只读扫描兜底，
    并标记 record_exists=False 让页面提示。
    """
    keys = ("stock_count", "list_updated", "day_count", "week_count",
            "month_count", "last_date", "lag_days", "source", "updated_at",
            "periods", "current", "history")
    result = {k: ([] if k == "history" else None) for k in keys}
    result.update({"stock_count": 0, "day_count": 0, "week_count": 0,
                   "month_count": 0, "source": "eltdx（通达信）",
                   "periods": {}, "record_exists": False})
    if not os.path.exists(UPDATE_RECORD):
        result.update(_fallback_status())
        return result
    try:
        with open(UPDATE_RECORD, encoding="utf-8") as f:
            rec = json.load(f)
        if isinstance(rec, dict):
            for k in keys:
                if k in rec:
                    result[k] = rec[k]
            result["record_exists"] = True
    except Exception:
        result.update(_fallback_status())
    return result


# ---------------------------------------------------------------------------
# 股票列表（本地 CSV，数据来自 eltdx）
# ---------------------------------------------------------------------------
def _read_stocks():
    if not os.path.exists(STOCK_LIST):
        return []
    rows = []
    with open(STOCK_LIST, encoding="utf-8") as f:
        for row in list(csv.reader(f))[1:]:
            if not row or not row[0].strip():
                continue
            rows.append({
                "code": row[0].strip(),
                "name": row[1].strip() if len(row) > 1 else "",
            })
    return rows


def stocks(keyword="", offset=0, limit=50, only_kline=False):
    rows = _read_stocks()
    kw = (keyword or "").strip().lower()
    if kw:
        rows = [r for r in rows if kw in r["code"].lower() or kw in r["name"].lower()]
    if only_kline:
        rows = [r for r in rows if has_kline(r["code"])]
    total = len(rows)
    page = rows[offset:offset + limit]
    for r in page:
        r["has_kline"] = has_kline(r["code"])
    return {"total": total, "rows": page, "offset": offset, "limit": limit}


def has_kline(code):
    """该股票是否有本地日线文件。"""
    name = code.replace(".", "")
    path = os.path.join(DATA_DIR, "day", code + "day.json")
    return os.path.exists(path)


# ---------------------------------------------------------------------------
# 自选股：本地存代码，行情走 eltdx
# ---------------------------------------------------------------------------
def _load_watchlist():
    if not os.path.exists(WATCHLIST):
        return []
    try:
        with open(WATCHLIST, encoding="utf-8") as f:
            data = json.load(f)
        return list(data.get("codes", [])) if isinstance(data, dict) else []
    except Exception:
        return []


def _save_watchlist(codes):
    tmp = WATCHLIST + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"codes": codes}, f, ensure_ascii=False, indent=2)
    os.replace(tmp, WATCHLIST)


def watchlist():
    codes = _load_watchlist()
    names = {r["code"]: r["name"] for r in _read_stocks()}
    return [{"code": c, "name": names.get(c, "")} for c in codes]


def watch_add(code):
    code = (code or "").strip()
    if not code or ("." not in code) or len(code.split(".")[0]) != 2:
        raise ValueError("代码格式应为 sh.600000 或 sz.000001")
    codes = _load_watchlist()
    if code not in codes:
        codes.append(code)
        _save_watchlist(codes)
    return watchlist()


def watch_remove(code):
    codes = [c for c in _load_watchlist() if c != code]
    _save_watchlist(codes)
    return watchlist()


def _eltdx_code(code):
    """sh.600000 -> sh600000（eltdx 行情接口格式）。"""
    return code.replace(".", "")


def quotes(codes):
    """用 eltdx 取实时行情。codes 为 sh.600000 形式，返回列表。"""
    from eltdx import TdxClient
    if not codes:
        return []
    clean = [c for c in dict.fromkeys(codes) if "." in c]
    if not clean:
        return []
    client = TdxClient.from_hosts(probe_hosts=True, probe_timeout=1.5)
    try:
        snapshots = client.get_quote([_eltdx_code(c) for c in clean])
    finally:
        client.close()
    result = []
    for s in snapshots:
        full = "%s.%s" % (s.exchange, s.code)
        price = getattr(s, "last_price", 0) or 0
        pre = getattr(s, "pre_close_price", 0) or 0
        change_pct = round((price - pre) / pre * 100, 2) if pre else 0
        result.append({
            "code": full, "price": round(price, 3), "pre_close": round(pre, 3),
            "open": round(getattr(s, "open_price", 0) or 0, 3),
            "high": round(getattr(s, "high_price", 0) or 0, 3),
            "low": round(getattr(s, "low_price", 0) or 0, 3),
            "change_pct": change_pct,
            "amount": round(getattr(s, "amount", 0) or 0, 2),
        })
    return result


# ---------------------------------------------------------------------------
# 更新任务：复用 eltdx_updater.py，解析 stdout 发进度
# ---------------------------------------------------------------------------
def update_state():
    with _update_lock:
        return dict(_update_state)


def start_update(kind="day", emit=None):
    """kind: day=增量日K / all=日周月全量 / list=重拉股票列表。"""
    with _update_lock:
        if _update_state["running"]:
            return False
        _update_state.update(running=True, phase="准备中", done=0, total=0,
                             ok=0, message="", started=time.time(), finished=0)

    cmd = [sys.executable, UPDATER]
    if kind == "all":
        cmd.append("--all")
    if kind == "list":
        cmd.append("--list")

    def worker():
        state = _update_state
        try:
            proc = subprocess.Popen(cmd, cwd=REPO_ROOT, stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT, text=True,
                                    encoding="utf-8", errors="replace", bufsize=1)
            for line in proc.stdout:
                line = line.rstrip()
                if not line:
                    continue
                with _update_lock:
                    if "[1/2]" in line or "拉取股票列表" in line:
                        state["phase"] = "更新股票列表"
                    elif "[2/2]" in line:
                        state["phase"] = "更新日K" if kind != "all" else "更新日/周/月K"
                    if "已处理" in line and "/" in line:
                        # 形如：已处理 100/5302，耗时 12.3s
                        try:
                            frag = line.split("已处理", 1)[1].split("/", 1)
                            state["done"] = int(frag[0].strip())
                            state["total"] = int(frag[1].split("，")[0].split(",")[0].strip())
                        except Exception:
                            pass
                    state["message"] = line
                if emit:
                    emit("portal_update_progress", update_state())
            proc.wait()
            with _update_lock:
                state["phase"] = "完成" if proc.returncode == 0 else "失败"
                state["done"] = state["total"] or state["done"]
                state["message"] = ("更新完成" if proc.returncode == 0
                                    else "更新进程退出码 %d" % proc.returncode)
                state["finished"] = time.time()
                state["running"] = False
            if emit:
                emit("portal_update_done", update_state())
        except Exception as exc:
            with _update_lock:
                state["phase"] = "失败"
                state["message"] = str(exc)
                state["running"] = False
                state["finished"] = time.time()
            if emit:
                emit("portal_update_done", update_state())

    threading.Thread(target=worker, daemon=True, name="klang-data-update").start()
    return True
