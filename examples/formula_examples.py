#!/usr/bin/env python3
"""可直接运行的中文公式样例，也是给 agent 看的可执行规范。

用法：
    python3 examples/formula_examples.py --list
    python3 examples/formula_examples.py --example 均线多头 --limit 200
    python3 examples/formula_examples.py --show 涨停
    python3 examples/formula_examples.py --example 涨停          # 全市场
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))  # 必须用本仓库源码，别让 site-packages 里的旧 egg 抢先

from Klang.lang import Kexec, setPY                                   # noqa: E402
from Klang import Kl, Klang, C, O, H, L, V, MA, MACD, CROSS           # noqa: E402

Klang.Klang_init()
code = Kl.code  # 公式里的 code('sh.600000') 需要这个 Python 全局函数

EXAMPLES = {
    "涨停": """涨停线 = 9.8
今日收盘 = C
昨日收盘 = C[1]
涨幅 = (今日收盘 - 昨日收盘) / 昨日收盘 * 100
if 涨幅[-1] > 涨停线:
    DISPLAY(涨幅[-1])""",
    "均线多头": """ma5 = MA(C, 5)
ma10 = MA(C, 10)
ma20 = MA(C, 20)
if ma5[-1] > ma10[-1] and ma10[-1] > ma20[-1]:
    DISPLAY(ma5[-1])""",
    "放量突破": """ma20 = MA(C, 20)
vol5 = MA(V, 5)
vol60 = MA(V, 60)
if C[-1] > ma20[-1] and vol5[-1] > vol60[-1] * 1.5:
    DISPLAY(C[-1])""",
    "MACD金叉": """dif, dea, macd = MACD(C)
if dif[-1] > dea[-1] and dif[-2] <= dea[-2]:
    DISPLAY(dif[-1])""",
    "单票调试": """code('sh.600000');
ma20 = MA(C, 20);
if C[-1] > ma20[-1]:
    DISPLAY(C[-1]);""",
}

hits = []


def getpyglobals(name):
    return globals().get(name)


def setpyglobals(name, val):
    globals()[name] = val


setPY(getpyglobals, setpyglobals)


def DISPLAY(value):  # noqa: N802 - 公式里用的中文函数名对应这个 Python 函数
    hits.append((Kl.cur_code, Kl.cur_name, value))


def main():
    parser = argparse.ArgumentParser(description="Klang 中文公式样例（本地缓存，不联网）")
    parser.add_argument("--list", action="store_true", help="列出所有样例")
    parser.add_argument("--show", metavar="名称", help="打印某个样例的公式正文")
    parser.add_argument("--example", metavar="名称", help="运行某个样例")
    parser.add_argument("--limit", type=int, default=0, help="只扫前 N 只股票（调试用）")
    args = parser.parse_args()

    if args.list:
        for name, formula in EXAMPLES.items():
            first = formula.splitlines()[0]
            print(f"{name:<8} {len(formula):>4} 字  {first}")
        return 0

    if args.show:
        name = args.show
        if name not in EXAMPLES:
            print(f"没有这个样例：{name}，可选：{' / '.join(EXAMPLES)}", file=sys.stderr)
            return 2
        print(EXAMPLES[name])
        return 0

    name = args.example or "均线多头"
    if name not in EXAMPLES:
        print(f"没有这个样例：{name}，可选：{' / '.join(EXAMPLES)}", file=sys.stderr)
        return 2

    original = list(Kl.stocklist)
    if args.limit:
        Kl.stocklist = original[: args.limit]

    formula = EXAMPLES[name]
    # 单票样例本身带 code(...)，不要再包 kloop；其余样例走全市场循环
    script = formula if name == "单票调试" else "kloop\n" + formula + "\nendp;"

    hits.clear()
    try:
        Kexec(script)
    finally:
        Kl.stocklist = original

    scanned = 1 if name == "单票调试" else (args.limit if args.limit else len(original))
    print(f"样例：{name}　扫描：{scanned} 只　命中：{len(hits)} 只")
    for code, stock_name, value in hits[:30]:
        print(f"  {code:<12} {stock_name:<10} {value}")
    if len(hits) > 30:
        print(f"  ... 其余 {len(hits) - 30} 只略")
    return 0


if __name__ == "__main__":
    sys.exit(main())
