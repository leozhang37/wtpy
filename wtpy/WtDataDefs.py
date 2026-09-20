from wtpy.WtCoreDefs import WTSBarStruct, WTSOrdDtlStruct, WTSOrdQueStruct, WTSTickStruct, WTSTransStruct
import numpy as np
import pandas as pd

import numpy as np
from ctypes import POINTER, addressof

from wtpy.WtCoreDefs import WTSBarStruct, WTSTickStruct

NpTypeBar = np.dtype([('date','u4'),('reserve','u4'),('time','u8'),('open','d'),\
                ('high','d'),('low','d'),('close','d'),('settle','d'),\
                ('turnover','d'),('volume','d'),('open_interest','d'),('diff','d')])

'''
K线时间戳的三种编码, 取值和 WTSBarStruct.to_tuple 的 flag 参数一致
    分钟线: (date-19900000)*10000 + HHMM, 转成可读时间戳要加 199000000000
    日线:   直接用 date
    秒线:   yyyyMMddHHmmss, 本身就是可读的, 不能再加偏移
'''
PERIOD_FLAG_MIN = 0
PERIOD_FLAG_DAY = 1
PERIOD_FLAG_SEC = 2

def period_to_flag(period:str) -> int:
    '''
    根据周期字符串推导时间戳编码标记
    @period 周期, 如 m1/m5/d1/s5/s15
    '''
    if period is None or len(period) == 0:
        return PERIOD_FLAG_MIN

    c = period[0]
    if c == 'd':
        return PERIOD_FLAG_DAY
    elif c == 's':
        return PERIOD_FLAG_SEC

    return PERIOD_FLAG_MIN

NpTypeTick = np.dtype([('exchg','S16'),('code','S32'),('price','d'),('open','d'),('high','d'),('low','d'),('settle_price','d'),\
                ('upper_limit','d'),('lower_limit','d'),('total_volume','d'),('volume','d'),('total_turnover','d'),('turn_over','d'),\
                ('open_interest','d'),('diff_interest','d'),('trading_date','u4'),('action_date','u4'),('action_time','u4'),\
                ('reserve','u4'),('pre_close','d'),('pre_settle','d'),('pre_interest','d'),\
                ('bid_price_0','d'),('bid_price_1','d'),('bid_price_2','d'),('bid_price_3','d'),('bid_price_4','d'),\
                ('bid_price_5','d'),('bid_price_6','d'),('bid_price_7','d'),('bid_price_8','d'),('bid_price_9','d'),\
                ('ask_price_0','d'),('ask_price_1','d'),('ask_price_2','d'),('ask_price_3','d'),('ask_price_4','d'),\
                ('ask_price_5','d'),('ask_price_6','d'),('ask_price_7','d'),('ask_price_8','d'),('ask_price_9','d'),\
                ('bid_qty_0','d'),('bid_qty_1','d'),('bid_qty_2','d'),('bid_qty_3','d'),('bid_qty_4','d'),\
                ('bid_qty_5','d'),('bid_qty_6','d'),('bid_qty_7','d'),('bid_qty_8','d'),('bid_qty_9','d'),\
                ('ask_qty_0','d'),('ask_qty_1','d'),('ask_qty_2','d'),('ask_qty_3','d'),('ask_qty_4','d'),\
                ('ask_qty_5','d'),('ask_qty_6','d'),('ask_qty_7','d'),('ask_qty_8','d'),('ask_qty_9','d')])

NpTypeTrans = np.dtype([('exchg','S16'),('code','S32'),('trading_date','u4'),('action_date','u4'),('action_time','u4'),\
                ('reserve1','u4'),('index','u8'),('ttype','i4'),('side','i4'),('price','d'),('volume','u4'),('reserve2','u4'),\
                ('askorder', 'i8'),('bidorder', 'i8')])

