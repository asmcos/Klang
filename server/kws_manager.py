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
}
app = socketio.WSGIApp(sio, static_files=STATIC_FILES)

mutex = Lock ()
port = 9088
server_list = {}
user_list = []
pending = {}   # user_id -> 还没回 exec_done 的分片数


def finish_if_done(user_id):
    """所有分片都回 exec_done 后才通知网页，避免结果还在路上就说跑完了。"""
    with mutex:
        left = pending.get(user_id, 0)
        if left > 0:
            return
        pending.pop(user_id, None)
    logger.info('任务完成 user=%s', user_id)
    sio.emit('u_done', {"done": "ok"}, to=user_id, namespace="/user")

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

        for new_stock_list in chunks:
            ws = get_server() #没有服务器，分片直接算失败
            if ws is None:
                with mutex:
                    pending[user_id] = max(0, pending.get(user_id, 1) - 1)
                logger.error('没有计算节点，分片终止 user=%s', user_id)
                sio.emit('error_event',{"message":"没有服务器终止"},to=user_id,namespace="/user")
                continue

            data ['stocklist'] = new_stock_list
            sio.emit("do_exec",data,to=ws,namespace="/Kserver")

        finish_if_done(user_id)

class Kserver(socketio.Namespace):
    def on_connect(self,sid,environ):
        print("A new server connect ",sid)
        server_list[sid] = 0
        send_notices()

    def on_disconnect(self,sid):
        server_list.pop(sid, None)
        send_notices()

    def on_ret_loop_list(self,sid,data):

        server_list[sid] = 0
        sio.start_background_task(do_loop,data)

    def on_exec_done(self,sid,data):
        #lock
        server_list[sid] = 0
        user_id = data.get("user_id")
        if user_id:
            with mutex:
                pending[user_id] = max(0, pending.get(user_id, 1) - 1)
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


sio.register_namespace(Kserver('/Kserver'))
sio.register_namespace(User('/user'))


if __name__ == '__main__':
    eventlet.wsgi.server(eventlet.listen(('', port)), app)
