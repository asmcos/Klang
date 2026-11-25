# Klang server：文件职责、协议与网页界面

## 一句话结论

**当前在用 Socket.IO 三件套**：`kws_manager.py`（管理端 + 网页）、`kws_server.py`（计算节点）、`klang_studio.html`（新网页，另保留旧 `online.html`）。
2022-10-19 换协议前的原生 WebSocket 旧版 `kws_manager_ws.py` / `kws_server_ws.py` 已于 2026-11-25 删除（可从 git 历史恢复），requirements.txt 里也没有 `websockets` 依赖。

| 文件 | 状态 | 说明 |
| --- | --- | --- |
| `kws_manager.py` | 当前在用 | Socket.IO 管理端，端口 9088；提供静态网页与数据门户事件 |
| `kws_server.py` | 当前在用 | 计算节点，连接 9088 的 `/Kserver`，调 `Kexec` 执行公式 |
| `klang_studio.html` | 当前在用 | 研究台：口语查找、数据台、股票池、自选、选股、公式库 |
| `spoken_catalog.json` | 当前在用 | 口语和公式的对照，网页与 `examples/spoken_scan.py` 共用 |
| `data_portal.py` | 新增 | 数据门户后端：本地数据状态、股票列表、eltdx 实时行情、自选股、更新任务与进度 |
| `online.html` | 旧网页，仍可用 | 依赖外部 CDN；新界面已把 socket.io 客户端落到本地 `vendor/` |
| `vendor/socket.io.min.js` | 新增 | Socket.IO 客户端 4.8.1（MIT），离线可用 |

## 启动

```bash
python3 server/kws_manager.py     # 终端 1：管理端 + 网页
python3 server/kws_server.py      # 终端 2：计算节点（可以开多个）
python3 server/kws_server.py      # 终端 3：再开一个节点，全市场扫描自动分片并行
# ... 建议 5-6 个节点，每个约 140MB 内存
```

**多节点实测（2026-11-25）**：6 个计算节点合计约 840MB 内存；全市场扫描时 6 个节点同时忙，
约 5 秒跑完；网页右上角「计算节点」会显示数量。节点数受限于内存与数据源并发读，开太多收益递减。

浏览器打开：

- <http://127.0.0.1:9088/studio> —— 新界面（推荐）
- <http://127.0.0.1:9088/online.html> —— 旧界面
- <http://127.0.0.1:9088/> —— 默认跳到新界面

部署在 nginx 后面时，把 `/socket.io/` 和 `/studio` 等路径一起反代到 9088；旧注释里的 8099/9099 是历史端口映射。

## 排障：错误日志在哪

两个服务都会把任务与错误写到同一个文件：

```bash
tail -f /home/jsh/work/Klang/server/server.log
```

记录内容包括：收到的任务（user / loop / 公式前 200 字）、每个执行分片、公式异常（`Kexec 失败 code=...: 具体异常`）、转发给网页的 ERROR、无计算节点、任务完成。日志按 2MB 轮转，保留 3 份。

网页上的红色提示来自 `u_ret` 里 `retcode=ERROR` 的消息；同一个错误也会进上面的日志文件，两边内容一致。

## 网页能做什么

门户页 `/studio` 是研究台，左侧六个页面：

1. **研究台**：口语输入框。说法来自 `spoken_catalog.json`，对上之后把公式放进选股台并运行。
2. **选股**：五个快捷样例，也可从公式库载入；全市场按 20 只分片并行，单票填代码秒级返回；结果可过滤、排序、导出 CSV。
3. **公式库**：同一份口语对照表，点一条就载入选股台。
4. **数据台**：A 股数量、本地日 K、最后日期、周/月 K、滞后天数；更新日 K / 全量 / 重拉列表，带进度和更新记录。
5. **股票池**：本地股票列表，按代码或名称搜索、只看已有日 K、分页、加自选。
6. **自选**：代码在 `~/.klang/watchlist.json`；现价由 `eltdx.get_quote()` 获取，红涨绿跌。

