#
# Klang class
# Klang 提供了全局的股票数据，和获取股票数据的方法
# Kdatas 是提供了单只股票的数据和计算方法
#
from . import data_klang as datakl
from .common import * 
import copy
import threading

class Klang():
    def __init__(self):
        self.data_engine  = datakl #klang data server
        # 加载数据时 设置的加载时间范围
        self.start_date   = start #common.py
        self.end_date     = end   #common.py 全部数据的最后交易周期
        self.stocklist    = []
        self.stockdict    = {} # {code:name} code to name
        self.day_df       = None  #当前选择的股票pandas格式数据
        self.week_df       = None  #当前选择的股票pandas格式数据
        self.month_df       = None  #当前选择的股票pandas格式数据
        self.cur_code     = None
        self.cur_name     = None
        #某次计算过程中 需要的数据片段
        self.dfstart      = "2021-01-01"
        self.dfend        = end #当前要计算的交易周期
        self.reload       = False
        self.canUpdate    = False # 允许更新update_list.csv        



    def get_day(self):
        code = self.cur_code 
        df = self.data_engine.day_data.get_data(self,code,self.start_date,self.end_date)
        df = df[self.dfstart:self.dfend] 
        self.day_df = df

    def get_week(self):
        code = self.cur_code 
        wdf = self.data_engine.week_data.get_data(self,code,self.start_date,self.end_date)
        wdf = wdf[self.dfstart:self.dfend] 
        self.week_df = wdf

    def get_month(self):
        code = self.cur_code   
        mdf = self.data_engine.month_data.get_data(self,code,self.start_date,self.end_date)
        mdf = mdf[self.dfstart:self.dfend] 
        self.month_df = mdf 

    #每次加载的时候可以设置并且获取部分数据
    # copy.deepcopy 深度复制数据，以免破坏

    def code(self,code):
        self.cur_code = code
        self.cur_name = self.stockdict[code]['name']
        self.get_day()
        self.week_df = None
        self.month_df = None





    def date(self,start="2021-01-01",end=end):

        self.dfstart=start
        self.dfend=end
        
        self.day_df = None 
        self.week_df = None
        self.month_df = None




    # 筹码 scr
    def chouma(self):
        return self.data_engine.get_scr(self.cur_code)
    
    """
    获取所有的A股的日K数据

    数据更新已迁到 tools/eltdx_updater.py（基于 eltdx），本方法仅保留
    为兼容旧调用：它只刷新当前日期区间，不联网下载。
    """
    def get_all_data(self):
        self.dfend = get_date(0)
        self.end_date = get_date(0)

    # 重新下载所有的数据 — 转交给 eltdx 更新器
    def downloadall(self):
        from tools.eltdx_updater import update_all
        update_all(self, incremental=False)

    # 增量更新数据 — 转交给 eltdx 更新器
    def updateall(self):
        from tools.eltdx_updater import update_all
        update_all(self, incremental=True)

Kl = Klang()

def Klang_init():
    global Kl
    import os

    # 只从本地缓存初始化股票列表；列表缺失时 init_stock_list 给出更新提示，
    # 不会在 import 期联网下载。
    Kl.stocklist = Kl.data_engine.init_stock_list(Kl)
    if not Kl.stocklist:
        return

    # 默认股票取本地日K存在的第一只；一只都没有就不加载，避免对空数据
    # 调 Kl.date() 报 TypeError。import 期只读本地、不联网。
    day_dir = datakl.data_path + "/day/"
    cur = None
    for item in Kl.stocklist:
        if os.path.exists(datakl.get_path(day_dir + item["code"] + "day.json")):
            cur = item
            break
    if cur is None:
        print("[Klang] 本地没有任何日K数据，未加载默认股票。")
        print("[Klang] 更新请运行：python3 tools/eltdx_updater.py")
        return

    Kl.cur_code = cur["code"]
    Kl.cur_name = cur["name"]
    Kl.date(start='2021-01-01')
    Kl.code(Kl.cur_code)

    
