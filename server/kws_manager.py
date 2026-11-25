import socketio
import eventlet
from threading import Lock,Thread
import threading
import sys,time,os
import json
import logging
from logging.handlers import RotatingFileHandler

# 错误/任务日志落盘：tail -f server/server.log 即可排障
LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'server.log')
logger = logging.getLogger('klang.manager')
logger.setLevel(logging.INFO)
if not logger.handlers:
    _h = RotatingFileHandler(LOG_FILE, maxBytes=2 * 1024 * 1024, backupCount=3, encoding='utf-8')
    _h.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
    logger.addHandler(_h)

# K WS manager 9088
# nginx ws 8099 -> 9088
# nginx wss 9099 -> 9088


# create a Socket.IO server
sio = socketio.Server( cors_allowed_origins='*' )

# 同一个 WSGI 入口同时提供 Socket.IO 和网页界面，浏览器直接开 http://host:9088/studio
HERE = os.path.dirname(os.path.abspath(__file__))
STATIC_FILES = {
    '/':              {'content_type': 'text/html',      'filename': os.path.join(HERE, 'klang_studio.html')},
    '/studio':        {'content_type': 'text/html',      'filename': os.path.join(HERE, 'klang_studio.html')},
    '/studio.html':   {'content_type': 'text/html',      'filename': os.path.join(HERE, 'klang_studio.html')},
    '/online.html':   {'content_type': 'text/html',      'filename': os.path.join(HERE, 'online.html')},
    '/socket.io.min.js': {'content_type': 'application/javascript',
                          'filename': os.path.join(HERE, 'vendor', 'socket.io.min.js')},
    '/spoken_catalog.json': {'content_type': 'application/json',
                             'filename': os.path.join(HERE, 'spoken_catalog.json')},
}
app = socketio.WSGIApp(sio, static_files=STATIC_FILES)

mutex = Lock ()
port = 9088
server_list = {}
user_list = []
pending = {}   # user_id -> 还没回 exec_done 的分片数
inflight = {}  # 计算节点 sid -> 正在执行的 user_id
listing = {}   # 计算节点 sid -> 正在要股票列表的 user_id


def finish_if_done(user_id):
    """所有分片都回 exec_done 后才通知网页，避免结果还在路上就说跑完了。

    pending 里已经没有这个用户时直接返回，避免完成信号发两次。
    """
    with mutex:
        if user_id not in pending:
            return
        if pending[user_id] > 0:
            return
        pending.pop(user_id, None)
    logger.info('任务完成 user=%s', user_id)
    sio.emit('u_done', {"done": "ok"}, to=user_id, namespace="/user")


def release_chunk(user_id):
    """一个分片结束或丢失时减计数，减到 0 就通知网页。"""
    with mutex:
        if user_id not in pending:
            return
        pending[user_id] = max(0, pending[user_id] - 1)
    finish_if_done(user_id)

def get_server():
    if len(server_list.keys()) < 1:
        return None
    while True:
        eventlet.sleep(0.001)
        mutex.acquire()
        for s in server_list.keys():
            if server_list[s] == 0:
                server_list[s] = 1
                mutex.release()
                return s
        mutex.release()

def do_loop(data):
        stocklist = data["stocklist"]
        del data["stocklist"]
        content = data["content"]
        user_id = data["user_id"]
        
        chunks = [stocklist[i:i+20] for i in range(0,len(stocklist),20)]
        with mutex:
            pending[user_id] = len(chunks)
        sio.emit('u_scan', {"total": len(stocklist)}, to=user_id, namespace="/user")

        for new_stock_list in chunks:
            ws = get_server() #没有服务器，分片直接算失败
            if ws is None:
                logger.error('没有计算节点，分片终止 user=%s', user_id)
                sio.emit('error_event',{"message":"没有服务器终止"},to=user_id,namespace="/user")
                release_chunk(user_id)
                continue

            data ['stocklist'] = new_stock_list
            with mutex:
                inflight[ws] = user_id
            sio.emit("do_exec",data,to=ws,namespace="/Kserver")

        finish_if_done(user_id)

class Kserver(socketio.Namespace):
    def on_connect(self,sid,environ):
        print("A new server connect ",sid)
        server_list[sid] = 0
        send_notices()

    def on_disconnect(self,sid):
        with mutex:
            server_list.pop(sid, None)
            listed = listing.pop(sid, None)
            owner = inflight.pop(sid, None)
        if listed:
            logger.error('计算节点在取股票列表时断开 user=%s', listed)
            sio.emit('error_event', {"message": "计算节点断开，任务终止"},
                     to=listed, namespace="/user")
        if owner:
            # 这一片不会再回 exec_done。记一条错误，其余分片继续。
            logger.error('计算节点执行中断开 user=%s', owner)
            sio.emit('u_ret', {"retcode": "ERROR", "name": "", "code": "",
                               "value": "计算节点断开，该分片未完成",
                               "user_id": owner}, to=owner, namespace="/user")
            release_chunk(owner)
        send_notices()

    def on_ret_loop_list(self,sid,data):
        with mutex:
            listing.pop(sid, None)
            server_list[sid] = 0
        sio.start_background_task(do_loop,data)

    def on_exec_done(self,sid,data):
        #lock
        user_id = data.get("user_id")
        with mutex:
            inflight.pop(sid, None)
            server_list[sid] = 0
            if user_id and user_id in pending:
                pending[user_id] = max(0, pending[user_id] - 1)
        if user_id:
            finish_if_done(user_id)

    def on_user_ret(self,sid,data):
        if data.get("retcode") == "ERROR":
            logger.error('公式错误 code=%s: %s', data.get("code"), data.get("value"))
        self.emit('u_ret',data,to=data["user_id"],namespace="/user")


