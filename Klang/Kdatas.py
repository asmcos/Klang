#
# K-line, stock datas 
# Klang 提供了全局的股票数据，和获取股票数据的方法
# Kdatas 是提供了单只股票的数据和计算方法
# 类似通达信这样的公式，经过计算的数据有时候需要 计算整个周期，有时候是单个周期
# 因此需要封装成 python 类来解决
# 例如： if CLOSE > OPEN, 判断的是单个周期
# 例如： EVERY (CLOSE > OPEN,N) 这时候判断的是多个周期

import numpy as np
import pandas

kl = None
def setstock(kl1):
    global kl
    kl = kl1

def _at(data, index):
    """按下标取值。pandas Series 用整数下标会按标签解释，必须走 iloc。"""
    if isinstance(data, pandas.Series):
        return data.iloc[index]
    return data[index]

"""
df2 = df[(df.date >= '2020-10-01') & 
             (df.date <= '2021-01-01')] 
"""

#获取股票数据
#baostock volume,TDX use vol
#

def getstockdata(name):
    # 本地无数据（未选择股票或尚未下载）时返回空序列，
    # 不要在访问 C.data 时抛难懂的 TypeError 或隐式联网更新。
    if kl.cur_code is None or not kl.stockdict:
        return pandas.Series([], dtype="float64")

    if isinstance(kl.day_df,pandas.core.frame.DataFrame):
        return kl.day_df[name]
    kl.get_day()

    return kl.day_df[name]
        
#做类似C/C[1]计算
#计算涨跌率
#C和C1都是列表，numpy计算的时候需要同样list size
def match_size(*datas_list):
    size = min(len(data) for data in datas_list)
    if size == 0:
        return np.array([]),np.array([])
    #[len-size:]
    new_list = [np.array(data[len(data)-size:]) for data in datas_list]
    return new_list


#股票数据重新定义以方便计算

