#!/usr/bin/env python3
# MIS Daily Scanner — Layer 1 (Market Context) + Layer 2 (VCP Opportunity)
# 运行时间: 每日 15:35
# 输出: /Users/tx/Documents/kimi/YYYY-MM-DD/

import os
import sys
import json
import re
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# 本机装有系统级代理（127.0.0.1:7890），requests 会自动读取 macOS 系统代理。
# 东财接口经 Python/OpenSSL 访问（无论走代理还是直连）均被对端断连，
# 新浪/腾讯接口正常。统一补丁：清空环境代理 + 忽略系统代理，全程直连国内数据源。
for _proxy_var in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY",
                   "http_proxy", "https_proxy", "all_proxy"):
    os.environ.pop(_proxy_var, None)

import requests.utils as _requests_utils
_requests_utils.getproxies = lambda: {}

# ========== 参数配置 ==========
PARAMS = {
    "save_path": "/Users/tx/Documents/GitHub/daily_stock_analysis/reports/mis/",
    "market_cap_min": 50,
    "market_cap_max": 300,
    "min_change_pct": 6.0,
    "max_20d_range_pct": 35.0,      # 已放宽
    "volume_ma_period": 10,
    "volume_ratio_min": 1.3,         # 已放宽
    "max_last_pullback_pct": 12.0,   # 已放宽
    "lookback_high": 30,             # 已改为30日
}

# ========== 工具函数 ==========
def ensure_dir(path):
    os.makedirs(path, exist_ok=True)
    return path

def get_today_str():
    return datetime.now().strftime("%Y-%m-%d")

