import socketio
from threading import Lock
import logging
from logging.handlers import RotatingFileHandler

import threading
import sys,os

# 日志落盘：tail -f server/server.log
LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'server.log')
logger = logging.getLogger('klang.server')
logger.setLevel(logging.INFO)
if not logger.handlers:
    _h = RotatingFileHandler(LOG_FILE, maxBytes=2 * 1024 * 1024, backupCount=3, encoding='utf-8')
    _h.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
    logger.addHandler(_h)

# 必须用本仓库源码；append 会被 site-packages 里的旧 Klang egg 抢先，import 阶段就联网崩掉
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

######################klang #######################
from Klang.lang import kparser,setPY,Kexec

from Klang import (Kl,
    OPEN, O,
    HIGH, H,
    LOW, L,
    CLOSE, C,
    VOLUME, V, VOL,
    TURN,T,
    DATETIME,

    WOPEN, WO,
    WHIGH, WH,
    WLOW, WL,
    WCLOSE, WC,
    WVOLUME, WV, WVOL,
    WTURN,WT,
    WDATETIME,

    MOPEN, MO,
    MHIGH, MH,
    MLOW, ML,
    MCLOSE, MC,
    MVOLUME, MV, MVOL,
    MTURN,MT,
    MDATETIME,

    SMA,MA,EMA,WMA,

    SUM,ABS,STD,

    CROSS,
    REF,BARSLAST,BARSCOUNT,BARSLASTFIND,
    MAX,
    MIN,
    EVERY,
    COUNT,
    HHV,
    LLV,
    IF, IIF,
    MACD,APPROX,
    TRANSVERSE,RSI,BOLL,STOCH)

from Klang.Klang import Klang_init

if len(sys.argv) > 1:
    canUpdate = sys.argv[1]
    if canUpdate == "canUpdate":
        Kl.canUpdate = True

Klang_init()

code = Kl.code
date = Kl.date

def getpyglobals(name):
    return globals().get(name)

def setpyglobals(name,val):
    globals()[name]=val


setPY(getpyglobals,setpyglobals)

def getstockinfo(name=0):
    code = Kl.cur_code
    return Kl.stockdict[code]['name'], code,\
            Kl.day_df['hqltsz'].iloc[-1],\
            Kl.stockdict[code]['tdxbk'],\
            Kl.stockdict[code]['tdxgn']

def getInfo(name):
    code = Kl.cur_code
    return Kl.stockdict[code][name]

def get_chouma(code=0):
    return Kl.chouma()

def kloopexec(content):
    code = "kloop \n" + content + "\nendp;"
    return code

def updateall(msg):
    print("update",msg)
    t = threading.Thread(target=Kl.updateall)
    t.start()
def downloadall(msg):
    print("download",msg)
    t = threading.Thread(target=Kl.downloadall)
    t.start()

mutex = Lock ()

user_id = ""
p_count = 0 
def PROGRESS(val=1):
    global p_count
    p_count +=1
    if val == 0 or p_count % val != 0:
        return 
    
    name,code,hqltsz,tdxbk,tdxgn = getstockinfo()
    message = {"retcode":"PROGRESS","name":name,"code":code,\
        "value":str(val)}
    message['user_id'] = user_id
    sio.emit("user_ret",message,namespace="/Kserver")

def DISPLAY(value):
    name,code,hqltsz,tdxbk,tdxgn = getstockinfo()
    message = {"retcode":"DISPLAY","name":name,"code":code,\
        "value":str(value),"hqltsz":hqltsz,'tdxbk':tdxbk,'tdxgn':tdxgn}
    message['user_id'] = user_id
    sio.emit("user_ret",message,namespace="/Kserver")

def execute(data):
    global user_id 
    logger.info('执行分片 user=%s loop=%s 股票数=%d 公式=%s', data.get("user_id"),
                bool(data.get("loop")), len(data.get("stocklist", [])),
                repr(data.get("content", ""))[:150])
    
    # 1. 判断是否加loop循环之行
    # 2. loop == False, manager 处理循环
    if data.get("loop") is not None and data.get("loop") != False:
        content = kloopexec(data['content'])
    else:
        content = data['content']+"\n"

    # 2. 执行 busy lock 执行锁
    mutex.acquire()
    user_id = data["user_id"]
    err_count = 0
    for stockcode in data ["stocklist"]:
        # 先加载该股票，跳过无本地数据的新股（列表里有代码但没 K 线文件）。
        # 否则公式里的 MA(C,N)[-1] 会对空序列抛 index out of bounds，污染网页错误提示。
        try:
            code(stockcode["code"])
        except Exception as exc:
            logger.warning('跳过无数据股票 code=%s: %s', stockcode["code"], exc)
            continue
        if Kl.day_df is None or len(Kl.day_df) == 0:
            logger.warning('跳过无数据股票 code=%s（本地无 K 线）', stockcode["code"])
            continue

        # 数据已加载，直接执行公式主体（不再重复注入 code()）
        try:
            Kexec(content)
        except Exception as exc:
            # 原来裸 except 直接吞掉，网页端只看到"跑完了但没结果"，这里记日志+回传前 3 条错误
            err_count += 1
            logger.error('Kexec 失败 code=%s: %s', stockcode["code"], exc)
            if err_count <= 3:
                message = {"retcode":"ERROR","name":"","code":stockcode["code"],\
                    "value":str(exc),"user_id":user_id}
                sio.emit("user_ret",message,namespace="/Kserver")
    # unlock
    mutex.release()   #之行完成，解锁，发通知给web用户
    #print('执行完成')

    # 3. 执行完成
    
    sio.emit('exec_done',{"user_id":user_id,"single":bool(data.get("single"))},namespace="/Kserver")
    user_id = ""

def get_stock_list(data):
    print(data)
    stocklist = Kl.stocklist
    data ["stocklist"]  = stocklist
    return data

sio = socketio.Client()
hostserver = 'http://localhost:9088'
#hostserver = 'https://klang.org.cn:8099'
          
class KserverNamespace(socketio.ClientNamespace):
    def on_connect(self):
        print('connection established',sio.namespaces)

    def on_disconnect(self):
        print("disconnected from server")
        logger.warning('与管理端断开连接，退出')
        os._exit(1) #由守护进程解决重启问题

    def on_loop_list_event(self,data):
        data =  get_stock_list(data) 
        self.emit("ret_loop_list",data,namespace="/Kserver")

    def on_do_exec(self,data):
        execute(data)
    def on_do_updataall(self,data):
        updateall(data)

    def on_do_downloadall(self,data):
        downloadall(data)

sio.register_namespace(KserverNamespace('/Kserver'))
sio.connect(hostserver,namespaces=["/Kserver"])
sio.wait()