class KdataBase(object):
    def __init__(self,index=0,data=[],dtype=float):
        self._data = data
        self.dtype = dtype
        self.index = index

    #返回最后一天的数据
    @property
    def value(self):
        if self.data is None or len(self.data) < 1:
            return None
        ret = _at(self.data, -1)
        if self.dtype == float:
            return round(float(ret), 3)
        return ret

    def __bool__(self):
        if self.data is None or len(self.data) < 1:
            return False
        return bool(_at(self.data, -1))

    @property
    def data(self):
        return self._data

    #C,index=0,
    #C[1],index=1
    def __getitem__(self, index):

        #Klang Don't None 类型，因此处理判断位None
        if index is None:
            return None
        if isinstance(index,str):
            try:
                return self.data[index]
            except:
                return None

        if index < 0:
            index = -(index + 1)

        n = self.__class__(index)
        if len(self.data) >index:
            nindex = len(self.data) - index
            n._data = self.data[:nindex]
        else:
            raise StopIteration
        return n
    # <
    def __lt__(self, other):
        if isinstance(other,KdataBase):  
            kb = KdataBase()
            d1,d2 = match_size(self.data,other.data)
            kb._data = d1 < d2
            kb.dtype = bool
            return kb
        if isinstance(other,float) or isinstance(other,int):
            kb = KdataBase()
            kb._data = self.data < other
            kb.dtype = bool
            return kb     
        else: #int float
            return self.value < other


    # >
    def __gt__(self, other):
        if isinstance(other,KdataBase):  
            kb = KdataBase()
            d1,d2 = match_size(self.data,other.data)
            kb._data = d1 > d2
            kb.dtype = bool
            return kb
        if isinstance(other,float) or isinstance(other,int):
            kb = KdataBase()
            kb._data = self.data > other
            kb.dtype = bool
            return kb             
        else: #int float
            return self.value > other


    # ==
    def __eq__(self, other):
        if isinstance(other,KdataBase):  
            kb = KdataBase()
            d1,d2 = match_size(self.data,other.data)
            kb._data = d1 == d2
            kb.dtype = bool
            return kb
        if isinstance(other,float) or isinstance(other,int):
            kb = KdataBase()
            kb._data = self.data == other
            kb.dtype = bool
            return kb             
        else: #int float
            return self.value == other


    # !=
    def __ne__(self, other):
        if isinstance(other,KdataBase):  
            kb = KdataBase()
            d1,d2 = match_size(self.data,other.data)
            kb._data = d1 != d2
            kb.dtype = bool
            return kb
        if isinstance(other,float) or isinstance(other,int):
            kb = KdataBase()
            kb._data = self.data != other
            kb.dtype = bool
            return kb             
        else: #int float
            return self.value != other


    # >=
    def __ge__(self, other):
        if isinstance(other,KdataBase):  
            kb = KdataBase()
            d1,d2 = match_size(self.data,other.data)
            kb._data = d1 >= d2
            kb.dtype = bool
            return kb
        if isinstance(other,float) or isinstance(other,int):
            kb = KdataBase()
            kb._data = self.data >= other
            kb.dtype = bool
            return kb 
        else: #int float
            return self.value >= other


    # <= 
    def __le__(self, other):
        if isinstance(other,KdataBase):  
            kb = KdataBase()
            d1,d2 = match_size(self.data,other.data)
            kb._data = d1 <= d2
            kb.dtype = bool
            return kb
        if isinstance(other,float) or isinstance(other,int):
            kb = KdataBase()
            kb._data = self.data <= other
            kb.dtype = bool
            return kb             
        else: #int float
            return self.value <= other

       # +
    def __add__(self,other):
        if isinstance(other,KdataBase):  
            kb = KdataBase()
            d1,d2 = match_size(self.data,other.data)
            kb._data = d1 + d2
            return kb
        if isinstance(other,float) or isinstance(other,int):
            kb = KdataBase()
            kb._data = self.data + other
            return kb             
        else: #int float
            return self.value + other

    def __radd__(self, other):
        return self.__add__(other)
    # -
    def __sub__(self,other):
        if isinstance(other,KdataBase):  
            kb = KdataBase()
            d1,d2 = match_size(self.data,other.data)
            kb._data = d1 - d2
            return kb
        if isinstance(other,float) or isinstance(other,int):
            kb = KdataBase()
            kb._data = self.data - other
            return kb 
        else: #int float
            return self.value - other
    # -
    def __rsub__(self,other):
        if isinstance(other,KdataBase):
            kb = KdataBase()
            d1,d2 = match_size(self.data,other.data)
            kb._data = d2 - d1
            return kb
        # 100 - C 要走这里。之前写成 self - other，左右减反了。
        if isinstance(other,(float,int)) and not isinstance(other,bool):
            kb = KdataBase()
            kb._data = other - np.asarray(self.data)
            return kb
        return other - self.value

    # *
    def __mul__(self,other):
        if isinstance(other,KdataBase):  
            kb = KdataBase()
            d1,d2 = match_size(self.data,other.data)
            kb._data = d1 * d2
            return kb
        if isinstance(other,float) or isinstance(other,int):
            kb = KdataBase()
            kb._data = self.data * other
            return kb             
        else: #int float
            return round(self.value * other,3)

    def __rmul__(self, other):
        return self.__mul__(other)

    # / 
    def __truediv__(self, other):
        #s1 , s2 = match_size(self.data,other.data)
        if isinstance(other,KdataBase):  
            kb = KdataBase()
            d1,d2 = match_size(self.data,other.data)
            kb._data = d1 / d2
            return kb
        if isinstance(other,float) or isinstance(other,int):
            kb = KdataBase()
            kb._data = self.data / other
            return kb             
        else:
            return round(self.value / other,3)

    def __rtruediv__(self, other):
        if isinstance(other,KdataBase):
            kb = KdataBase()
            d1,d2 = match_size(self.data,other.data)
            kb._data = d2 / d1
            return kb
        # 100 / C 要走这里。之前写成 self / other，分子分母反了。
        if isinstance(other,(float,int)) and not isinstance(other,bool):
            kb = KdataBase()
            kb._data = other / np.asarray(self.data, dtype=float)
            return kb
        return round(other / self.value,3)


    __div__ = __truediv__
    __rdiv__ = __rtruediv__

    def __len__(self):
        return len(self.data)

    def __repr__(self):
        return str(self.value)


