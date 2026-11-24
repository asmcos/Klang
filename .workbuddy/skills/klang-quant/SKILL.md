---
name: klang-quant
description: 使用 Klang（K线股票编程语言，github.com/asmcos/Klang）做 A 股量化分析：安装依赖、下载本地行情数据、用 Python API（C/O/H/L 序列对象）算指标、用中文公式（Kexec/kloop）全市场选股、或跑起 socketio 网页版选股服务。当用户要求「用 Klang 选股」「找今天的涨停股」「用 Klang 算指标/写公式」「下载 A 股数据」「启动 Klang 服务」时使用本技能。This skill should be used when working with the Klang stock K-line language library: setup, data download, Python API, Chinese formula scanning, or the web scan service.
agent_created: true
---

# Klang 量化分析

## 概述

Klang 是股票 K 线编程语言，特点是**中文写公式**（`今日收盘 = C`、`涨幅 > 9.8`）和**整序列运算**（`C[1]` 表示上一根 K 线，`C/C[1]` 直接得到涨跌幅序列）。

本技能固化了三件事：**把数据准备好**（本地缓存，不联网也能用）、**三种交互方式怎么写**（Python API / 中文公式 / 网页服务）、**实测踩过的坑**。

Klang 仓库：<https://github.com/asmcos/Klang> ｜ 问答社区：<https://forum.klang.org.cn>

## 何时使用

- 要用 Klang 跑选股、算技术指标、批量回测某段行情
- 用户问「今天涨停的股票有哪些」「哪些票放量突破」这类需要扫全市场的问题
- 别人的 WorkBuddy 需要知道 Klang 怎么装、数据怎么下、公式怎么写

## 核心前提：数据是本地缓存

**Klang 的 import 不联网**（2026-11 重构后），只读 `~/.klang/`：

```
~/.klang/klang_stock_list.csv      股票列表：code,name,SCR,tdxbk,tdxgn
~/.klang/day/<code>day.json        日K：  [code, name, [{date,open,close,high,low,volume,turn,amount}, ...]]
~/.klang/week/<code>week.json      周K
~/.klang/month/<code>month.json    月K
```

JSON 内记录**倒序**（最新在前）。**没数据先跑更新脚本**，别直接 import 就以为坏了。

---

## 工作流

### 第 1 步：准备环境

```bash
git clone https://github.com/asmcos/Klang.git
cd Klang
pip3 install -r requirements.txt    # numpy/pandas/ply/eventlet/... + eltdx
```

`eltdx` 是取行情数据的依赖（通达信协议），`ply` 是中文公式的语法引擎，两个都不能少。

### 第 2 步：下载行情数据

```bash
python3 tools/eltdx_updater.py                # 只更新日K（日常用）
python3 tools/eltdx_updater.py --all          # 全量下载日/周/月K线
python3 tools/eltdx_updater.py --codes sh.600000 sz.000001   # 指定股票
python3 tools/eltdx_updater.py --list          # 强制刷新股票列表
```

实测：**5302 只 A 股增量日K 约 845 秒**（约 0.16 秒/只），数据可到当日收盘。
更新器会自动探测可用行情服务器（`eltdx` 内置 `probe_hosts`），不必手工填 IP。

### 第 3 步：验证环境

```bash
python3 -c "
from Klang import Klang, C
Klang.Klang_init()
print('默认股票:', Klang.Kl.cur_code, Klang.Kl.cur_name)
print('最新收盘:', C.value, '日期:', C.data.index[-1])
"
```

预期：`sh.600000 浦发银行` + 一个收盘价 + `2026-11-24` 这类日期。
若 `C.value` 是 `None`，说明本地没数据，回第 2 步。

---

## 交互方式一：Python API（最直接）

```python
from Klang import Klang, C, O, H, L, V

Klang.Klang_init()
Kl = Klang.Kl

Kl.code('sh.601012')              # 切换股票
Kl.date(start='2026-01-01')       # 设置区间（默认从 2021-01-01 开始）

C.value        # 最新收盘（标量）
C.data         # 收盘价序列（pandas Series，索引是日期）
C[1].data      # 上一根 K 线的收盘序列 —— 注意是整条序列，不是单点
C['2026-11-20'] # 按日期取值
(C - C[1]) / C[1]   # 涨跌幅序列（numpy 数组）

MA(C, 5)       # 通达信风格函数：MA/EMA/SMA/WMA/HHV/LLV/REF/REFDATE/CROSS/
               # MACD/RSI/BOLL/KDJ/COUNT/EVERY/EXIST/IIF/STD/ABS/SUM...
```

要点：
- `C` 是**序列对象**不是数字，`C.value` 才是最后一个值；`C.data` 是整条序列。
- `C[1]` 是「前一根」，所以 `C[1].data` 比 `C.data` 少一根——两个序列做运算时长度会自动对齐（取短的那个）。
- 算单个数用 `C.value`、`C[1].value`。

## 交互方式二：中文公式（kloop 全市场扫描）