NpTypeOrdQue = np.dtype([('exchg','S16'),('code','S32'),('trading_date','u4'),('action_date','u4'),('action_time','u4'),\
                ('side','u4'),('price','d'),('order_items','u4'),('qsize', 'i8'),('volumes','u4', 50)])

NpTypeOrdDtl = np.dtype([('exchg','S16'),('code','S32'),('trading_date','u4'),('action_date','u4'),('action_time','u4'),\
                ('reserve1','u4'),('index','u8'),('price','d'),('volume','u4'),('side','u4'),('otype','u4'),('reserve2','u4')])

class WtNpKline:
    '''
    基于numpy.ndarray的K线数据容器
    提供一些常用的属性和方法
    '''
    __type__:np.dtype = NpTypeBar
    def __init__(self, isDay:bool = False, forceCopy:bool = False, periodFlag:int = None):
        '''
        基于numpy.ndarray的K线数据容器
        @isDay      是否是日线数据, 主要用于控制bartimes的生成机制
        @forceCopy  是否强制拷贝, 如果为True, 则会拷贝一份数据, 否则会直接引用内存中的数据
                    强制拷贝主要用于WtDtHelper的read_dsb_bars和read_dmb_bars接口, 因为这两个接口返回的数据是临时的, 调用结束就会释放
        @periodFlag 时间戳编码标记, 见 PERIOD_FLAG_*。
                    秒线的时间戳是 yyyyMMddHHmmss, 和分钟线的
                    (date-19900000)*10000+HHMM 差5个数量级, 只靠 isDay
                    这个布尔量表达不了, 所以单独加了这个标记。
                    不传则按 isDay 推导, 保持原有调用方的行为不变
        '''
        self.__data__:np.ndarray = None
        self.__isDay__:bool = isDay
        if periodFlag is None:
            periodFlag = PERIOD_FLAG_DAY if isDay else PERIOD_FLAG_MIN
        self.__period_flag__:int = periodFlag
        self.__force_copy__:bool = forceCopy
        self.__bartimes__:np.ndarray = None
        self.__df__:pd.DataFrame = None

    def __len__(self):
        if self.__data__ is None:
            return 0
        
        return len(self.__data__)
    
    def __getitem__(self, index:int):
        if self.__data__ is None:
            raise IndexError("No data in WtNpKline")
        
        return self.__data__[index]

    def set_day_flag(self, isDay:bool):
        if self.__isDay__ != isDay:
            self.__isDay__ = isDay
            #日线标记变了, 编码标记要跟着走
            self.__period_flag__ = PERIOD_FLAG_DAY if isDay else PERIOD_FLAG_MIN
            self.__bartimes__ = None
            self.__df__ = None

    def set_period_flag(self, periodFlag:int):
        '''
        设置时间戳编码标记, 见 PERIOD_FLAG_*
        '''
        if self.__period_flag__ != periodFlag:
            self.__period_flag__ = periodFlag
            self.__isDay__ = (periodFlag == PERIOD_FLAG_DAY)
            self.__bartimes__ = None
            self.__df__ = None

    def set_data(self, firstBar, count:int):
        BarList = WTSBarStruct*count
        if self.__force_copy__:
            c_array = BarList.from_buffer_copy(BarList.from_address(addressof(firstBar.contents)))
        else:
            c_array = BarList.from_buffer(BarList.from_address(addressof(firstBar.contents)))
        npAy = np.frombuffer(c_array, dtype=self.__type__, count=count)

        # 这里有点不高效，需要拼接的地方，主要是WtDtServo的场景，这里慢点没关系
        if self.__data__ is not None:
            self.__data__ = np.concatenate((self.__data__, npAy))
            self.__data__.flags.writeable = self.__force_copy__
        else:
            self.__data__ = npAy
            self.__data__.flags.writeable = False

    @property
    def ndarray(self) -> np.ndarray:
        return self.__data__
    
    @property
    def opens(self) -> np.ndarray:
        return self.__data__["open"]

    @property
    def highs(self) -> np.ndarray:
        return self.__data__["high"]

    @property
    def lows(self) -> np.ndarray:
        return self.__data__["low"]

    @property
    def closes(self) -> np.ndarray:
        return self.__data__["close"]

    @property
    def volumes(self) -> np.ndarray:
        return self.__data__["volume"]

    @property
    def bartimes(self) -> np.ndarray:
        '''
        这里应该会构造一个副本, 可以暂存一个
        '''
        if self.__bartimes__ is None:
            if self.__period_flag__ == PERIOD_FLAG_DAY:
                self.__bartimes__ = self.__data__["date"]
            elif self.__period_flag__ == PERIOD_FLAG_SEC:
                '''
                秒线的时间戳已经是 yyyyMMddHHmmss, 直接用。
                如果误加了199000000000, 得到的是一个毫无意义的大数
                '''
                self.__bartimes__ = self.__data__["time"]
            else:
                self.__bartimes__ = self.__data__["time"] + 199000000000
        return self.__bartimes__
    
    def get_bar(self, iLoc:int = -1) -> tuple:
        return self.__data__[iLoc]
    
    @property
    def is_day(self) -> bool:
        return self.__isDay__

    @property
    def period_flag(self) -> int:
        '''
        时间戳编码标记, 见 PERIOD_FLAG_*
        '''
        return self.__period_flag__
    
    def to_df(self) -> pd.DataFrame:
        if self.__df__ is None:
            self.__df__ = pd.DataFrame(self.__data__, index=self.bartimes)
            self.__df__.drop(columns=["time", "reserve"], inplace=True)
            self.__df__["bartime"] = self.__df__.index
        return self.__df__
    