def send_notices():
    server_state = []
    for key in server_list.keys() :
            server_state.append(server_list[key])
    msg = {
        "servers":server_state,
        "users":len(user_list),
    }
    for user in user_list:
        sio.emit("u_info",msg,to=user,namespace="/user")


class User(socketio.Namespace):
    def on_connect(self,sid,environ):
        print("A new user connect ",sid)
        user_list.append(sid)
        send_notices()
    def on_disconnect(self,sid):
        if sid in user_list:
            user_list.remove(sid)
        pending.pop(sid, None)
        send_notices()
    def on_uexec_event(self,sid,data):
        #
        # 'u_exec_event',{content:vue.$data.sourcecode,loop:true}
        #
        server = get_server()
        if server is None:
            logger.error('收到任务但没有计算节点 user=%s', sid)
            self.emit("error_event",{"message":"没有发现服务器"})
            return 

        logger.info('收到任务 user=%s loop=%s 代码段=%s', sid, bool(data.get("loop")),
                    repr(data.get("content", ""))[:200])
        print(data)
        data["user_id"] = sid
        if data.get("loop") == True:
            data['loop'] = False
            with mutex:
                listing[server] = sid
            sio.emit("loop_list_event",data,to=server,namespace="/Kserver")
        else:
            # 单票模式：网页发 {content, loop:false, code:"sh.600000"}
            # 计算节点需要 stocklist，manager 在这里补上，避免 KeyError
            if not data.get("stocklist"):
                code = data.get("code")
                if not code:
                    logger.error('单票模式缺少 code 参数 user=%s', sid)
                    self.emit("error_event",{"message":"单票模式缺少 code 参数"})
                    return
                data["stocklist"] = [{"code": code}]
                data["single"] = True
            with mutex:
                pending[sid] = 1
                inflight[server] = sid
            sio.emit('u_scan', {"total": len(data["stocklist"])}, to=sid, namespace="/user")
            sio.emit("do_exec",data,to=server,namespace="/Kserver")
            
    def on_u_cmd_event(self,sid,data):
        #
        # 'u_cmd_event', {content:"UPDATEALL"}
        #
        if data.get("content") == "UPDATEALL":
            for s in server_list.keys():
                sio.emit("do_updataall",{},s,namespace="/Kserver")
        if data.get("content") == "DOWNLOADALL":
            for s in server_list.keys():
                sio.emit("do_downloadall",{},s,namespace="/Kserver")

    # ---- 数据门户：只暴露 eltdx 能提供的数据与本地缓存状态 ----
    def on_portal_req(self, sid, data):
        """网页请求数据，统一回 portal_resp，避免阻塞事件循环。"""
        import data_portal as dp
        action = data.get("action") if isinstance(data, dict) else None
        reply = {"action": action, "ok": False}
        # 前端按 id 匹配 portal_resp 的回调，必须原样带回，否则页面拿不到任何数据
        if isinstance(data, dict) and data.get("id") is not None:
            reply["id"] = data["id"]
        try:
            if action == "status":
                reply.update(ok=True, data=dp.status(),
                             update=dp.update_state())
            elif action == "stocks":
                reply.update(ok=True, data=dp.stocks(
                    data.get("keyword", ""), int(data.get("offset", 0)),
                    min(int(data.get("limit", 50)), 200),
                    bool(data.get("only_kline"))))
            elif action == "watchlist":
                reply.update(ok=True, data=dp.watchlist())
            elif action == "watch_add":
                reply.update(ok=True, data=dp.watch_add(data.get("code")))
            elif action == "watch_remove":
                reply.update(ok=True, data=dp.watch_remove(data.get("code")))
            elif action == "quotes":
                codes = data.get("codes") or []
                if not isinstance(codes, list):
                    codes = [codes]
                reply.update(ok=True, data=dp.quotes(codes))
            elif action == "update_start":
                kind = data.get("kind", "day")
                if kind not in ("day", "all", "list"):
                    raise ValueError("未知的更新类型")
                def emit(event, payload):
                    sio.emit(event, payload, to=sid, namespace="/user")
                started = dp.start_update(kind, emit=emit)
                reply.update(ok=True, data={"started": started,
                                            "message": "已有更新任务在运行" if not started else "已开始"})
            elif action == "update_state":
                reply.update(ok=True, data=dp.update_state())
            else:
                reply["message"] = "未知操作"
        except Exception as exc:
            logger.exception('数据门户请求失败 user=%s action=%s', sid, action)
            reply["message"] = str(exc)
        self.emit("portal_resp", reply, to=sid)


sio.register_namespace(Kserver('/Kserver'))
sio.register_namespace(User('/user'))


if __name__ == '__main__':
    eventlet.wsgi.server(eventlet.listen(('', port)), app)
