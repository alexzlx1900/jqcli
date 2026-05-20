# 克隆自聚宽文章：https://www.joinquant.com/post/72076
# 标题：非小市值的融合策略
# 作者：Ryan.mfu

import pandas as pd
import numpy as np
import math
import datetime
import calendar
from jqdata import *
from jqfactor import get_factor_values
from prettytable import PrettyTable
from sklearn.svm import SVR  # 保留原创业板策略中的引用

# ==========================================
# 核心系统模块：初始化与调度
# ==========================================

def initialize(context):
    # --- 系统与费率设置 (融合三个策略的设置) ---
    set_option("avoid_future_data", True)
    set_option("use_real_price", True)
    set_benchmark("000300.XSHG")
    
    # 股票滑点与费率 (合并红利与创业板的设置，取其一或兼容)
    set_slippage(PriceRelatedSlippage(0.001), type="stock")
    set_order_cost(OrderCost(open_tax=0, close_tax=0.001, open_commission=0.00025, close_commission=0.00025, close_today_commission=0, min_commission=5), type='stock')
    
    # 基金滑点与费率 (来自ETF轮动)
    set_slippage(PriceRelatedSlippage(0.0001), type="fund")
    set_order_cost(OrderCost(open_tax=0, close_tax=0, open_commission=0.00006, close_commission=0.00006, close_today_commission=0, min_commission=0), type="fund")
    
    log.set_level('order', 'error')
    log.set_level('history', 'error')
    log.set_level('system', 'error')
    
    # --- 1. 组合管理参数 ---
    g.strategy_names = ["红利增强", "创业板动量", "ETF轮动"]
    g.strat_alloc = {"红利增强": 0.4, "创业板动量": 0.3, "ETF轮动": 0.3} # 4:3:3配比
    g.stock_owner = {} # 格式: {stock_code: '策略名'}，用于持仓隔离
    
    # --- 2. 子策略1：红利指数增强参数 ---
    g.div_sell_list = []
    g.div_buy_df = [] # 原文这里初始化为[], 后续被重写为DataFrame
    g.div_target_num = [5, 3]
    g.div_high_limit_list = []
    g.div_hold_list = []

    # --- 3. 子策略2：创业板动量参数 ---
    g.gem_lookback_days = [3, 20, 200]
    g.gem_holdings_num = 5        
    g.gem_min_money = 5000        
    g.gem_stop_loss = 0.95        
    
    # --- 4. 子策略3：ETF动量轮动参数 ---
    g.etf_pool = []
    g.etf_lookback_days = 25               
    g.etf_holdings_num = 1                 
    g.etf_defensive_etf = "511880.XSHG"    
    g.etf_min_money = 5000                 
    g.etf_enable_profit_protection = True                      
    g.etf_profit_protection_lookback = 3                       
    g.etf_profit_protection_threshold = 0.05                    
    g.etf_profit_protection_check_times = ['11:00']            
    g.etf_loss = 0.97                      
    g.etf_min_score_threshold = 0          
    g.etf_max_score_threshold = 100.0      
    g.etf_enable_volume_check = True
    g.etf_volume_lookback = 5
    g.etf_volume_threshold = 2
    g.etf_volume_return_limit = 1          
    g.etf_use_short_momentum_filter = True
    g.etf_short_lookback_days = 10
    g.etf_short_momentum_threshold = 0.0
    g.etf_enable_premium_filter = True      
    g.etf_premium_threshold = 0.08          
    g.etf_rankings_cache = {'date': None, 'data': None}   
    g.etf_profit_protection_sold_today = []               

    # --- 5. 任务调度 (严格按照三个子策略的原时间要求) ---
    # 红利增强
    run_daily(div_prepare_stock_list, '09:15')
    run_monthly(div_get_stock_list, 1, '09:25')
    run_monthly(div_trade, 1 ,'09:32')
    run_daily(div_check_limit_up, '10:00')
    
    # 创业板动量
    run_weekly(gem_rebalance, -1, time='09:32')
    
    # ETF动量轮动
    run_daily(etf_check_positions, time='09:10') # 原代码记录持仓状态并清理今日卖出名单
    for check_time in g.etf_profit_protection_check_times:
        run_daily(etf_profit_protection_check, time=check_time)
    run_daily(etf_sell_trade, time='14:00')
    run_daily(etf_buy_trade, time='14:05')
    
    # 组合管理与盘后统计
    run_daily(quarterly_rebalance, time='14:30') # 季度最后一天14:30对齐资金
    run_daily(print_daily_summary, time='15:10') # 每日盘后日志


# ==========================================
# 子策略1：红利指数增强模块 (100% 还原)
# ==========================================

