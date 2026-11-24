#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""用 Klang 扫描 A 股涨停 / 跌停股票。

用法：
    python3 tools/limit_up.py                # 今日涨停
    python3 tools/limit_up.py --down         # 今日跌停
    python3 tools/limit_up.py --broken       # 炸板（盘中触及涨停但未封住）
    python3 tools/limit_up.py --date 2026-11-24
    python3 tools/limit_up.py --limit 200    # 只扫前 200 只（调试用）

数据来自本地缓存 ~/.klang/，需要先运行 tools/eltdx_updater.py 更新。
"""
import os
import sys
import argparse
from pathlib import Path

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))

from Klang import Klang

Klang.Klang_init()
Kl = Klang.Kl


def limit_pct(code, name):
    """该股可能的涨跌停幅度（%），返回候选列表。

    主板（sh.60 / sz.00）10%；创业板（sz.30）、科创板（sh.68）20%；
    主板 ST/*ST 5%，但退市整理期股票是 10%（名字里通常仍带 ST），
    所以 ST 股同时接受 5% 和 10% 两档，按实际收盘价匹配。
    """
    if code.startswith("sz.30") or code.startswith("sh.68"):
        return [20.0]
    if "ST" in name.upper().replace(" ", ""):
        return [5.0, 10.0]
    return [10.0]


def match_limit(close, high, prev_close, limits):
    """收盘价是否落在某个涨停价上（且当天最高价等于该价，即封住板）。"""
    for lim in limits:
        price = round(prev_close * (1 + lim / 100), 2)
        if abs(close - price) < 0.005 and abs(high - price) < 0.005:
            return lim
    return None


def scan(target_date=None):
    """扫描全市场，返回 (涨停, 跌停, 炸板) 三个列表。"""
    up, down, broken = [], [], []
    total = len(Kl.stocklist)
    for i, s in enumerate(Kl.stocklist, 1):
        code, name = s["code"], s["name"]
        try:
            Kl.code(code)
            df = Kl.day_df
            if df is None or len(df) < 2:
                continue
            if target_date:
                if str(target_date) not in df.index:
                    continue
                row = df.loc[str(target_date)]
                pos = df.index.get_loc(str(target_date))
                if pos == 0:
                    continue
                prev_close = df["close"].iloc[pos - 1]
            else:
                row = df.iloc[-1]
                prev_close = df["close"].iloc[-2]

            close = float(row["close"])
            high = float(row["high"])
            low = float(row["low"])
            if prev_close <= 0:
                continue

            lp = limit_pct(code, name)
            pct = (close - prev_close) / prev_close * 100

            hit = match_limit(close, high, prev_close, lp)
            if hit is not None:
                item = {
                    "code": code, "name": name, "pct": pct, "close": close,
                    "prev": prev_close, "amount": float(row.get("amount", 0) or 0),
                    "turn": float(row.get("turn", 0) or 0), "limit": hit,
                }
                up.append(item)
                continue

            # 跌停
            hit_dn = match_limit(close, low, prev_close, lp)
            if hit_dn is not None:
                down.append({
                    "code": code, "name": name, "pct": pct, "close": close,
                    "prev": prev_close, "amount": float(row.get("amount", 0) or 0),
                    "turn": float(row.get("turn", 0) or 0), "limit": hit_dn,
                })
                continue

            # 炸板：盘中触及涨停但收盘没封住
            for lim in lp:
                up_price = round(prev_close * (1 + lim / 100), 2)
                if abs(high - up_price) < 0.005 and close < up_price - 0.005:
                    broken.append({
                        "code": code, "name": name, "pct": pct, "close": close,
                        "prev": prev_close, "amount": float(row.get("amount", 0) or 0),
                        "turn": float(row.get("turn", 0) or 0), "limit": lim,
                    })
                    break
        except Exception:
            continue
    return up, down, broken


def show(title, items):
    print("\n%s（%d 只）" % (title, len(items)))
    print("-" * 92)
    print("%-10s %-10s %8s %8s %8s %10s %8s %6s" % (
        "代码", "名称", "涨幅%", "收盘", "昨收", "成交额(亿)", "换手%", "限制"))
    print("-" * 92)
    for it in sorted(items, key=lambda x: -x["pct"]):
        print("%-10s %-10s %8.2f %8.2f %8.2f %10.2f %8.2f %6s" % (
            it["code"], it["name"][:8], it["pct"], it["close"], it["prev"],
            it["amount"] / 1e8, it["turn"],
            ("%g%%" % it["limit"]) if it.get("limit") else "-"))
    if not items:
        print("（无）")
    print()


def main():
    ap = argparse.ArgumentParser(description="扫描 A 股涨停/跌停")
    ap.add_argument("--down", action="store_true", help="看跌停")
    ap.add_argument("--broken", action="store_true", help="看炸板")
    ap.add_argument("--date", help="指定交易日，如 2026-11-24")
    ap.add_argument("--limit", type=int, help="只扫前 N 只")
    args = ap.parse_args()

    if args.limit:
        Kl.stocklist = Kl.stocklist[:args.limit]

    if not Kl.stocklist:
        print("[Klang] 本地没有股票列表，请先运行：python3 tools/eltdx_updater.py")
        return

    up, down, broken = scan(args.date)

    print("=" * 78)
    print("Klang 涨停扫描 | 本地股票 %d 只 | 数据目录 %s" % (
        len(Kl.stocklist), os.path.expanduser("~/.klang")))
    print("=" * 78)

    if args.down:
        show("跌停", down)
    elif args.broken:
        show("炸板（触及涨停未封住）", broken)
    else:
        show("涨停", up)
        if args.broken:
            show("炸板（触及涨停未封住）", broken)


if __name__ == "__main__":
    main()