class Kdatas(KdataBase):
    def __init__(self,index=0):
        self._data        = []
        self.cur_code     = "00000" # 股票代码
        self.dfstart      = -1 #stock start date
        self.dfend        = -1 #stock end date
        self.index        = index     #C,C[1],C[2]
    
     #返回最后一天的数据
    @property
    def value(self):
        if len(self.data) <1:
            return None
        return self.dtype(_at(self.data, -1))

    #比较code 值的目的是切换股票的时候刷新
    @property
    def data(self):
        if len(self._data) == 0 or self.cur_code != kl.cur_code\
            or self.dfstart != kl.dfstart\
            or self.dfend   != kl.dfend:

            #reload
            self.dfstart  = kl.dfstart
            self.dfend    = kl.dfend
            self.cur_code = kl.cur_code

            d = getstockdata(self.name).astype(self.dtype)
            index = len(d) - self.index
            if index > 0:
                self._data = d[:index]
            else :
                self._data = []
        return self._data


class KWdatas(Kdatas):
    def get_week_stockdata(self,name):
        if isinstance(kl.week_df,pandas.core.frame.DataFrame):
            return kl.week_df[name]
        kl.get_week()
        return kl.week_df[name]
 
    @property
    def data(self):
        if len(self._data) == 0 or self.cur_code != kl.cur_code:

            self.cur_code = kl.cur_code

            d = self.get_week_stockdata(self.name).astype(self.dtype)
            index = len(d) - self.index
            if index > 0:
                self._data = d[:index]
            else :
                self._data = []
        return self._data

class KMdatas(Kdatas):
    def get_month_stockdata(self,name):
        if isinstance(kl.month_df,pandas.core.frame.DataFrame):
            return kl.month_df[name]
        kl.get_month()
        return kl.month_df[name]

    @property
    def data(self):
        if len(self._data) == 0 or self.cur_code != kl.cur_code:

            self.cur_code = kl.cur_code

            d = self.get_month_stockdata(self.name).astype(self.dtype)
            index = len(d) - self.index
            if index > 0:
                self._data = d[:index]
            else :
                self._data = []
        return self._data


     
# create open high low close volume datetime
# 建立全局的 o,O,OPEN,等关键词
for name in ["open", "high", "low", "close", "volume", 'vol','amount','datetime','turn']:
    dtype = float if name != "datetime" else np.str_
    cls = type("{}Kdatas".format(name.capitalize()), (Kdatas, ), {"name": name, "dtype": dtype})
    obj = cls()
    for var in [name[0], name[0].upper(), name.upper()]:
        globals()[var] = obj

for name in ["open", "high", "low", "close", "volume", 'vol','amount','datetime','turn']:
    dtype = float if name != "datetime" else np.str_
    cls = type("{}Kdatas".format(name.capitalize()), (KWdatas, ), {"name": name, "dtype": dtype})
    obj = cls()
    for var in ["w"+name[0], "W"+name[0].upper(), "W"+name.upper()]:
        globals()[var] = obj

for name in ["open", "high", "low", "close", "volume", 'vol','amount','datetime','turn']:
    dtype = float if name != "datetime" else np.str_
    cls = type("{}Kdatas".format(name.capitalize()), (KMdatas, ), {"name": name, "dtype": dtype})
    obj = cls()
    for var in ["m"+name[0], "M"+name[0].upper(), "M"+name.upper()]:
        globals()[var] = obj