class WtNpTicks:
    '''
    基于numpy.ndarray的tick数据容器
    提供一些常用的属性和方法
    '''
    __type__:np.dtype = NpTypeTick
    def __init__(self, forceCopy:bool = False):
        '''
        基于numpy.ndarray的tick数据容器
        @forceCopy  是否强制拷贝, 如果为True, 则会拷贝一份数据, 否则会直接引用内存中的数据
                    强制拷贝主要用于WtDtHelper的read_dsb_ticks和read_dmb_ticks接口, 因为这两个接口返回的数据是临时的, 调用结束就会释放
        '''
        self.__data__:np.ndarray = None
        self.__times__:np.ndarray = None
        self.__force_copy__:bool = forceCopy
        self.__df__:pd.DataFrame = None

    def __len__(self):
        if self.__data__ is None:
            return 0
        
        return len(self.__data__)
    
    def __getitem__(self, index:int):
        if self.__data__ is None:
            raise IndexError("No data in WtNpTicks")
        
        return self.__data__[index]

    def set_data(self, firstTick, count:int):
        BarList = WTSTickStruct*count
        if self.__force_copy__:
            c_array = BarList.from_buffer_copy(BarList.from_address(addressof(firstTick.contents)))
        else:
            c_array = BarList.from_buffer(BarList.from_address(addressof(firstTick.contents)))

        npAy = np.frombuffer(c_array, dtype=self.__type__, count=count)
        # 这里有点不高效，需要拼接的地方主要是WtDtServo的场景，这里慢点没关系
        # 一旦触发拼接逻辑，都会拷贝一次
        if self.__data__ is not None:
            self.__data__ = np.concatenate((self.__data__, npAy))
            self.__data__.flags.writeable = self.__force_copy__
        else:
            self.__data__ = npAy
            self.__data__.flags.writeable = False

    @property
    def times(self) -> np.ndarray:
        '''
        这里应该会构造一个副本, 可以暂存一个
        '''
        if self.__times__ is None:
            self.__times__ = np.uint64(self.__data__["action_date"])*1000000000 + self.__data__["action_time"]
        return self.__times__


    def to_df(self) -> pd.DataFrame:
        if self.__df__ is None:
            self.__df__ = pd.DataFrame(self.__data__, index=self.times)
            self.__df__.drop(columns=["reserve"], inplace=True)
            self.__df__["time"] = self.__df__.index
        return self.__df__

    @property
    def ndarray(self) -> np.ndarray:
        return self.__data__
    
