import pandas as pd
import numpy as np
import utils
import os


def add_features_trajectories(df):
    '''
    add features on trajectories data
    '''
    df = df.copy()
    # x east y north
    print("warning not using track_unwrapped")
    gsx = df.groundspeed * np.sin(df.track)
    gsy = df.groundspeed * np.cos(df.track)
    # groundspeed = airspeed + wind
    # u east v north
    tasx = gsx - df.u_component_of_wind
    tasy = gsy - df.v_component_of_wind
    tas = np.hypot(tasx,tasy)
    # energy_rate = df.vertical_rate
    return df.assign(
        gsx = gsx,
        gsy = gsy,
        tasx = tasx,
        tasy = tasy,
        tas = tas,
        wind = np.hypot(df.u_component_of_wind,df.v_component_of_wind)
    )

def applytransfo(df,lfactors,inverse=False):
    '''
    used to factorize code
    '''
    ldf = list(df)
    for factor,lvar in lfactors:
        for v in lvar:
            if v in ldf:
                df[v] = df[v] * (1 / factor if inverse else factor)
    return df

TO_SI = (
        (np.pi/180,["longitude", "latitude", "track", "track_unwrapped"]),
        (utils.FEET2METER, ["altitude"]),
        (utils.FEET2METER / 60, ["vertical_rate"]),
        (utils.KTS2MS, ["groundspeed","gsx","gsy","tasx","tasy","tas"]),
)

def convert_to_SI(df):
    df = df.copy()
    return applytransfo(df, TO_SI)


def convert_from_SI(df):
    df = df.copy()
    return applytransfo(df, TO_SI, inverse=True)



def read_trajectories(f):
    ''' read and convert trajectories to SI units
    '''
    df = pd.read_parquet(f)
    for v in ["flight_id", "icao24"]:
        df[v] = df[v].astype(np.int64)
    df = convert_to_SI(df)
    return df#add_features_trajectories(df)


def add_features_flight(df):
    """
    为航班数据添加时间特征
    
    功能：从现有的时间列中提取有用的时间特征，便于数据分析
    
    参数：
    df: 包含航班数据的DataFrame
    
    返回：
    添加了新时间特征列的DataFrame
    
    内存使用说明：
    - assign() 会创建新DataFrame，短时间内内存使用约为原数据的2倍
    - 如果内存紧张，可以使用就地修改的方式（见下面的替代实现）
    """
    # 方式1：使用 assign()（当前实现）
    # 优点：函数式编程，不修改原数据，更安全
    # 缺点：会临时占用约2倍内存
    return df.assign(
        # 从实际离港时间提取星期几 (1=周一, 2=周二, ..., 7=周日)
        # isocalendar()：ISO 8601标准的日历系统
        dayofweek = df.actual_offblock_time.dt.isocalendar().day,
        
        # 从实际离港时间提取一年中的第几周 (1-53)
        weekofyear = df.actual_offblock_time.dt.isocalendar().week,
        
        # 将到达时间转换为当天的第几分钟 (0-1439)
        # 例如：14:30 = 14*60+30 = 870分钟
        arrival_minutes = df.arrival_time.dt.hour*60+df.arrival_time.dt.minute,
        
        # 将实际离港时间转换为当天的第几分钟 (0-1439)
        # 例如：08:15 = 8*60+15 = 495分钟
        actual_offblock_minutes = df.actual_offblock_time.dt.hour*60+df.actual_offblock_time.dt.minute,
        )

    # 方式2：就地修改（内存友好的替代方案）
    # 如果内存是瓶颈，可以使用这种方式：
    """
    # 复制DataFrame以避免修改原始数据
    result_df = df.copy()
    
    # 直接在复制的DataFrame上添加新列（就地修改）
    result_df['dayofweek'] = result_df.actual_offblock_time.dt.isocalendar().day
    result_df['weekofyear'] = result_df.actual_offblock_time.dt.isocalendar().week
    result_df['arrival_minutes'] = result_df.arrival_time.dt.hour*60+result_df.arrival_time.dt.minute
    result_df['actual_offblock_minutes'] = result_df.actual_offblock_time.dt.hour*60+result_df.actual_offblock_time.dt.minute
    
    return result_df
    """

def read_flights(f):
    '''
    从parquet文件读取航班数据
    '''
    # 定义需要转换为日期时间类型的列
    dates = ["date","actual_offblock_time","arrival_time"]
    
    # 定义数据类型转换规则：(目标类型, [列名列表])
    ltypes = [
        ("string", ["adep","ades"]),  # 出发地和目的地机场代码
        ("string", ["callsign","airline"]),  # 航班呼号和航空公司
        ("string",["wtc"]),  # 飞机尾流类别
        ("string",["country_code_ades","country_code_adep","name_ades","name_adep"]),  # 国家代码和机场名称
        ("string",["aircraft_type"]),  # 飞机类型
        (np.float64, ["flight_duration","taxiout_time","flown_distance","tow"]),  # 浮点数类型
        (np.int64, ["flight_id"]),  # 整数类型
        ("datetime64[ns, UTC]", dates),  # 日期时间类型
    ]
    
    # 读取parquet文件
    df = pd.read_parquet(f)
    
    # 批量转换数据类型
    # 这里使用双重循环来应用上面定义的类型转换规则
    for dtype, lvar in ltypes:  # 遍历每个(数据类型, 列名列表)对
        for v in lvar:  # 遍历该类型对应的所有列名
            df[v] = df[v].astype(dtype)  # 将列转换为指定类型
    
    # 添加时间特征并返回
    return add_features_flight(df)