地址可以用 `#home` `#formula` `#library` `#data` `#stocks` `#watch` 直接打开。断线可一键重连；侧栏显示计算节点数。旧 `u_cmd_event`（UPDATEALL/DOWNLOADALL）仍保留，供旧 `online.html` 使用。静态文件增加 `/spoken_catalog.json`。

**数据边界**：所有行情数据来自 eltdx（通达信）+ 本地缓存；eltdx 拿不到的（如本地没有的板块/概念）不做展示。自选股列表是本地偏好，不属于行情数据。更新进度由服务端解析 `tools/eltdx_updater.py` 的 stdout 转发（eltdx 本身无进度回调）。

### 更新记录 JSON（网页数据的权威来源）

`~/.klang/update_record.json` 由 `tools/eltdx_updater.py` **独占写入**（原子写，避免半截 JSON），网页只读展示，不再自己扫目录推算：

```json
{
  "schema": 1, "source": "eltdx（通达信）", "updated_at": "2026-11-25 11:48:52",
  "stock_count": 5302, "list_updated": "2026-11-24 12:01",
  "day_count": 5358, "week_count": 0, "month_count": 0,
  "last_date": "2026-11-24", "lag_days": 1,
  "periods": {"day": {"files": 5358, "last_date": "2026-11-24"}, "...": {}},
  "current": {"kind": "day", "label": "更新日 K", "result": "success",
              "started": "...", "finished": "...", "total": 1, "done": 1,
              "ok": 1, "failed": 0, "message": "完成：1/1 成功，耗时 0.1s"},
  "history": ["... 最近 20 次更新，结构同 current ..."]
}
```

- 写入时机：任务开始（running）→ 列表拉取后 → 每 100 只 → 任务结束（success/failed，并刷新各周期文件数与最后日期）；异常也落盘。
- 网页通过 `portal_req:status` 读它；文件未生成时用只读扫描兜底并标记 `record_exists=false`。
- 更新程序与 Klang 库的边界不变：脚本用 eltdx 下载并写盘，Klang 只读取 `~/.klang/` 做公式计算。

## Socket.IO 协议

浏览器连命名空间 `/user`，计算节点连 `/Kserver`，都在 `http://<host>:9088`。

### 浏览器 → manager

| 事件 | 载荷 | 说明 |
| --- | --- | --- |
| `uexec_event` | `{content: "公式源码", loop: true}` | 全市场扫描 |
| `uexec_event` | `{content: "公式源码", loop: false, code: "sh.600000"}` | 单票调试；manager 补 `stocklist` |
| `u_cmd_event` | `{content: "UPDATEALL"}` 或 `{content: "DOWNLOADALL"}` | 旧版更新命令，供 online.html 使用 |
| `portal_req` | `{id, action, ...}` | 数据门户统一请求，见下表 |

### manager → 计算节点

| 事件 | 载荷 | 说明 |
| --- | --- | --- |
| `loop_list_event` | 原请求 + `user_id` | 要股票列表 |
| `do_exec` | `{content, stocklist:[{code}, ...], user_id, loop:false, single?}` | 执行一批股票 |

### 计算节点 → manager → 浏览器

| 事件（Kserver） | 转发为（user） | 载荷 |
| --- | --- | --- |
| `ret_loop_list` | - | 原请求 + `stocklist` |
| `user_ret`（`retcode=DISPLAY`） | `u_ret` | `{name, code, value, hqltsz, tdxbk, tdxgn, user_id}` |
| `user_ret`（`retcode=PROGRESS`） | `u_ret` | `{name, code, value, user_id}` |
| `user_ret`（`retcode=SCAN`） | `u_ret` | `{name, code, user_id}`；每处理一只股票一条，网页滚动代码 |
| - | `u_scan` | `{total:n}`；开扫前告诉网页总共多少只，用来画进度条 |
| `user_ret`（`retcode=ERROR`） | `u_ret` | `{code, value:<异常文本>, user_id}` |
| `exec_done` | - | `{user_id, single}`；manager 等所有分片回齐才发 `u_done` |
| - | `u_info` | `{servers:[0/1...], users:n}` |
| - | `u_done` | `{done:"ok"}`；异常时 `{retcode:"没有服务器终止"}` |