class WtNpTransactions:
    '''
    基于numpy.ndarray的逐笔成交数据容器
    提供一些常用的属性和方法
    '''
    __type__:np.dtype = NpTypeTrans
    def __init__(self, forceCopy:bool = False):
        '''
        基于numpy.ndarray的逐笔成交数据容器
        @forceCopy  是否强制拷贝, 如果为True, 则会拷贝一份数据, 否则会直接引用内存中的数据
                    强制拷贝主要用于WtDtHelper的read_dsb_trans和read_dmb_trans接口, 因为这两个接口返回的数据是临时的, 调用结束就会释放
        '''
        self.__data__:np.ndarray = None
        self.__force_copy__:bool = forceCopy

    def __len__(self):
        if self.__data__ is None:
            return 0
        
        return len(self.__data__)
    
    def __getitem__(self, index:int):
        if self.__data__ is None:
            raise IndexError("No data in WtNpTransactions")
        
        return self.__data__[index]

    def set_data(self, firstItem, count:int):
        DataList = WTSTransStruct*count
        if self.__force_copy__:
            c_array = DataList.from_buffer_copy(DataList.from_address(addressof(firstItem.contents)))
        else:
            c_array = DataList.from_buffer(DataList.from_address(addressof(firstItem.contents)))
        
        npAy = np.frombuffer(c_array, dtype=self.__type__, count=count)
        # 这里有点不高效，需要拼接的地方主要是WtDtServo的场景，这里慢点没关系
        # 一旦触发拼接逻辑，都会拷贝一次
        if self.__data__ is not None:
            self.__data__ = np.concatenate((self.__data__, npAy))
            self.__data__.flags.writeable = self.__force_copy__
        else:
            self.__data__ = npAy
            self.__data__.flags.writeable = False

    @property
    def ndarray(self) -> np.ndarray:
        return self.__data__
    
class WtNpOrdDetails:
    '''
    基于numpy.ndarray的逐笔委托数据容器
    提供一些常用的属性和方法
    '''
    __type__:np.dtype = NpTypeOrdDtl
    def __init__(self, forceCopy:bool = False):
        '''
        基于numpy.ndarray的逐笔委托数据容器
        @forceCopy  是否强制拷贝, 如果为True, 则会拷贝一份数据, 否则会直接引用内存中的数据
                    强制拷贝主要用于WtDtHelper的read_dsb_trans和read_dmb_trans接口, 因为这两个接口返回的数据是临时的, 调用结束就会释放
        '''
        self.__data__:np.ndarray = None
        self.__force_copy__:bool = forceCopy

    def __len__(self):
        if self.__data__ is None:
            return 0
        
        return len(self.__data__)
    
    def __getitem__(self, index:int):
        if self.__data__ is None:
            raise IndexError("No data in WtNpOrdDetails")
        
        return self.__data__[index]

    def set_data(self, firstItem, count:int):
        DataList = WTSOrdDtlStruct*count
        if self.__force_copy__:
            c_array = DataList.from_buffer_copy(DataList.from_address(addressof(firstItem.contents)))
        else:
            c_array = DataList.from_buffer(DataList.from_address(addressof(firstItem.contents)))

        npAy = np.frombuffer(c_array, dtype=self.__type__, count=count)
        # 这里有点不高效，需要拼接的地方主要是WtDtServo的场景，这里慢点没关系
        # 一旦触发拼接逻辑，都会拷贝一次
        if self.__data__ is not None:
            self.__data__ = np.concatenate((self.__data__, npAy))
            self.__data__.flags.writeable = self.__force_copy__
        else:
            self.__data__ = npAy
            self.__data__.flags.writeable = False

    @property
    def ndarray(self) -> np.ndarray:
        return self.__data__
    
