#
# klang.org.cn 提供的股票数据（本地缓存版）
#
# 本模块现在**只负责本地数据的加载**，不联网、不更新。
# 数据下载/更新请用 tools/eltdx_updater.py（基于 eltdx）。
#
import os
import json
import shutil
import pandas as pd
from .common import end, get_date
from datetime import date, datetime, timedelta


def get_path(name):
    t = os.path.expanduser(name)
    return os.path.normpath(t)


data_path = get_path("~/.klang")
os.makedirs(data_path, exist_ok=True)
os.makedirs(get_path(data_path + "/day"), exist_ok=True)
os.makedirs(get_path(data_path + "/week"), exist_ok=True)
os.makedirs(get_path(data_path + "/month"), exist_ok=True)

filename_sl = get_path("~/.klang/klang_stock_list.csv")
file_updata_list = get_path("~/.klang/update_list.csv")


# ---------------------------------------------------------------------------
# 数据新鲜度提示
# ---------------------------------------------------------------------------
def last_local_date(freq="day", sample_limit=20):
    """扫描本地 K 线文件，返回出现最多的最后一个日期。

    只抽样 sample_limit 个文件，避免每次 import 扫描 5000+ 文件。
    返回 (last_date_str, file_count)；无数据时返回 (None, 0)。
    """
    ext = {"day": "day", "week": "week", "month": "month"}.get(freq, "day")
    folder = get_path(data_path + "/" + ext)
    if not os.path.isdir(folder):
        return None, 0

    files = [f for f in os.listdir(folder) if f.endswith(ext + ".json")]
    if not files:
        return None, 0

    counter = {}
    step = max(1, len(files) // sample_limit)
    sampled = files[::step][:sample_limit]
    for name in sampled:
        try:
            with open(os.path.join(folder, name), encoding="utf-8") as f:
                obj = json.load(f)
            rows = obj[2] if isinstance(obj, list) and len(obj) >= 3 else []
            if not rows:
                continue
            # 本地文件是倒序存放（最新在前），取第一条的 date
            d = rows[0].get("date") if isinstance(rows[0], dict) else None
            if d:
                counter[d] = counter.get(d, 0) + 1
        except Exception:
            continue

    if not counter:
        return None, len(files)
    # 取出现次数最多的日期作为代表
    last = max(counter, key=counter.get)
    return last, len(files)


def check_freshness(warn_days=7):
    """检查本地数据新鲜度，返回 (last_date, lag_days, file_count)。

    lag_days 为 None 表示无数据。import 时打印提示但不联网。
    """
    last, count = last_local_date("day")
    if not last:
        return None, None, count
    try:
        lag = (date.today() - date.fromisoformat(last[:10])).days
    except Exception:
        lag = None
    return last, lag, count


def print_data_status():
    """import 时调用：报告本地数据状态，必要时提示更新。"""
    global stocklist
    # 缺股票列表时给出下载指引
    if not os.path.exists(filename_sl):
        print("[Klang] 本地股票列表不存在：" + filename_sl)
        print("[Klang] import 不联网、不更新。请运行更新脚本下载数据：")
        print("[Klang]   cd <项目根目录> && python3 tools/eltdx_updater.py")
        return

    last, lag, count = check_freshness()
    if not last:
        print("[Klang] 本地有股票列表但没有日K数据，请运行：python3 tools/eltdx_updater.py")
        return
    if lag is not None and lag > 7:
        print("[Klang] 本地日K最后日期 %s，距今 %d 天，数据已过期。" % (last, lag))
        print("[Klang] 需要更新请运行：python3 tools/eltdx_updater.py")
    # lag <= 7 时静默，不打扰


# ---------------------------------------------------------------------------
# 股票列表（只读本地）
# ---------------------------------------------------------------------------
stocklist = []
stockindex = {}
stockupdate = {}


def get_scr(code):
    index = stockindex.get(code)
    if index is None or index >= len(stocklist):
        return "50"
    return stocklist[index].get("SCR", "50")


def get_chouma(code):
    return get_scr(code)


def init_stock_list(Kl, offset=0):
    """从本地 CSV 加载股票列表；缺失时提示，不联网下载。"""
    global stocklist, stockupdate

    if not os.path.exists(filename_sl):
        print_data_status()
        stocklist = []
        return stocklist

    stocklist = []
    print("正在从文件", filename_sl, "加载股票列表")
    with open(filename_sl, encoding="utf-8") as f:
        stocklines = f.readlines()
    stocklines = stocklines[1:]  # 删除表头

    index = 0
    for line in stocklines:
        line = line.strip()
        if not line:
            continue
        parts = line.split(",")
        if len(parts) < 2:
            continue
        code, name = parts[0], parts[1]
        scr = parts[2] if len(parts) > 2 else "50"
        tdxbk = parts[3] if len(parts) > 3 else ""
        tdxgn = parts[4] if len(parts) > 4 else ""
        stocklist.append({"code": code, "name": name, "df": None,
                          "SCR": scr, "tdxbk": tdxbk, "tdxgn": tdxgn})
        Kl.stockdict[code] = {"name": name, "SCR": scr, "tdxbk": tdxbk,
                              "tdxgn": tdxgn, "index": index}
        stockindex[code] = index
        index += 1

    # 更新记录（只用于提示，不触发下载）
    if os.path.exists(file_updata_list):
        try:
            with open(file_updata_list) as f:
                stockupdate = json.load(f)
        except Exception:
            pass

    print_data_status()
    return stocklist


# ---------------------------------------------------------------------------
# K 线数据（只读本地）
# ---------------------------------------------------------------------------
def json_to_df(json_data, setindex=False):
    df = pd.json_normalize(json_data)
    if len(df) < 1:
        return []

    df = df[df["volume"] > 0.0]
    if len(df) < 1:
        return []

    datas = df.sort_values(by="date", ascending=True)
    if setindex is True:
        datas["datetime"] = datas["date"]
        datas = datas.set_index("date")
    close = datas["close"].iloc[-1]
    volume = datas["volume"].iloc[-1]
    turn = datas["turn"].iloc[-1]
    try:
        datas["hqltsz"] = float(volume) * float(close) / float(turn) / 1000000
    except Exception:
        datas["hqltsz"] = 0.0001
    datas.rename(columns={"volume": "vol"}, inplace=True)
    return datas


class GetData:
    """只从本地缓存读取 K 线，不联网。"""

    def __init__(self, freq="d"):
        self.freq = self._name(freq)

    def _name(self, _name):
        name_table = {"day": "d", "d": "d", "week": "w", "w": "w",
                      "month": "m", "m": "m"}
        self.freq = name_table.get(_name, "d")
        return self.freq

    # 无数据股票（新股在列表里但没有本地 K 线文件）返回结构完整的空表，
    # 保证 MA(C,N) 等公式能算出空序列、[-1] 取不到值而静默跳过，不抛 KeyError。
    EMPTY_COLUMNS = ["open", "close", "high", "low", "vol", "turn",
                     "amount", "hqltsz", "datetime"]

    @classmethod
    def _empty_df(cls):
        return pd.DataFrame(columns=cls.EMPTY_COLUMNS)

    def _read_file_data(self, code):
        ext_table = {"d": "day", "w": "week", "m": "month"}
        ext = ext_table.get(self.freq, "day")
        path = get_path("~/.klang/" + ext + "/" + code + ext + ".json")
        if not os.path.exists(path):
            return self._empty_df()

        try:
            with open(path, encoding="utf-8") as f:
                obj = json.load(f)
            rows = obj[2] if isinstance(obj, list) and len(obj) >= 3 else []
            df = json_to_df(rows)
            if not isinstance(df, pd.DataFrame) or len(df) < 1:
                return self._empty_df()
            df["datetime"] = df["date"]
            df = df.set_index("date")
            return df
        except Exception:
            return self._empty_df()

    def get_data(self, Kl, code, start, end):
        # 纯本地：文件不存在或损坏时返回空 DataFrame，不联网补数据
        return self._read_file_data(code)


day_data = GetData(freq="d")
week_data = GetData(freq="w")
month_data = GetData(freq="m")