def get_yesterday_str():
    return (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

# ========== Layer 1: Market Context (Fallback to Sina API when EM fails) ==========
def _get_sina_spot_all():
    """使用新浪财经接口获取全市场 A 股实时数据"""
    import requests, json, time
    
    count_url = "http://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/Market_Center.getHQNodeStockCount?node=hs_a"
    r = requests.get(count_url, timeout=15)
    total = int(re.findall(r'\d+', r.text)[0])
    page_count = int(total / 80) + (1 if total % 80 else 0)
    print(f"  新浪接口: 全市场 {total} 只, 共 {page_count} 页")
    
    url = "http://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/Market_Center.getHQNodeData"
    all_data = []
    for page in range(1, page_count + 1):
        params = {
            "page": str(page), "num": "80", "sort": "symbol", "asc": "1",
            "node": "hs_a", "symbol": "", "_s_r_a": "auto"
        }
        try:
            r = requests.get(url, params=params, timeout=15)
            data = json.loads(r.text)
            if data:
                all_data.extend(data)
        except Exception as e:
            print(f"  第 {page} 页获取失败: {e}")
        if page % 10 == 0:
            print(f"  已获取 {page}/{page_count} 页 ({len(all_data)} 条)")
        time.sleep(0.2)
    
    df = pd.DataFrame(all_data)
    if df.empty:
        return df
    
    # 列名映射: 新浪 → 东方财富格式
    df = df.rename(columns={
        'code': '代码',
        'name': '名称',
        'trade': '最新价',
        'changepercent': '涨跌幅',
        'pricechange': '涨跌额',
        'volume': '成交量',
        'amount': '成交额',
        'high': '最高',
        'low': '最低',
        'open': '今开',
        'settlement': '昨收',
        'turnoverratio': '换手率',
        'per': '市盈率-动态',
        'pb': '市净率',
        'mktcap': '总市值',
        'nmc': '流通市值',
    })
    
    # 新浪单位: mktcap/nmc 是万元, amount 是元, volume 是手数
    # 转换为东方财富统一单位: 亿元
    df['总市值'] = pd.to_numeric(df['总市值'], errors='coerce') / 10000
    df['流通市值'] = pd.to_numeric(df['流通市值'], errors='coerce') / 10000
    df['成交额'] = pd.to_numeric(df['成交额'], errors='coerce')  # 元

    
    # 计算振幅
    df['最新价'] = pd.to_numeric(df['最新价'], errors='coerce')
    df['最高'] = pd.to_numeric(df['最高'], errors='coerce')
    df['最低'] = pd.to_numeric(df['最低'], errors='coerce')
    df['昨收'] = pd.to_numeric(df['昨收'], errors='coerce')
    df['振幅'] = ((df['最高'] - df['最低']) / df['昨收'] * 100).round(2)
    
    # 添加缺失列（统一用空值）
    df['所属行业'] = '—'
    df['量比'] = np.nan
    df['涨速'] = np.nan
    df['5分钟涨跌'] = np.nan
    df['60日涨跌幅'] = np.nan
    df['年初至今涨跌幅'] = np.nan
    
    # 数值转换
    for col in ['最新价', '涨跌幅', '涨跌额', '成交量', '成交额', '换手率', '市盈率-动态', '市净率', '总市值', '流通市值']:
        df[col] = pd.to_numeric(df[col], errors='coerce')
    
    return df

def layer1_market_analysis():
    """市场环境分析"""
    import akshare as ak
    import requests, re, json
    
    today = get_today_str()
    
    # 获取全市场数据（新浪为主源：东财接口经 Python/OpenSSL 在本机环境下必被断连，
    # 已实测走代理与直连均失败，curl 却正常，判断为 TLS 指纹被对端拦截）
    print(f"[{datetime.now()}] Layer 1: 获取市场数据...")
    spot = None
    try:
        spot = _get_sina_spot_all()
        print(f"  新浪接口: 获取 {len(spot)} 条数据")
    except Exception as e:
        print(f"  新浪接口失败: {e}")

    if spot is None or spot.empty:
        print(f"  回退到东方财富接口...")
        try:
            spot = ak.stock_zh_a_spot_em()
            print(f"  东方财富接口: 获取 {len(spot)} 条数据")
        except Exception as e:
            print(f"  东方财富接口也失败: {e}")
            return None
    
    if spot is None or spot.empty:
        return None
    
    # 类型转换
    spot['涨跌幅'] = pd.to_numeric(spot['涨跌幅'], errors='coerce')
    spot['成交额'] = pd.to_numeric(spot['成交额'], errors='coerce')
    spot['成交量'] = pd.to_numeric(spot['成交量'], errors='coerce')
    
    # 1. 市场广度
    up = len(spot[spot['涨跌幅'] > 0])
    down = len(spot[spot['涨跌幅'] < 0])
    flat = len(spot[spot['涨跌幅'] == 0])
    total = len(spot)
    
    # 2. 涨跌停统计
    limit_up = len(spot[spot['涨跌幅'] >= 9.9])
    limit_down = len(spot[spot['涨跌幅'] <= -9.9])
    strong_up = len(spot[spot['涨跌幅'] >= 5])
    strong_down = len(spot[spot['涨跌幅'] <= -5])
    
    # 3. 成交额
    total_amount = spot['成交额'].sum() / 1e8  # 亿
    
    # 4. 涨停股明细（用于看板块热点）
    zt_stocks = spot[spot['涨跌幅'] >= 9.9].sort_values('涨跌幅', ascending=False)
    zt_cols = [c for c in ['代码', '名称', '涨跌幅', '成交额', '所属行业'] if c in zt_stocks.columns]
    zt_list = zt_stocks[zt_cols].head(30)
    
    # 5. 跌幅榜前20（风险信号）
    dt_stocks = spot[spot['涨跌幅'] <= -5].sort_values('涨跌幅', ascending=True)
    dt_cols = [c for c in ['代码', '名称', '涨跌幅', '所属行业'] if c in dt_stocks.columns]
    dt_list = dt_stocks[dt_cols].head(20)
    
    # 6. 情绪周期判断（简化版）
    if limit_up > 100 and limit_down < 10:
        emotion = "高潮期 | 赚钱效应极强，注意次日分化"
    elif limit_up > 50 and limit_down < 20:
        emotion = "发酵期 | 板块轮动积极，可积极参与"
    elif limit_up > 20 and limit_down < 30:
        emotion = "启动期/分歧期 | 局部机会，控制仓位"
    elif limit_down > 30:
        emotion = "衰退期/冰点 | 空仓观望，等待企稳"
    else:
        emotion = "震荡期 | 无明确方向，减少操作"
    
    # 7. 市场总结
    market_summary = {
        '日期': today,
        '上涨家数': up,
        '下跌家数': down,
        '平盘家数': flat,
        '涨停家数': limit_up,
        '跌停家数': limit_down,
        '涨幅>5%': strong_up,
        '跌幅>5%': strong_down,
        '总成交额(亿)': round(total_amount, 2),
        '涨跌比': f"{up}:{down}",
        '情绪周期': emotion,
        'VCP策略建议': '空仓/观察' if limit_up > 150 or limit_down > 30 else '正常扫描'
    }
    
    return {
        'summary': pd.DataFrame([market_summary]),
        'zt_list': zt_list.reset_index(drop=True),
        'dt_list': dt_list.reset_index(drop=True),
        'raw_spot': spot
    }

# ========== Layer 2: VCP Scanner (保留原有逻辑) ==========
def get_stock_history(code):
    import akshare as ak
    try:
        prefix = 'sh' if code.startswith('6') else 'sz'
        symbol = f"{prefix}{code}"
        start = (datetime.now() - timedelta(days=90)).strftime('%Y%m%d')
        end = datetime.now().strftime('%Y%m%d')
        df = ak.stock_zh_a_hist_tx(symbol=symbol, start_date=start, end_date=end, adjust="qfq")
        if df is None or len(df) < 60:
            return None
        # 腾讯列名映射 → 东方财富格式
        df = df.rename(columns={
            'close': '收盘',
            'high': '最高',
            'low': '最低',
            'amount': '成交量',
        })
        for col in ['收盘', '最高', '最低', '成交量']:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        df.dropna(subset=['收盘', '最高', '最低', '成交量'], inplace=True)
        return df.reset_index(drop=True)
    except Exception as e:
        print(f"  获取 {code} 历史数据失败: {e}")
        return None

def calc_vcp_pullbacks(hist):
    recent = hist.tail(40).reset_index(drop=True)
    if len(recent) < 20:
        return [], False
    highs = recent['最高']
    lows = recent['最低']
    peaks = []
    for i in range(2, len(recent)-2):
        if (highs.iloc[i] > highs.iloc[i-1] and highs.iloc[i] > highs.iloc[i-2] and
            highs.iloc[i] > highs.iloc[i+1] and highs.iloc[i] > highs.iloc[i+2]):
            peak_price = highs.iloc[i]
            subsequent_low = lows.iloc[i:].min()
            pullback = (peak_price - subsequent_low) / peak_price * 100
            peaks.append((i, pullback, peak_price))
    peaks = sorted(peaks, key=lambda x: x[0], reverse=True)[:3]
    if len(peaks) < 3:
        return [], False
    pullbacks = [p[1] for p in peaks]
    is_decreasing = pullbacks[0] > pullbacks[1] > pullbacks[2]
    return pullbacks, is_decreasing

def check_second_wave(hist):
    if len(hist) < 30:
        return False
    prev_20 = hist.iloc[-21:-1].reset_index(drop=True)
    if len(prev_20) < 10:
        return False
    prev_20['ma10_vol'] = prev_20['成交量'].rolling(10).mean()
    for i in range(10, len(prev_20)):
        day = prev_20.iloc[i]
        prev = prev_20.iloc[i-1]
        change = (day['收盘'] - prev['收盘']) / prev['收盘'] * 100
        if change < 6:
            continue
        recent_high = prev_20['最高'].iloc[max(0, i-19):i].max()
        if day['最高'] <= recent_high:
            continue
        ma10 = prev_20['ma10_vol'].iloc[i]
        if pd.isna(ma10) or ma10 == 0:
            continue
        ratio = day['成交量'] / ma10
        if ratio >= 1.5:
            return True
    return False

def analyze_vcp(code, name, market_cap):
    hist = get_stock_history(code)
    if hist is None or len(hist) < 60:
        return None
    
    recent = hist.tail(25).reset_index(drop=True)
    recent_20 = recent.tail(20)
    price_range = (recent_20['最高'].max() - recent_20['最低'].min()) / recent_20['收盘'].mean() * 100
    if price_range >= PARAMS['max_20d_range_pct']:
        return None
    
    lookback = PARAMS['lookback_high']
    today_high = recent['最高'].iloc[-1]
    prev_high = recent['最高'].iloc[-(lookback+1):-1].max()
    if today_high <= prev_high:
        return None
    
    today_close = recent['收盘'].iloc[-1]
    prev_close = recent['收盘'].iloc[-2]
    change_pct = (today_close - prev_close) / prev_close * 100
    if change_pct < PARAMS['min_change_pct']:
        return None
    
    recent['ma10_vol'] = recent['成交量'].rolling(PARAMS['volume_ma_period']).mean()
    today_vol = recent['成交量'].iloc[-1]
    ma10_vol = recent['ma10_vol'].iloc[-1]
    if pd.isna(ma10_vol) or ma10_vol == 0:
        return None
    vol_ratio = today_vol / ma10_vol
    if vol_ratio < PARAMS['volume_ratio_min']:
        return None
    
    pullbacks, is_decreasing = calc_vcp_pullbacks(hist)
    if len(pullbacks) < 3:
        return None
    if not is_decreasing:
        return None
    if pullbacks[0] >= PARAMS['max_last_pullback_pct']:
        return None
    
    if check_second_wave(hist):
        return None
    
    return {
        '代码': code, '名称': name, '流通市值(亿)': round(market_cap, 2),
        '收盘价': round(today_close, 2), '涨跌幅(%)': round(change_pct, 2),
        '20日振幅(%)': round(price_range, 2), '30日新高': '是',
        '量比(对MA10)': round(vol_ratio, 2),
        'VCP回调幅度(3次)': [round(p, 2) for p in pullbacks],
        '候选级别': '核心' if pullbacks[0] < 7 else '观察',
    }

def layer2_vcp_scan(spot):
    """VCP扫描"""
    print(f"[{datetime.now()}] Layer 2: VCP扫描...")
    
    df = spot.copy()
    df['流通市值'] = pd.to_numeric(df['流通市值'], errors='coerce')
    df['涨跌幅'] = pd.to_numeric(df['涨跌幅'], errors='coerce')
    
    df = df[~df['名称'].str.contains('ST|退', na=False, regex=False)]
    df = df[~df['代码'].str.startswith('68', na=False)]
    df = df[~df['代码'].str.startswith('8', na=False)]
    df = df[~df['代码'].str.startswith('4', na=False)]
    df = df[~df['代码'].str.startswith('9', na=False)]
    df = df[(df['流通市值'] >= PARAMS['market_cap_min']) & 
            (df['流通市值'] <= PARAMS['market_cap_max'])]
    df = df[df['涨跌幅'] >= PARAMS['min_change_pct']]
    
    print(f"基础过滤: {len(df)} 只")
    
    results = []
    for idx, row in df.iterrows():
        result = analyze_vcp(row['代码'], row['名称'], row['流通市值'])
        if result:
            results.append(result)
            print(f"  ✓ {result['代码']} {result['名称']} | 涨{result['涨跌幅(%)']}% | 回调{result['VCP回调幅度(3次)'][0]}%")
    
    return pd.DataFrame(results) if results else pd.DataFrame()

# ========== 主流程 ==========
def main():
    today_str = get_today_str()
    save_dir = ensure_dir(os.path.join(PARAMS['save_path'], today_str))
    
    print(f"\n{'='*60}")
    print(f"MIS Daily Run — {today_str}")
    print(f"{'='*60}")
    
    # Layer 1
    market_data = layer1_market_analysis()
    if market_data is None:
        print("Layer 1 获取失败，终止")
        return
    
    # 保存 Layer 1
    with pd.ExcelWriter(os.path.join(save_dir, "market_layer1.xlsx")) as writer:
        market_data['summary'].to_excel(writer, sheet_name='市场概览', index=False)
        market_data['zt_list'].to_excel(writer, sheet_name='涨停股明细', index=False)
        market_data['dt_list'].to_excel(writer, sheet_name='跌幅榜前20', index=False)
    
    print(f"\nLayer 1 完成: {save_dir}/market_layer1.xlsx")
    print(f"  涨停: {market_data['summary']['涨停家数'].values[0]} | 跌停: {market_data['summary']['跌停家数'].values[0]}")
    print(f"  情绪: {market_data['summary']['情绪周期'].values[0]}")
    
    # Layer 2
    vcp_df = layer2_vcp_scan(market_data['raw_spot'])
    
    if len(vcp_df) == 0:
        empty = pd.DataFrame({'日期': [today_str], '备注': ['今日无符合VCP突破的候选']})
        empty.to_excel(os.path.join(save_dir, "vcp_breakout.xlsx"), index=False)
        print(f"\nLayer 2 完成: 今日无 VCP 候选")
    else:
        vcp_df = vcp_df.sort_values('量比(对MA10)', ascending=False).reset_index(drop=True)
        vcp_df.to_excel(os.path.join(save_dir, "vcp_breakout.xlsx"), index=False)
        print(f"\nLayer 2 完成: 找到 {len(vcp_df)} 只 VCP 候选")
    
    print(f"\n{'='*60}")
    print(f"全部完成。输出目录: {save_dir}")
    print(f"{'='*60}")

if __name__ == "__main__":
    main()