def div_prepare_stock_list(context):
    g.div_high_limit_list = []
    # 仅获取红利策略名下的持仓
    g.div_hold_list = [s for s, owner in g.stock_owner.items() if owner == "红利增强"]
    if len(g.div_hold_list) != 0:
        df = get_price(g.div_hold_list, end_date=context.previous_date, frequency='daily', fields=['close','high_limit'], count=1, panel=False, fill_paused=False, skip_paused=False).dropna()
        df = df[df['close'] == df['high_limit']]
        g.div_high_limit_list = list(df.code)

def div_get_stock_list(context):
    g.div_buy_df = pd.DataFrame(index=[], columns=[ 'name', 'price', 'amount', 'value'])
    yesterday = str(context.previous_date)
    today = context.current_dt
    
    initial_list = get_all_securities('stock', today).index.tolist()
    initial_list = filter_new_stock(context,initial_list)
    initial_list = filter_kcb_stock(initial_list)
    initial_list = filter_st_stock(initial_list)
    initial_list = filter_paused_stock(initial_list)
    
    # 红利低波
    stock_list = initial_list
    stock_list = get_dividend_ratio_filter_list(context, stock_list, False, 0.00, 0.10, 0.03) 
    stock_list = get_factor_filter_list(context, stock_list, 'beta', True, 0.00, 0.50) 
    HLDB_list = stock_list[:min(g.div_target_num[0], len(stock_list))]
    
    # 红利价值
    stock_list = initial_list
    df = get_fundamentals(query(
            valuation.code,
        ).filter(
            valuation.code.in_(stock_list),
            valuation.pe_ratio.between(5, 50), 
            indicator.inc_return.between(5, 100), 
            indicator.inc_total_revenue_year_on_year.between(5, 100), 
            indicator.inc_net_profit_year_on_year.between(10, 100), 
        ))
    stock_list = list(df.code)
    stock_list = get_dividend_ratio_filter_list(context, stock_list, False, 0.00, 0.10, 0.03) 
    HLJZ_list = stock_list[:min(g.div_target_num[1], len(stock_list))]

    target_list = list(set(HLDB_list).union(set(HLJZ_list)))
    g.div_sell_list = [s for s in g.div_hold_list if s not in target_list and s not in g.div_high_limit_list]
    buy_list = [s for s in target_list if s not in g.div_hold_list]
    
    # 资金管理：以组合分配比例计算该策略的总目标价值
    target_budget = context.portfolio.total_value * g.strat_alloc["红利增强"]
    
    if len(buy_list) > 0:
        # 每只股票分得的理论目标价值 = 红利策略总目标价值 / 目标股票总数
        value_per_stock = target_budget / len(target_list) if len(target_list) > 0 else 0
        
        df = get_price(buy_list, end_date=yesterday, frequency='1d', count=1, fields=['close'], fq='pre', panel=False, skip_paused=False, fill_paused=True).set_index('code')
        df['today_hl_price'] = [0]*len(df)
        for s in list(df.index):
            if ((s[0] == '3') and (str(context.current_dt)[:10] >= '2020-08-24')):
                df.loc[s, 'today_hl_price'] = round(df.loc[s,'close']*1.05, 2)
            else:
                df.loc[s, 'today_hl_price'] = round(df.loc[s,'close']*1.05, 2)
        g.div_buy_df['name'] = [get_security_info(s, yesterday).display_name for s in buy_list]
        g.div_buy_df['price'] = [df.loc[s,'today_hl_price'] for s in buy_list]
        # 严格使用原有的手数计算公式
        g.div_buy_df['amount'] = [100 * int(1.05 * value_per_stock / df.loc[s,'today_hl_price'] / 100) for s in buy_list]
        g.div_buy_df['value'] = g.div_buy_df['price'] * g.div_buy_df['amount']
        g.div_buy_df.index = buy_list    

    log.info('红利增强卖出清单: %s' % g.div_sell_list)
    log.info('红利增强买入清单:\n%s' % g.div_buy_df)


def div_trade(context):
    current_data = get_current_data()
    for s in g.div_sell_list:
        if current_data[s].last_price < current_data[s].high_limit:
            if order_target_value(s, 0) is not None:
                if s in g.stock_owner: del g.stock_owner[s]
    
    df = g.div_buy_df
    for s in list(df.index):
        if order(s, df.loc[s,'amount'], LimitOrderStyle(df.loc[s, 'price'])) is not None:
            g.stock_owner[s] = "红利增强"


def div_check_limit_up(context):
    current_data = get_current_data()
    if g.div_high_limit_list != []:
        for s in g.div_high_limit_list:
            if current_data[s].last_price < current_data[s].high_limit:
                if order_target_value(s, 0) is not None:
                    if s in g.stock_owner: del g.stock_owner[s]
                log.info(f"{s} 涨停打开，卖出")
            else:
                log.info(f"{s} 涨停，继续持有")