### 数据门户协议

浏览器发 `portal_req`，manager 回 `portal_resp`（带同样的 `id` 用于配对）：

| `action` | 额外载荷 | 返回 `data` |
| --- | --- | --- |
| `status` | - | `{record_exists, stock_count, list_updated, day_count, week_count, month_count, last_date, lag_days, source, updated_at, periods, current, history}`（来自 update_record.json；`periods` 含日/周/月各自的 `files` 与 `last_date`） |
| `stocks` | `keyword, offset, limit, only_kline` | `{total, rows:[{code,name,has_kline}], offset, limit}` |
| `watchlist` | - | `[{code,name}]` |
| `watch_add` / `watch_remove` | `code` | 更新后的自选列表 |
| `quotes` | `codes:[sh.600000,...]` | `[{code,price,pre_close,open,high,low,change_pct,amount}]` |
| `update_start` | `kind: day/all/list` | `{started,message}` |
| `update_state` | - | `{running,phase,done,total,ok,message,started,finished}` |

更新期间 manager 另发 `portal_update_progress` / `portal_update_done`（载荷同 `update_state`）。
自选股行情代码需 `sh600000` 格式，页面传 `sh.600000`，`data_portal._eltdx_code()` 负责转换。

### 写公式的两个注意点

1. 计算节点在每个分片前先 `code('<代码>')` 加载该股票（无本地日 K 的新股会跳过、不报错），公式里**不要再写 `code()`**。
2. 比较前取末值 `[-1]`；非 `kloop` 脚本每条语句要带分号。详见 `../examples/agent_formulas.md`。

## 2026-11-25 修复记录

- 管理端现在直接提供静态页面，`/studio` 不再需要另起静态服务器。
- 修复 `do_loop` 里未定义的 `self.emit`（改为 `sio.emit`），无计算节点时不再继续派发。
- 修复 `kws_server.py` 的 `sys.path.append`：原写法会被 site-packages 里的旧 Klang egg 抢先，导致 import 阶段联网崩溃；改为 `sys.path.insert(0, 仓库根)`。
- `u_done` 改为等所有分片 `exec_done` 后再发，避免"说跑完了但结果还在路上"。
- 公式异常不再被裸 `except` 吞掉，前 3 条以 `retcode=ERROR` 回传网页。
- 支持单票模式：网页发 `code`，manager 补 `stocklist` 并标 `single`。
- 新增 `server/server.log` 落盘日志：任务、分片、公式异常、完成信号都记文件，方便排障。
- 修复用户断线时 `user_list.remove(sid)` 可能抛 `ValueError`，并顺手清理残留的 `pending` 状态。
- 删除原生 WebSocket 旧版 `kws_manager_ws.py` / `kws_server_ws.py`；文档同步清理引用（git 历史可恢复）。
- 修复全市场扫描中 `sh.688845` / `sz.301661` 等"列表里有、本地无 K 线"的新股报错：
  - `Klang/data_klang.py`：无数据返回结构完整的空 DataFrame（含 open/close/vol 等列），不再返回 RangeIndex 空表。
  - `Klang/Klang.py`：`get_day/week/month` 用 `_slice_by_date`，空表跳过日期切片，避免 `cannot do slice indexing on RangeIndex`。
  - `server/kws_server.py`：执行前先加载股票，`day_df` 为空则记 warning 并跳过，不回传 ERROR 污染网页。
  - 验证：6 节点全市场扫描命中 363 只，ERROR 0。
- 门户化改造（2026-11-25）：`klang_studio.html` 从纯公式页改为四标签门户（数据总览/股票列表/自选股/公式选股）；新增 `data_portal.py` 与 `portal_req/resp` 协议；更新按钮走 `tools/eltdx_updater.py` 并解析 stdout 显示进度；自选股本地 JSON + eltdx 实时行情。验证：Python/JS 语法、页面 200、6 节点在线、8 类门户事件端到端、模拟更新器进度事件全部通过。
