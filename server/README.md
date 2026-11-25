# Klang server：文件职责、协议与网页界面

## 一句话结论

**当前在用 Socket.IO 三件套**：`kws_manager.py`（管理端 + 网页）、`kws_server.py`（计算节点）、`klang_studio.html`（新网页，另保留旧 `online.html`）。
2022-10-19 换协议前的原生 WebSocket 旧版 `kws_manager_ws.py` / `kws_server_ws.py` 已于 2026-11-25 删除（可从 git 历史恢复），requirements.txt 里也没有 `websockets` 依赖。

| 文件 | 状态 | 说明 |
| --- | --- | --- |
| `kws_manager.py` | 当前在用 | Socket.IO 管理端，端口 9088；同时提供静态网页 |
| `kws_server.py` | 当前在用 | 计算节点，连接 9088 的 `/Kserver`，调 `Kexec` 执行公式 |
| `klang_studio.html` | 新增 | 配套网页：公式样例、全市场/单票运行、结果表格、过滤、CSV 导出 |
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

- 连上后显示计算节点数、在线用户数，断线可一键重连
- 五个内置公式样例，点一下载入编辑器（涨停 / 均线多头 / 放量突破 / MACD 金叉 / 单票调试）
- **全市场扫描**：`loop=true`，manager 把股票列表按 20 只分片发给计算节点并行跑
- **单票调试**：填代码（如 `sh.600000`），manager 自动注入 `code('...')`，秒级返回
- 实时显示 DISPLAY 结果、PROGRESS 次数、错误信息和耗时；结果可过滤、排序、导出 CSV
- 数据更新命令按钮：`u_cmd_event` 支持 `UPDATEALL` / `DOWNLOADALL`（对应页面上的工具入口，旧 online.html 有）

## Socket.IO 协议

浏览器连命名空间 `/user`，计算节点连 `/Kserver`，都在 `http://<host>:9088`。

### 浏览器 → manager

| 事件 | 载荷 | 说明 |
| --- | --- | --- |
| `uexec_event` | `{content: "公式源码", loop: true}` | 全市场扫描 |
| `uexec_event` | `{content: "公式源码", loop: false, code: "sh.600000"}` | 单票调试；manager 补 `stocklist` |
| `u_cmd_event` | `{content: "UPDATEALL"}` 或 `{content: "DOWNLOADALL"}` | 更新/下载本地数据 |

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
| `user_ret`（`retcode=ERROR`） | `u_ret` | `{code, value:<异常文本>, user_id}` |
| `exec_done` | - | `{user_id, single}`；manager 等所有分片回齐才发 `u_done` |
| - | `u_info` | `{servers:[0/1...], users:n}` |
| - | `u_done` | `{done:"ok"}`；异常时 `{retcode:"没有服务器终止"}` |

### 写公式的两个注意点

1. 计算节点在每个分片前自动拼 `code('<代码>')\n;`，公式里**不要再写 `code()`**。
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