# 红利辅助过滤函数
def filter_paused_stock(stock_list):
    current_data = get_current_data()
    return [stock for stock in stock_list if not current_data[stock].paused]

def filter_st_stock(stock_list):
    current_data = get_current_data()
    return [stock for stock in stock_list if not current_data[stock].is_st and 'ST' not in current_data[stock].name and '*' not in current_data[stock].name and '退' not in current_data[stock].name]

def filter_kcb_stock(stock_list):
    return [stock for stock in stock_list  if ((stock[0] != '4') and (stock[0] != '8') and (stock[0:2] != '68'))]

def filter_new_stock(context, stock_list):
    yesterday = context.previous_date
    return [stock for stock in stock_list if not yesterday - get_security_info(stock).start_date < datetime.timedelta(days=250)]

def get_dividend_ratio_filter_list(context, stock_list, sort, p1, p2, threshold):
    time1 = context.previous_date
    time0 = time1 - datetime.timedelta(days=365)
    interval = 1000 
    list_len = len(stock_list)
    q = query(finance.STK_XR_XD.code, finance.STK_XR_XD.a_registration_date, finance.STK_XR_XD.bonus_amount_rmb
    ).filter(finance.STK_XR_XD.a_registration_date >= time0, finance.STK_XR_XD.a_registration_date <= time1, finance.STK_XR_XD.code.in_(stock_list[:min(list_len, interval)]))
    df = finance.run_query(q)
    if list_len > interval:
        df_num = list_len // interval
        for i in range(df_num):
            q = query(finance.STK_XR_XD.code, finance.STK_XR_XD.a_registration_date, finance.STK_XR_XD.bonus_amount_rmb
            ).filter(finance.STK_XR_XD.a_registration_date >= time0, finance.STK_XR_XD.a_registration_date <= time1, finance.STK_XR_XD.code.in_(stock_list[interval*(i+1):min(list_len,interval*(i+2))]))
            temp_df = finance.run_query(q)
            df = df.append(temp_df)
    dividend = df.fillna(0)
    dividend = dividend.set_index('code')
    dividend = dividend.groupby('code').sum()
    temp_list = list(dividend.index) 
    q = query(valuation.code,valuation.market_cap).filter(valuation.code.in_(temp_list))
    cap = get_fundamentals(q, date=time1)
    cap = cap.set_index('code')
    df = pd.concat([dividend, cap] ,axis=1, sort=False)
    df['dividend_ratio'] = (df['bonus_amount_rmb']/10000) / df['market_cap']
    df = df.sort_values(by=['dividend_ratio'], ascending=sort)
    df = df[int(p1*len(df)):int(p2*len(df))]
    df = df[df['dividend_ratio'] > threshold]
    return list(df.index)

def get_factor_filter_list(context, stock_list, jqfactor, sort, p1, p2):
    yesterday = context.previous_date
    score_list = get_factor_values(stock_list, jqfactor, end_date=yesterday, count=1)[jqfactor].iloc[0].tolist()
    df = pd.DataFrame(columns=['code','score'])
    df['code'] = stock_list
    df['score'] = score_list
    df = df.dropna()
    df.sort_values(by='score', ascending=sort, inplace=True)
    final_list = list(df.code)[int(p1*len(df)):int(p2*len(df))]
    return final_list


# ==========================================
# 子策略2：创业板动量模块 (100% 还原)
# ==========================================

def gem_calc_momentum_score(security, lookback):
    try:
        prices = attribute_history(security, lookback+10, '1d', ['close'], skip_paused=True, df=False)
        if len(prices['close']) < lookback: return 0
        price_series = prices['close'][-lookback-1:]
        if len(price_series) < lookback+1: return 0
        current_data = get_current_data()
        current_price = current_data[security].last_price
        if current_price is None or current_price <= 0: return 0
        
        price_series = np.append(price_series, current_price)
        y = np.log(price_series)
        x = np.arange(len(y))
        weights = np.linspace(1, 2, len(y))
        
        slope, intercept = np.polyfit(x, y, 1, w=weights)
        annualized_return = math.exp(slope * 250) - 1
        
        ss_res = np.sum(weights * (y - (slope * x + intercept))**2)
        ss_tot = np.sum(weights * (y - np.mean(y))**2)
        r_squared = 1 - ss_res/ss_tot if ss_tot != 0 else 0
        
        score = annualized_return * r_squared
        
        if len(price_series) >= 4:
            returns = price_series[-4:]/price_series[-5:-1] - 1
            if min(returns) < -0.03:
                score = score * 0.5
        
        return score if score > 0 else 0
    except Exception as e:
        log.warning(f"计算{security}得分出错: {e}")
        return 0

