#!/usr/bin/env python3
"""查找 N 个交易日内涨幅超过 X% 的股票（基于 Klang 本地缓存）。

用法：
    python3 tools/rise_scan.py                    # 10 个交易日涨幅 >= 30%
    python3 tools/rise_scan.py --days 5 --pct 20  # 5 日涨幅 >= 20%
    python3 tools/rise_scan.py --limit 200        # 只扫前 200 只（调试）
"""
import argparse
import os
import sys

# 强制使用本仓库源码，避免加载 site-packages 里的旧版 Klang（import 会联网）
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from Klang import Klang, C


def scan(days=10, pct=30.0, limit=0):
    Klang.Klang_init()
    Kl = Klang.Kl

    stocklist = Kl.stocklist
    if limit:
        stocklist = stocklist[:limit]

    results = []
    skipped = 0
    for s in stocklist:
        code, name = s['code'], s['name']
        try:
            Kl.code(code)
            cl = C.data
            if len(cl) < days + 1:
                skipped += 1          # 次新股/停牌太久，数据不足
                continue
            cur = float(cl.iloc[-1])
            base = float(cl.iloc[-(days + 1)])   # N 根 K 线前的收盘
            if not cur or not base or base <= 0:
                skipped += 1
                continue
            gain = (cur - base) / base * 100
            if gain >= pct:
                results.append({
                    'code': code,
                    'name': name,
                    'gain': gain,
                    'base': base,
                    'close': cur,
                    'start': str(cl.index[-(days + 1)])[:10],
                    'end': str(cl.index[-1])[:10],
                })
        except Exception:
            skipped += 1
            continue
    return results, skipped


def show(results, days, pct, skipped):
    print("\n%d 个交易日内涨幅 >= %.0f%%（截至最新交易日）" % (days, pct))
    print("=" * 96)
    print("%-11s %-10s %9s %9s %9s  %-11s %-11s" % (
        "代码", "名称", "涨幅%", "起价", "现价", "起始日", "结束日"))
    print("-" * 96)
    for r in sorted(results, key=lambda x: -x['gain']):
        print("%-11s %-10s %9.2f %9.2f %9.2f  %-11s %-11s" % (
            r['code'], r['name'][:8], r['gain'], r['base'], r['close'],
            r['start'], r['end']))
    print("-" * 96)
    print("命中 %d 只 | 数据不足跳过 %d 只" % (len(results), skipped))
    if results:
        print("数据区间: %s ~ %s" % (results[0]['start'], results[0]['end']))


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--days', type=int, default=10, help='交易日数，默认 10')
    ap.add_argument('--pct', type=float, default=30.0, help='涨幅阈值%%，默认 30')
    ap.add_argument('--limit', type=int, default=0, help='只扫前 N 只（调试）')
    a = ap.parse_args()
    res, skipped = scan(a.days, a.pct, a.limit)
    show(res, a.days, a.pct, skipped)
