# Klang 中文公式：给 AI Agent 的速查样例

这份文件是给 WorkBuddy / Claude / 其他 agent 看的。**先看这里，再看 `SKILL.md`**，按下面的写法抄就能跑。
所有例子都基于本地缓存 `~/.klang/`，不需要联网；公式引擎是 `Kexec` / `kloop`。

---

## 0. 三条命令建立信任

```bash
cd /home/jsh/work/Klang

# 1) 看有哪些官方样例、各自干什么
python3 examples/formula_examples.py --list

# 2) 只扫前 200 只，验证公式能跑（约 1 秒）
python3 examples/formula_examples.py --example 均线多头 --limit 200

# 3) 确认某个公式的完整代码
python3 examples/formula_examples.py --show 涨停
```

如果能打印出命中股票，说明数据、import、`setPY` 全部正确。
扫描全市场去掉 `--limit` 即可；不要一上来就 `Kexec` 5000 只。

---

## 1. 四条硬性约束（违反必炸）

| # | 规则 | 错误现场 | 正确做法 |
| --- | --- | --- | --- |
| 1 | 公式用到的序列必须先 import 到 Python 全局 | `from Klang import C` 漏掉 → `TypeError: 'NoneType' object is not subscriptable`（取 `C[1]` 时） | `from Klang import Kl, Klang, C, O, H, L, V, MA, MACD, CROSS` |
| 2 | 运算结果是**序列**，比较/打印前取末值 `[-1]` | `涨幅 > 9.8` → `TypeError: int() argument must be ... not 'KdataBase'` | `涨幅[-1] > 9.8` |
| 3 | 公式只能调用 Python 全局里已有的函数 | `round(x, 2)` → `TypeError: 'NoneType' object is not callable` | 在 Python 侧 `def round2(x): return round(x,2)`，或 `setPY` 桥接后再用 |
| 4 | 调试先缩小股票池 | 全市场刷屏、报错难定位 | `Kl.stocklist = Kl.stocklist[:200]` |

补充：`setPY(getpyglobals, setpyglobals)` 只自动注入 `str/int/float/min/max/len`；
`DISPLAY`、`print`、`getstockinfo` 这类函数要么来自 server 全局，要么自己在 Python 侧定义。

最小骨架（本地 Python 里跑公式必须照这个写）：

```python
from Klang.lang import Kexec, setPY
from Klang import Kl, Klang, C, O, H, L, V, MA, MACD, CROSS   # ①

Klang.Klang_init()

def getpyglobals(name): return globals().get(name)
def setpyglobals(name, val): globals()[name] = val
setPY(getpyglobals, setpyglobals)                                # ③

hits = []
def DISPLAY(value):                                             # 自定义输出函数
    hits.append((Kl.cur_code, Kl.cur_name, value))

Kl.stocklist = Kl.stocklist[:200]                               # ④

Kexec("""
kloop
涨幅 = (C - C[1]) / C[1] * 100
if 涨幅[-1] > 9.8:                                              # ②
    DISPLAY(涨幅[-1])
endp;
""")
```

---

## 2. 五个可复制的公式

### 2.1 涨停扫描（最常用）

```text
涨停线 = 9.8
今日收盘 = C
昨日收盘 = C[1]
涨幅 = (今日收盘 - 昨日收盘) / 昨日收盘 * 100
if 涨幅[-1] > 涨停线:
    DISPLAY(涨幅[-1])
```

注意：这只是**中文公式的教学写法**。真正的涨停判定不能用 9.8% 百分比，
要按「涨停价 = round(昨收 × (1 + 档位), 2)」并确认收盘封在涨停价，见 `tools/limit_up.py`。

### 2.2 均线多头排列

```text
ma5 = MA(C, 5)
ma10 = MA(C, 10)
ma20 = MA(C, 20)
if ma5[-1] > ma10[-1] and ma10[-1] > ma20[-1]:
    DISPLAY(ma5[-1])
```

### 2.3 放量站上 20 日线

```text
ma20 = MA(C, 20)
vol5 = MA(V, 5)
vol60 = MA(V, 60)
if C[-1] > ma20[-1] and vol5[-1] > vol60[-1] * 1.5:
    DISPLAY(C[-1])
```

### 2.4 MACD 金叉

`MACD(C)` 返回三个序列：DIF / DEA / 柱。

```text
dif, dea, macd = MACD(C)
if dif[-1] > dea[-1] and dif[-2] <= dea[-2]:
    DISPLAY(dif[-1])
```

### 2.5 单票调试（不加 `kloop`）

```text
code('sh.600000');
ma20 = MA(C, 20);
if C[-1] > ma20[-1]:
    DISPLAY(C[-1]);
```

非 `kloop` 脚本的每条语句都要用 `;` 结尾（kloop 块内靠换行即可）。
`code()` 在 Python 侧对应 `code = Kl.code`，必须先定义再 `setPY`。

网页端选「单票运行」时，manager 会自动注入 `code('...')`，公式里**不要再写 `code()`**。

---

## 3. Python API 等价写法（不用公式时优先用这个）

```python
from Klang import Klang, C, V, MA
Klang.Klang_init()
Kl = Klang.Kl
Kl.code('sh.600000')

C.value            # 最新收盘，标量
C.data             # 整条收盘序列，pandas Series
C[1].value         # 上一根 K 线收盘
(C / C[1] - 1)     # 涨跌幅序列，直接算，不用循环
MA(C, 20).data     # 20 日均线序列
```

规律：**Python API 里序列直接运算；中文公式里比较前取 `[-1]`。**

---

## 4. 网页服务怎么接

```bash
python3 server/kws_manager.py   # Socket.IO 管理端，端口 9088，同时提供网页
python3 server/kws_server.py    # 计算节点，另开一个终端
```

浏览器打开 <http://127.0.0.1:9088/studio>。

协议（见 `server/README.md`）：浏览器连 `/user` 命名空间，发
`uexec_event {content, loop, code?}`；收 `u_ret`（DISPLAY/PROGRESS）、`u_info`、`u_done`。
`loop=true` 走全市场分片扫描；`loop=false` 且带 `code` 走单票。

---

## 5. 报错对照表

| 报错 | 原因 | 处理 |
| --- | --- | --- |
| `'NoneType' object is not subscriptable` | `C` 没 import 进 Python 全局 | 补 `from Klang import C` |
| `int() argument must be ... not 'KdataBase'` | 直接拿序列做比较 | 比较对象改成 `序列[-1]` |
| `'NoneType' object is not callable` | 公式调用了 Python 全局没有的函数 | Python 侧定义同名函数后再 `Kexec` |
| `C.value` 是 `None` | 本地没数据 | `python3 tools/eltdx_updater.py` |
| 扫出来 0 只但没报错 | 条件太严 / 数据不是当天 | 先 `--limit 200` 打印几条 `C[-1]` 看数值 |
| 公式执行一半刷 `Klang ERROR` | 单只股票数据不足 | 正常现象，kloop 会吞掉继续；看 traceback 定位 |