def gem_get_target_weights(context):
    current_date = context.previous_date
    stock_pool = list(set(get_index_stocks('399006.XSHE', current_date))) 
    scores = []
    for stock in stock_pool:
        score1 = gem_calc_momentum_score(stock, g.gem_lookback_days[1]) 
        score2 = gem_calc_momentum_score(stock, g.gem_lookback_days[2]) 
        if score1 <= 0 or score2 <= 0: continue
        score = score1 * score2* gem_calc_momentum_score(stock, g.gem_lookback_days[0]) 
        if score > 0:
            scores.append((stock, score))
    
    if len(scores) <= 0: return {}
    
    scores.sort(key=lambda x: x[1], reverse=True)
    top_stocks = [s[0] for s in scores[:g.gem_holdings_num]]
    weight = 1.0 / len(top_stocks)
    target = {stock: weight for stock in top_stocks}
    
    log.info(f"创业板动量今日得分前{g.gem_holdings_num}名: {[s[0] for s in scores[:g.gem_holdings_num]]}")
    return target

def gem_smart_order_target_value(context, security, target_value):
    current_data = get_current_data()
    if security not in current_data: 
        log.info("交易的标的不存在，交易失败") 
        return False
    if current_data[security].paused:
        log.info("交易的标的停牌，交易失败！") 
        return False
    
    price = current_data[security].last_price
    if price <= 0: 
        log.info("交易的标的价格负数，交易失败！") 
        return FalseFalse
    
    pos = context.portfolio.positions.get(security, None)
    current_amount = pos.total_amount if pos else 0
    
    target_amount = int(target_value / price)
    target_amount = (target_amount // 100) * 100
    if target_amount <= 0 and target_value > 0:
        target_amount = 100
    
    diff_amount = target_amount - current_amount
    if diff_amount == 0: return True
    
    #if abs(diff_amount) * price < g.gem_min_money: return False
    
    if diff_amount < 0:
        closeable = pos.closeable_amount if pos else 0
        if closeable <= 0: return False
        diff_amount = -min(abs(diff_amount), closeable)
    
    if security.startswith('688'):
        style = MarketOrderStyle(limit_price=price * 1.02)  
    else:
        style = MarketOrderStyle()
        
    order_result = order(security, diff_amount, style = style)
    if order_result:
        # 修改点：成功交易后，维护 stock_owner
        if target_value == 0:
            if security in g.stock_owner: del g.stock_owner[security]
        else:
            g.stock_owner[security] = "创业板动量"
        return True
    log.info("交易失败！")
    return False

def gem_rebalance(context):
    log.info("=== 创业板动量 开始调仓 ===")
    target_weights = gem_get_target_weights(context)
    
    # 资金管理：以组合分配比例计算该策略的总目标价值
    total_value = context.portfolio.total_value * g.strat_alloc["创业板动量"]
    
    # 卖出不在目标中的持仓（仅限该策略所属持仓）
    current_holdings = [s for s, owner in g.stock_owner.items() if owner == "创业板动量"]
    for sec in current_holdings:
        if len(target_weights) == 0 or sec not in target_weights:
            gem_smart_order_target_value(context, sec, 0)
            
    if len(target_weights) == 0: return
    
    # 买入/调整目标持仓
    for sec, weight in target_weights.items():
        target_value = total_value * weight
        gem_smart_order_target_value(context, sec, target_value)
    
    # 固定止损检查
    current_holdings_updated = [s for s, owner in g.stock_owner.items() if owner == "创业板动量"]
    for sec in current_holdings_updated:
        pos = context.portfolio.positions[sec]
        if pos.total_amount > 0:
            current_price = pos.price
            avg_cost = pos.avg_cost
            if current_price <= avg_cost * g.gem_stop_loss:
                log.info(f"触发创业板动量止损: {sec} 成本{avg_cost:.3f} 现价{current_price:.3f}")
                gem_smart_order_target_value(context, sec, 0)


# ==========================================
# 子策略3：ETF动量轮动模块 (100% 还原)
# ==========================================

def etf_profit_protection_check(context):
    if not g.etf_enable_profit_protection: return
    for sec in list(context.portfolio.positions.keys()):
        # 修改点：只检查归属于 ETF策略 的持仓
        if g.stock_owner.get(sec) != "ETF轮动": continue
        
        pos = context.portfolio.positions[sec]
        if pos.total_amount > 0:
            if etf_check_profit_protection(sec, context):
                if etf_smart_order_target_value(sec, 0, context):
                    log.info(f"盈利保护卖出: {sec} {etf_get_name(sec)}")
                    if sec not in g.etf_profit_protection_sold_today:
                        g.etf_profit_protection_sold_today.append(sec)

def etf_check_profit_protection(security, context, lookback=None, threshold=None):
    if not g.etf_enable_profit_protection: return False
    lookback = lookback or g.etf_profit_protection_lookback
    threshold = threshold or g.etf_profit_protection_threshold
    hist = attribute_history(security, lookback, '1d', ['high'])
    if hist.empty or len(hist) < lookback: return False
    max_high = hist['high'].max()
    current_price = get_current_data()[security].last_price
    if current_price <= max_high * (1 - threshold): return True
    else: return False

def etf_get_premium_rate(code, date, max_back_days=5):
    price_data = get_price(code, start_date=date, end_date=date, frequency='daily', fields=['close'])
    if price_data.empty: return None, None, None
    price = price_data['close'].iloc[0]

    net_value = None
    used_date = date
    start_date = date - datetime.timedelta(days=max_back_days*2)
    trade_days = get_trade_days(start_date=start_date, end_date=date)
    trade_days = [pd.to_datetime(d).date() for d in trade_days]
    
    for dt in reversed(trade_days):
        if dt > date: continue
        net_data = get_extras('unit_net_value', code, start_date=dt, end_date=dt, df=True)
        if not net_data.empty and not pd.isna(net_data[code].iloc[0]):
            net_value = net_data[code].iloc[0]
            used_date = dt
            break
        try:
            q = query(finance.FUND_NET_VALUE).filter(finance.FUND_NET_VALUE.code == code, finance.FUND_NET_VALUE.day == dt)
            net_df = finance.run_query(q)
            if not net_df.empty:
                net_value = net_df['net_value'].iloc[0]
                used_date = dt
                break
        except: continue

    if net_value is None: return None, None, None
    premium_rate = (price - net_value) / net_value
    return premium_rate, price, net_value

def etf_get_cached_rankings(context):
    today = context.current_dt.date()
    if g.etf_rankings_cache['date'] != today:
        ranked = etf_get_ranked_etfs(context)
        g.etf_rankings_cache = {'date': today, 'data': ranked}
    return g.etf_rankings_cache['data']

def etf_refresh_rankings_cache(context):
    today = context.current_dt.date()
    ranked = etf_get_ranked_etfs(context)
    g.etf_rankings_cache = {'date': today, 'data': ranked}
    return ranked

def etf_get_ranked_etfs(context):
    all_funds = get_all_securities(['fund'], date=context.current_dt)
    g.etf_pool = all_funds[
        (all_funds['display_name'].str.contains('能源', na=False)) |
        (all_funds['display_name'].str.contains('大宗', na=False)) |
        (all_funds['display_name'].str.contains('油', na=False)) |
        (all_funds['display_name'].str.contains('豆粕', na=False)) |
        (all_funds['display_name'].str.contains('黄金', na=False)) |
        (all_funds['display_name'].str.contains('白银', na=False)) |
        (all_funds['display_name'].str.contains('混合LOF', na=False)) |
        (all_funds['display_name'].str.contains('增强ETF', na=False)) |
        (all_funds['display_name'].str.contains('指数ETF', na=False)) |
        (all_funds['display_name'].str.contains('增强LOF ', na=False)) |
        (all_funds['display_name'].str.contains('质量ETF ', na=False)) |
        (all_funds['display_name'].str.contains('质量LOF ', na=False)) |
        (all_funds['display_name'].str.contains('指数LOF', na=False)) |
        (all_funds['display_name'].str.contains('0LOF', na=False)) |
        (all_funds['display_name'].str.contains('0ETF', na=False)) | 
        (all_funds['display_name'].str.contains('盘LOF ', na=False)) |
        (all_funds['display_name'].str.contains('盘ETF', na=False)) |
        (all_funds['display_name'].str.contains('板LOF ', na=False)) |
        (all_funds['display_name'].str.contains('板ETF', na=False)) |
        (all_funds['display_name'].str.contains('科创LOF ', na=False)) |
        (all_funds['display_name'].str.contains('科创ETF', na=False)) 
    ]    
    
    etf_metrics = []
    for etf in g.etf_pool.index:
        d = get_current_data()[etf]
        # 【新增优化1】：严格排除价格异常、退市或停牌的标的
        if d.paused or np.isnan(d.last_price) or d.last_price <= 0: 
            continue
            
        # 【新增优化2】：强流动性过滤，拉黑僵尸LOF
        # 门槛：近20个交易日日均成交额 > 100万元，且昨日有实际成交量
        hist_data = attribute_history(etf, 20, '1d', ['money', 'volume'])
        if hist_data.empty or hist_data['money'].mean() < 1000000 or hist_data['volume'].iloc[-1] <= 0:
            continue

        metrics = etf_calc_momentum_metrics(context, etf)
        if metrics is not None:
            if g.etf_min_score_threshold < metrics['score'] < g.etf_max_score_threshold:
                etf_metrics.append(metrics)
                
    etf_metrics.sort(key=lambda x: x['score'], reverse=True)
    return etf_metrics

def etf_calc_momentum_metrics(context, etf):
    try:
        name = etf_get_name(etf)
        lookback = max(g.etf_lookback_days, g.etf_short_lookback_days) + 20
        prices = attribute_history(etf, lookback, '1d', ['close', 'high'])
        if len(prices) < g.etf_lookback_days: return None

        current_price = get_current_data()[etf].last_price
        price_series = np.append(prices["close"].values, current_price)

        if etf_check_profit_protection(etf, context): return None

        if g.etf_enable_premium_filter:
            prev_date = get_trade_days(end_date=context.current_dt.date(), count=2)[0]
            premium, _, _ = etf_get_premium_rate(etf, prev_date)
            if premium is not None:
                if premium > g.etf_premium_threshold: return None

        if g.etf_enable_volume_check:
            vol_ratio = etf_get_volume_ratio(context, etf)
            if vol_ratio is not None:
                annualized = etf_get_annualized_returns(price_series, g.etf_lookback_days)
                if annualized > g.etf_volume_return_limit: return None

        if len(price_series) >= g.etf_short_lookback_days + 1:
            short_return = price_series[-1] / price_series[-(g.etf_short_lookback_days + 1)] - 1
        else:
            short_return = 0

        if g.etf_use_short_momentum_filter and short_return < g.etf_short_momentum_threshold: return None

        recent = price_series[-(g.etf_lookback_days + 1):]
        y = np.log(recent)
        x = np.arange(len(y))
        weights = np.linspace(1, 2, len(y))
        slope, intercept = np.polyfit(x, y, 1, w=weights)
        annualized_returns = math.exp(slope * 250) - 1

        ss_res = np.sum(weights * (y - (slope * x + intercept)) ** 2)
        ss_tot = np.sum(weights * (y - np.mean(y)) ** 2)
        r_squared = 1 - ss_res / ss_tot if ss_tot != 0 else 0

        score = annualized_returns * r_squared

        if len(price_series) >= 4:
            day1 = price_series[-1] / price_series[-2]
            day2 = price_series[-2] / price_series[-3]
            day3 = price_series[-3] / price_series[-4]
            if min(day1, day2, day3) < g.etf_loss: return None

        return {
            'etf': etf, 'etf_name': name, 'annualized_returns': annualized_returns,
            'r_squared': r_squared, 'score': score, 'current_price': current_price, 'short_return': short_return,
        }
    except Exception as e:
        log.warning(f"计算 {etf} {etf_get_name(etf)} 时出错: {e}")
        return None

def etf_get_annualized_returns(price_series, lookback_days):
    recent = price_series[-(lookback_days + 1):]
    y = np.log(recent)
    x = np.arange(len(y))
    weights = np.linspace(1, 2, len(y))
    slope, _ = np.polyfit(x, y, 1, w=weights)
    return math.exp(slope * 250) - 1

def etf_get_intraday_trading_progress(current_dt):
    current_minutes = current_dt.hour * 60 + current_dt.minute
    morning_start = 9 * 60 + 30
    morning_end = 11 * 60 + 30
    afternoon_start = 13 * 60
    afternoon_end = 15 * 60
    full_minutes = 240.0

    if current_minutes <= morning_start: elapsed = 0
    elif current_minutes <= morning_end: elapsed = current_minutes - morning_start
    elif current_minutes < afternoon_start: elapsed = 120
    elif current_minutes <= afternoon_end: elapsed = 120 + (current_minutes - afternoon_start)
    else: elapsed = 240
    progress = elapsed / full_minutes
    return min(max(progress, 0), 1)

def etf_get_volume_ratio(context, security, lookback=None, threshold=None):
    lookback = lookback or g.etf_volume_lookback
    threshold = threshold or g.etf_volume_threshold
    try:
        name = etf_get_name(security)
        hist = attribute_history(security, lookback, '1d', ['volume'])
        if hist.empty or len(hist) < lookback: return None
        avg_vol = hist['volume'].mean()

        today = context.current_dt.date()
        df_vol = get_price(security, start_date=today, end_date=context.current_dt, frequency='1m', fields=['volume'], skip_paused=False, fq='pre')
        if df_vol is None or df_vol.empty: return None
        current_vol = df_vol['volume'].sum()
        progress = etf_get_intraday_trading_progress(context.current_dt)
        if progress <= 0: return None
        normalized_current_vol = current_vol / progress
        ratio = normalized_current_vol / avg_vol if avg_vol > 0 else 0
        if ratio > threshold: return ratio
        return None
    except Exception as e: return None

def etf_check_positions(context):
    g.etf_profit_protection_sold_today = []

def etf_sell_trade(context):
    ranked = etf_get_cached_rankings(context)
    target_etfs = []
    for m in ranked[:g.etf_holdings_num]:
        if m['score'] >= g.etf_min_score_threshold:
            target_etfs.append(m['etf'])

    defensive_available = etf_check_defensive_available(context)
    if not target_etfs and defensive_available: target_etfs = [g.etf_defensive_etf]
    target_set = set(target_etfs)
    
    current_etf_holdings = [s for s, owner in g.stock_owner.items() if owner == "ETF轮动"]
    for sec in current_etf_holdings:
        if sec not in target_set:
            if etf_smart_order_target_value(sec, 0, context):
                log.info(f"卖出不在目标的持仓: {sec} {etf_get_name(sec)}")

def etf_buy_trade(context):
    """买入符合条件的 ETF (已增加容量预警与防卡死机制)"""
    log.info("========== 买入操作开始 ==========")

    ranked = etf_refresh_rankings_cache(context)
    log.info("=== ETF 排名前 5 ===")
    for i, m in enumerate(ranked[:5]):
        log.info(f"排名 {i+1}: {m['etf']} {m['etf_name']}, 得分 {m['score']:.4f}")

    # 【新增核心逻辑 1】：预先计算每只目标ETF计划分配的理论资金
    total_val = context.portfolio.total_value * g.strat_alloc["ETF轮动"]
    target_per_etf = total_val / g.etf_holdings_num

    target_etfs = []

    for m in ranked:
        if len(target_etfs) >= g.etf_holdings_num:
            break
        etf = m['etf']

        # 黑名单与盈利保护检查
        if etf_check_profit_protection(etf, context):
            continue
        if etf in g.etf_profit_protection_sold_today:
            continue

        # =====================================================================
        # 【新增核心逻辑 2：事前容量预测与防呆过滤】
        # 判断该基金是否有足够的流动性吃下我们的单子。如果我们的目标买入金额
        # 超过了该基金近5日日均成交额的 10%，则判定为“当日无法全部买入”。
        # 此时直接放弃该标的，进入下一个循环（转而买入排名下一个）。
        # =====================================================================
        hist_money = attribute_history(etf, 5, '1d', ['money'])
        if not hist_money.empty:
            avg_money = hist_money['money'].mean()
            # 如果日均成交额为0或预期买入资金超过日均成交额10%
            if avg_money <= 0 or target_per_etf > (avg_money * 0.1):
                log.warning(f"⛔ 容量预警拦截: {etf} {m['etf_name']} 计划买入 {target_per_etf/10000:.1f}万，超出其日均成交额({avg_money/10000:.1f}万)的10%安全线！已放弃并顺延至下一名。")
                continue
        else:
            continue # 获取不到数据说明存在异常，跳过

        target_etfs.append(etf)
        log.info(f"入选目标 ETF {len(target_etfs)}: {etf} {m['etf_name']}, 得分 {m['score']:.4f}")

    # 防御模式
    if not target_etfs:
        if etf_check_defensive_available(context):
            target_etfs = [g.etf_defensive_etf]
            log.info(f"进入防御模式: {target_etfs} {etf_get_name(target_etfs)}")
        else:
            log.info("无目标 ETF 且防御不可用, 保持空仓")
            return

    # 【新增核心逻辑 3：彻底解除阻塞死锁】
    # 检查是否有之前因跌停或流动性差而滞留的“僵尸持仓”
    current_etf_pos = [s for s, owner in g.stock_owner.items() if owner == "ETF轮动"]
    to_sell = [s for s in current_etf_pos if s not in target_etfs]
    if to_sell:
        log.warning(f"⚠️ ETF轮动存在未完全清仓的遗留标的: {[etf_get_name(s) for s in to_sell]}。强制跳过阻塞逻辑，利用剩余资金继续执行新目标买入！")

    # 执行实际买入
    for etf in target_etfs:
        current_val = 0
        if etf in context.portfolio.positions:
            pos = context.portfolio.positions[etf]
            if pos.total_amount > 0:
                # 兼容价格异常的情况，防止计算市值报错
                valid_price = pos.price if not np.isnan(pos.price) and pos.price > 0 else 0
                current_val = pos.total_amount * valid_price
                
        if abs(current_val - target_per_etf) > target_per_etf * 0.05 or current_val == 0:
            if etf_smart_order_target_value(etf, target_per_etf, context):
                action = "买入" if current_val < target_per_etf else "调仓"
                log.info(f"{action}: {etf} {etf_get_name(etf)}, 目标金额 {target_per_etf:.2f}")

    log.info("========== 买入操作完成 ==========")

def etf_get_name(security):
    try: return get_current_data()[security].name
    except: return "未知"

def etf_check_defensive_available(context):
    data = get_current_data()
    etf = g.etf_defensive_etf
    if data[etf].paused: return False
    if data[etf].last_price >= data[etf].high_limit: return False
    if data[etf].last_price <= data[etf].low_limit: return False
    return True

def etf_smart_order_target_value(security, target_value, context):
    data = get_current_data()
    name = etf_get_name(security)

    if data[security].paused: return False
    
    price = data[security].last_price
    # 安全校验：价格为空或为0拒绝下单
    if price is None or np.isnan(price) or price <= 0: 
        log.info("价格不正常，拒绝下单", price)
        return False

    target_amount = int(target_value / price)
    target_amount = (target_amount // 100) * 100
    if target_amount <= 0 and target_value > 0: target_amount = 100

    cur_pos = context.portfolio.positions.get(security, None)
    cur_amount = cur_pos.total_amount if cur_pos else 0
    diff = target_amount - cur_amount

    if diff > 0:
        if data[security].last_price >= data[security].high_limit: 
            log.info(f"{security} {name} 涨停, 跳过买入")
            return False
    elif diff < 0:
        if data[security].last_price <= data[security].low_limit: 
            log.info(f"{security} {name} 跌停, 跳过卖出")
            return False

    if diff < 0:
        closeable = cur_pos.closeable_amount if cur_pos else 0
        if closeable == 0: return False
        diff = -min(abs(diff), closeable)

    if diff != 0:
        order_result = order(security, diff)
        if order_result:
            if target_value == 0:
                # 【修改点】：确保仓位真实清零后，才删除策略归属标签
                if context.portfolio.positions[security].total_amount == 0:
                    if security in g.stock_owner: del g.stock_owner[security]
                else:
                    log.warning(f"⚠️ 卖单已下达但 {security} 未完全清仓，保留归属标签明日继续尝试卖出")
            else:
                g.stock_owner[security] = "ETF轮动"
            return True
    return False

# ==========================================
# 季度再平衡与日志打印
# ==========================================

def quarterly_rebalance(context):
    """每个季度最后一个交易日的14:30，将资金配比重新配平为4:3:3"""
    today = context.current_dt.date()
    # 判断是否为季末月份
    if today.month in [3, 6, 9, 12]:
        # 获取该月最后一天
        _, last_day = calendar.monthrange(today.year, today.month)
        month_end_date = datetime.date(today.year, today.month, last_day)
        # 获取截至该月最后一天的交易日历，取最后一个即为该月最后一个交易日
        trade_days = get_trade_days(end_date=month_end_date, count=30)
        last_trade_day = trade_days[-1]
        
        if today == last_trade_day:
            log.info(">>>> 触发季度资产再平衡 (配平回 4:3:3) <<<<")
            total_value = context.portfolio.total_value
            
            for strat_name, ratio in g.strat_alloc.items():
                target_strat_val = total_value * ratio
                strat_holdings = [s for s, owner in g.stock_owner.items() if owner == strat_name]
                
                # 计算该策略当前持仓总市值
                curr_strat_val = sum([context.portfolio.positions[s].value for s in strat_holdings])
                
                if curr_strat_val > 0:
                    # 将该策略内所有的股票按比例缩放
                    scale_ratio = target_strat_val / curr_strat_val
                    for s in strat_holdings:
                        target_s_val = context.portfolio.positions[s].value * scale_ratio
                        # 使用普通调仓单，忽略限价细节以确保快速配平
                        order_target_value(s, target_s_val)

def print_daily_summary(context):
    """15:10 表格打印持仓明细和盈亏汇总"""
    log.info("="*20 + " 每日账户汇总报告 (15:10) " + "="*20)
    total_val = context.portfolio.total_value
    total_pnl = total_val - context.portfolio.starting_cash
    
    summary_table = PrettyTable(['子策略', '理论目标额', '实有市值', '持仓盈亏', '持仓数量'])
    detail_table = PrettyTable(['策略', '代码', '名称', '现价', '市值', '盈亏额', '盈亏率%'])
    
    for strat_name, ratio in g.strat_alloc.items():
        strat_target_val = total_val * ratio
        strat_stocks = [s for s, owner in g.stock_owner.items() if owner == strat_name]
        
        strat_mkt_val = 0
        strat_pnl = 0
        
        for s in strat_stocks:
            pos = context.portfolio.positions[s]
            pnl = (pos.price - pos.avg_cost) * pos.total_amount
            pnl_pct = (pos.price / pos.avg_cost - 1) * 100 if pos.avg_cost > 0 else 0
            
            strat_mkt_val += pos.value
            strat_pnl += pnl
            
            try:
                sec_name = get_security_info(s).display_name
            except:
                sec_name = "未知"
                
            detail_table.add_row([strat_name, s, sec_name, round(pos.price, 3), round(pos.value, 2), round(pnl, 2), f"{pnl_pct:.2f}%"])
            
        summary_table.add_row([strat_name, round(strat_target_val, 2), round(strat_mkt_val, 2), round(strat_pnl, 2), len(strat_stocks)])

    print(summary_table)
    print("\n[子策略持仓明细]")
    print(detail_table)
    log.info(f"==> 账户总资产: {total_val:.2f} | 账户总盈亏: {total_pnl:.2f}")