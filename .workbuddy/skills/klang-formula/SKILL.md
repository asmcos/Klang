---
name: klang-formula
description: 编写并运行 Klang 中文选股公式。在需要写公式、改公式、解释 C/O/H/L、MA、MACD、CROSS、[-1]、kloop、DISPLAY，或 spoken 目录里没有对应说法时使用。Use when writing or debugging a Klang formula, including Chinese formula syntax, sequence indexing, and indicator calls.
---

# Klang 公式怎么写

公式是给 `Kexec` 跑的中文脚本。比较和输出都看**最后一根 K 线**。全市场扫描由外层循环完成，公式正文里不要再写 `kloop`。

## 先跑起来

```bash
cd /media/jsh/work/Klang   # 换成本机仓库目录
python3 examples/spoken_scan.py --show 均线多头
python3 examples/spoken_scan.py --run "均线多头" --limit 200
```

`--limit 200` 通过后再去掉，扫全市场。不要先对 5000 只试语法。

## 骨架

网页选股和 `spoken_scan.py` 都是逐只股票执行下面这种正文（换行即语句结束）：

```text
ma5 = MA(C, 5)
ma10 = MA(C, 10)
if ma5[-1] > ma10[-1]:
    DISPLAY(ma5[-1])
```

本地自己包循环时才加 `kloop` / `endp`：

```python
from Klang.lang import Kexec, setPY
from Klang import Kl, Klang, C, O, H, L, V, MA, MACD, CROSS
Klang.Klang_init()

def getpyglobals(name): return globals().get(name)
def setpyglobals(name, val): globals()[name] = val
setPY(getpyglobals, setpyglobals)

def DISPLAY(value):
    print(Kl.cur_code, Kl.cur_name, value)

Kexec("""
kloop
ma5 = MA(C, 5)
if ma5[-1] > C[-1]:
    DISPLAY(ma5[-1])
endp;
""")
```

公式里出现的 `C`、`MA`、`DISPLAY` 必须先存在于 Python 全局。`setPY` 只自动放进 `str/int/float/min/max/len`。

## 四条硬约束

1. 序列先 import：`from Klang import C, O, H, L, V, MA`。漏了会在 `C[1]` 处报 `'NoneType' object is not subscriptable`。
2. 比大小、做输出前取末值：`涨幅[-1] > 5`，`DISPLAY(涨幅[-1])`。`涨幅` 本身是整段序列。
3. 公式里只能调用 Python 全局已有的函数。`round()` 会报 `'NoneType' object is not callable`。要四舍五入就在 Python 侧定义同名函数，或改用 `int(x * 100) / 100`。
4. 切片只能写在名字上：`C[1]`、`涨幅[-1]` 可以，`C[1][-1]`、`CROSS(...)[-1]` 不能。先赋值再切片：`昨收 = C[1]`，然后 `昨收[-1]`。

`[-1]` 是当前这根，`[1]` 和 `[-2]` 是前一根。正数下标是向前数几根。

## 名字

| 口语 | 公式里的名字 |
| --- | --- |
| 收盘 / 开盘 / 最高 / 最低 | `C` `O` `H` `L` |
| 成交量 / 换手 | `V` `T` |
| 昨收 | `C[1]`，赋值后再 `[-1]` |
| 涨幅（%） | `(C - C[1]) / C[1] * 100` |
| 均线 | `MA(C, 5)` `MA(C, 10)` `MA(C, 20)` `MA(C, 60)` |
| 均量 | `MA(V, 5)` |
| 上穿 | `gold = CROSS(MA(C,5), MA(C,10))` 然后 `if gold[-1]` |
| MACD | `dif, dea, macd = MACD(C)` |
| KDJ | `k, d, j = KDJ(C, H, L)` |
| RSI | `rsi = RSI(C, 14)` |
| 布林 | `up, mid, low = BOLL(C, 20, 2)` |
| N 日最高收盘 / 最低收盘 | `HHV(C, N)` `LLV(C, N)` |
| 近 N 根里有几次 | `COUNT(C > C[1], N)`，返回数字，不要再 `[-1]` |
| 代码前缀 / 名称前缀 | `CODELIKE('600')` `NAMELIKE('ST')` |

`DISPLAY(值)` 是选中。计算节点会带上代码、名称、板块再回给网页。

## 不要这样写

- 不要用 `涨幅 > 9.8` 代替封板涨停。主板 10%、创业板/科创板 20%、ST 5%。涨停跌停炸板用 `python3 tools/limit_up.py`。
- 不要在网页公式或 `spoken_scan` 正文里写 `kloop` / `code()`。外层已经逐只加载。
- 不要调用 `round`、`sum`、`abs` 这些没放进全局的 Python 函数。指标用 `SUM` / `ABS`（大写，通达信函数）。
- 单票、不进 `kloop` 的脚本，每条语句用分号：`code('sh.600000');`。换行脚本不用分号。

更长的样例和报错对照在 `examples/agent_formulas.md`。