```python
from Klang.lang import kparser, setPY, Kexec
from Klang import Klang, C, O, H, L, V      # ← 公式里用到的序列必须 import 进来

Klang.Klang_init()
Kl = Klang.Kl

def getpyglobals(name): return globals().get(name)
def setpyglobals(name, val): globals()[name] = val
setPY(getpyglobals, setpyglobals)

显示 = print        # 中文函数名，指向 python 函数

Kexec("""
kloop
今日收盘 = C
昨日收盘 = C[1]
涨幅 = (今日收盘-昨日收盘)/昨日收盘*100
if 涨幅[-1] > 9.8:
    显示(Kl.cur_code, Kl.cur_name, 涨幅[-1])
endp
""")
```

`kloop ... endp` 会**遍历 `Kl.stocklist` 全部股票**，逐只 `Kl.code()` 后执行块内语句。

### 中文公式的四个硬性约束（实测踩过）

1. **序列要先 import 进作用域**。公式里的 `C` 是从 python 全局取名字，漏了 `from Klang import C` 会报
   `TypeError: 'NoneType' object is not subscriptable`（取 `C[1]` 时炸）。
2. **公式里的运算结果是序列，比较前要取末值 `[-1]`**。
   `涨幅 > 9.8` 会报 `TypeError: int() argument must be ... not 'KdataBase'`；正确写法是 `涨幅[-1] > 9.8`。
3. **公式里只能调用 python 全局里存在的函数**。`setPY` 只自动注入 `str/int/float/min/max/len`，
   写 `round(...)` 会报 `TypeError: 'NoneType' object is not callable`。要别的函数就在 python 侧定义好再传。
4. **调试时先限制股票数**：`Kl.stocklist = Kl.stocklist[:200]`，否则全市场刷屏且难定位错误。
   公式执行出错会打印 `Klang ERROR <code> <name>` 和 traceback，但**不会中断整个循环**。

中文公式还支持：`MA(C,60)`、`CROSS(C,MA(C,60))`、`:=` 赋值、`if/else`、`for/range`、
`print(...)`、以及 `kloop`/`endp`/`kstop`。

## 交互方式三：网页选股服务

```bash
python3 server/kws_manager.py     # socketio 管理端（端口 9088）
python3 server/kws_server.py      # 计算节点
```

两个都要起，然后打开 `server/online.html`（或线上 <https://klang.org.cn/online.html>）。
manager 把全 A 股扫描任务分片派发到多个 server 并行计算，网页端写公式、收结果。
单机调试用前两种方式就够，分布式才需要起服务。

---

## 实战：找今天的涨停股票

仓库自带现成脚本（2026-11 新增）：

```bash
python3 tools/limit_up.py            # 今日涨停
python3 tools/limit_up.py --down     # 今日跌停
python3 tools/limit_up.py --broken   # 炸板（盘中触及涨停但没封住）
python3 tools/limit_up.py --date 2026-11-24
python3 tools/limit_up.py --limit 200   # 只扫前 200 只（调试）
```

输出表格含：代码、名称、涨幅%、收盘、昨收、成交额（亿）、换手%、涨跌幅限制档位。
全市场 5302 只扫描约 **18 秒**。

### 涨停判定规则（别写死）

```
主板（sh.60 / sz.00）      ±10%
创业板（sz.30）、科创板（sh.68） ±20%
主板 ST/*ST                ±5%
退市整理期（名字仍带 ST）    ±10%   ← 容易漏掉的一档
```

**判定用价格而不是涨幅**：涨停价 = `round(昨收 × (1 + 限制), 2)`，
当 `|收盘 - 涨停价| < 0.005` 且 `最高价 == 涨停价`（即封住板）才算涨停。
只看涨幅百分比会漏掉退市整理期股票，也会把「涨到 9.98% 但没封板」的票算进去。

---

## 关键坑速查

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| `import Klang` 报连不上服务器 | 旧版本 import 会联网取 host | 现已改为纯本地；确认用的是新版本 |
| `C.value` 是 None / `C.data` 是空序列 | 本地没数据 | 跑 `tools/eltdx_updater.py` |
| 数据停在几天前 | 缓存是最后一个交易日的数据 | 收盘后重跑更新脚本 |
| 盘中扫出的涨停数一直在变 | 当日 K 线是**盘中快照**，不是收盘价 | 收盘后（15:00 后）再扫才有意义 |
| 成交量比别家的数据小 100 倍 | 通达信接口的 `volume_lots` 日K 是「手」（×100=股），周/月是「百手」（×10000=股） | 用 `成交额 ÷ 均价` 反推校验 |
| 股票名字变成代码（如 `sh.600000`） | 名称表没取到 | 名称来源优先级：eltdx 名称表 → 日K 文件 → 旧 CSV |
| 公式里 `round()` 报 NoneType 不可调用 | 公式只能调 python 全局里的函数 | 在 python 侧定义好，或改用 `int(x*100)/100` |

## 别做的事

- 不要在 import 阶段加联网请求——数据层已经明确是「导入只读本地」，联网交给更新脚本。
- 不要把更新逻辑塞进 `Klang_init()`，它只负责本地加载。
- 不要用 `涨幅 > 9.8` 当涨停判据（漏退市整理期、误收未封板股）。
- 不要假设 `~/.klang` 里的数据一定是今天，先查 `C.data.index[-1]`。
