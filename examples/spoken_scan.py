#!/usr/bin/env python3
"""把一句口语对上 Klang 公式或现成扫描脚本，然后找出股票。

用法：
    python3 examples/spoken_scan.py --list
    python3 examples/spoken_scan.py --match "今天哪些股票涨停"
    python3 examples/spoken_scan.py --show 均线多头
    python3 examples/spoken_scan.py --run "均线多头" --limit 200
    python3 examples/spoken_scan.py --run "MACD金叉"

口语对照表在 server/spoken_catalog.json，网页公式库读的是同一份。
涨停 / 跌停 / 炸板默认走 tools/limit_up.py（按涨停价封板），
加 --formula 才改用目录里的教学公式。
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = ROOT / "server" / "spoken_catalog.json"
sys.path.insert(0, str(ROOT))

from Klang.lang import Kexec, setPY  # noqa: E402
from Klang import (  # noqa: E402
    Kl, Klang, C, O, H, L, V,
    MA, MACD, CROSS, RSI, BOLL, KDJ, HHV, LLV, COUNT, NAMELIKE, CODELIKE,
)

Klang.Klang_init()


def getpyglobals(name):
    return globals().get(name)


def setpyglobals(name, val):
    globals()[name] = val


setPY(getpyglobals, setpyglobals)

hits = []


def DISPLAY(value):  # noqa: N802
    hits.append((Kl.cur_code, Kl.cur_name, value))


def load_catalog():
    with CATALOG_PATH.open(encoding="utf-8") as f:
        return json.load(f)


def norm(text):
    return "".join(str(text).lower().split())


def match_query(catalog, query):
    """取被问句包含、且说法最长的一条，避免「金叉」盖过「MACD金叉」。"""
    q = norm(query)
    best = None
    best_len = 0
    for item in catalog:
        names = [item.get("title", ""), item.get("id", "")] + list(item.get("utterances") or [])
        for name in names:
            nu = norm(name)
            if nu and (nu in q or q in nu) and len(nu) > best_len:
                best = item
                best_len = len(nu)
    return best


def find_item(catalog, key):
    key_n = norm(key)
    for item in catalog:
        if norm(item.get("id")) == key_n or norm(item.get("title")) == key_n:
            return item
    return match_query(catalog, key)


def run_formula(formula, limit):
    stocks = list(Kl.stocklist)
    if limit:
        stocks = stocks[:limit]
    errors = 0
    hits.clear()
    for stock in stocks:
        code = stock.get("code")
        try:
            Kl.code(code)
        except Exception:
            continue
        if Kl.day_df is None or len(Kl.day_df) == 0:
            continue
        try:
            Kexec(formula if formula.endswith("\n") else formula + "\n")
        except Exception as exc:
            errors += 1
            if errors <= 3:
                print(f"公式错误 {code}: {exc}", file=sys.stderr)
    return len(stocks), errors


def run_tool(argv, limit):
    cmd = list(argv)
    if cmd and cmd[0] == "python3":
        cmd[0] = sys.executable
    if limit:
        cmd.extend(["--limit", str(limit)])
    proc = subprocess.run(cmd, cwd=str(ROOT))
    return proc.returncode


def main():
    parser = argparse.ArgumentParser(description="口语选股：对上公式后扫描本地行情")
    parser.add_argument("--list", action="store_true", help="列出全部口语说法")
    parser.add_argument("--match", metavar="问句", help="只打印对上的条目，不扫描")
    parser.add_argument("--show", metavar="名称", help="打印某条的公式")
    parser.add_argument("--run", metavar="问句", help="对上问句并扫描")
    parser.add_argument("--formula", action="store_true",
                        help="涨停/跌停/炸板也改走目录里的公式，不调用 limit_up.py")
    parser.add_argument("--limit", type=int, default=0, help="只扫前 N 只")
    args = parser.parse_args()

    catalog = load_catalog()
    if args.list:
        for item in catalog:
            says = " / ".join(item.get("utterances") or [])
            how = "脚本" if item.get("tool") and not args.formula else "公式"
            print(f"{item['title']:<16} {how:<4} {says}")
        return 0

    key = args.match or args.show or args.run
    if not key:
        parser.print_help()
        return 2
    item = find_item(catalog, key)
    if item is None:
        print(f"没有对上的说法：{key}", file=sys.stderr)
        print("先看 python3 examples/spoken_scan.py --list", file=sys.stderr)
        return 2

    print(f"问句：{key}")
    print(f"对应：{item['title']}  ({item['id']})")
    print(item.get("blurb") or "")
    if args.match:
        if item.get("tool"):
            print("执行：", " ".join(item["tool"]))
        print(item.get("formula") or "")
        return 0
    if args.show:
        print(item.get("formula") or "")
        return 0

    if item.get("tool") and not args.formula:
        print("执行：", " ".join(item["tool"]))
        return run_tool(item["tool"], args.limit)

    formula = item.get("formula") or ""
    scanned, errors = run_formula(formula, args.limit)
    print(f"扫描：{scanned} 只　命中：{len(hits)} 只　公式错误：{errors}")
    for code, name, value in hits[:40]:
        print(f"  {code:<12} {name:<10} {value}")
    if len(hits) > 40:
        print(f"  ... 其余 {len(hits) - 40} 只略")
    return 0


if __name__ == "__main__":
    sys.exit(main())