class WtNpOrdQueues:
    '''
    基于numpy.ndarray的委托队列数据容器
    提供一些常用的属性和方法
    '''
    __type__:np.dtype = NpTypeOrdQue
    def __init__(self, forceCopy:bool = False):
        '''
        基于numpy.ndarray的委托队列数据容器
        @forceCopy  是否强制拷贝, 如果为True, 则会拷贝一份数据, 否则会直接引用内存中的数据
                    强制拷贝主要用于WtDtHelper的read_dsb_trans和read_dmb_trans接口, 因为这两个接口返回的数据是临时的, 调用结束就会释放
        '''
        self.__data__:np.ndarray = None
        self.__force_copy__:bool = forceCopy

    def __len__(self):
        if self.__data__ is None:
            return 0
        
        return len(self.__data__)
    
    def __getitem__(self, index:int):
        if self.__data__ is None:
            raise IndexError("No data in WtNpOrdQueues")
        
        return self.__data__[index]

    def set_data(self, firstItem, count:int):
        DataList = WTSOrdQueStruct*count
        if self.__force_copy__:
            c_array = DataList.from_buffer_copy(DataList.from_address(addressof(firstItem.contents)))
        else:
            c_array = DataList.from_buffer(DataList.from_address(addressof(firstItem.contents)))

        npAy = np.frombuffer(c_array, dtype=self.__type__, count=count)
        # 这里有点不高效，需要拼接的地方主要是WtDtServo的场景，这里慢点没关系
        # 一旦触发拼接逻辑，都会拷贝一次
        if self.__data__ is not None:
            self.__data__ = np.concatenate((self.__data__, npAy))
            self.__data__.flags.writeable = self.__force_copy__
        else:
            self.__data__ = npAy
            self.__data__.flags.writeable = False

    @property
    def ndarray(self) -> np.ndarray:
        return self.__data__
    
class WtBarCache:
    def __init__(self, isDay:bool = False, forceCopy:bool = False, periodFlag:int = None):
        '''
        @periodFlag 时间戳编码标记, 见 PERIOD_FLAG_*, 不传则按 isDay 推导
        '''
        self.records:WtNpKline = None
        self.__is_day__ = isDay
        self.__period_flag__ = periodFlag
        self.__force_copy__ = forceCopy
        self.__total_count__ = 0

    def on_read_bar(self, firstItem:POINTER(WTSBarStruct), count:int, isLast:bool):
        if self.records is None:
            self.records = WtNpKline(isDay=self.__is_day__, forceCopy=self.__force_copy__,
                                     periodFlag=self.__period_flag__)

        # 多次set_data，会在内部自动concatenate
        self.records.set_data(firstItem, count)

    def on_data_count(self, count:int):
        # 其实这里最好的处理方式是能够直接将底层的内存块拷贝，拼接成一块大的内存块
        # 但是暂时没想好怎么处理，所以只能多次set_data了，会损失一些性能，但是比以前快
        self.__total_count__ = count
        pass

class WtTickCache:
    def __init__(self, forceCopy:bool = False):
        self.records:WtNpTicks = None
        self.__force_copy__ = forceCopy
        self.__total_count__ = 0

    def on_read_tick(self, firstItem:POINTER(WTSTickStruct), count:int, isLast:bool):
        if self.records is None:
            self.records = WtNpTicks(forceCopy=self.__force_copy__)

        # 多次set_data，会在内部自动concatenate
        self.records.set_data(firstItem, count)

    def on_data_count(self, count:int):
        # 其实这里最好的处理方式是能够直接将底层的内存块拷贝，拼接成一块大的内存块
        # 但是暂时没想好怎么处理，所以只能多次set_data了，会损失一些性能，但是比以前快
        self.__total_count__ = count
        pass