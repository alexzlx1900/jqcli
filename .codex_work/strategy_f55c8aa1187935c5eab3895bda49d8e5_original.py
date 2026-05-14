# 克隆自聚宽文章：https://www.joinquant.com/post/68653
# 标题：强势科创板小市值v1.2严格风控 + 低回撤交易系统
# 作者：zptzz

# 导入函数库
from jqdata import *
from jqfactor import *
import numpy as np
import pandas as pd
from datetime import time, datetime, timedelta

# 初始化函数 
def initialize(context):
    # 基础设置
    set_option('avoid_future_data', True)
    set_benchmark('000001.XSHG')
    set_option('use_real_price', True)
    set_slippage(FixedSlippage(3/10000))
    set_order_cost(OrderCost(open_tax=0, close_tax=0.001, 
                            open_commission=2.5/10000, close_commission=2.5/10000, 
                            close_today_commission=0, min_commission=5), type='stock')
    log.set_level('order', 'error')
    log.set_level('system', 'error')
    log.set_level('strategy', 'debug')

    # 全局变量
    g.no_trading_today_signal = False
    g.pass_april = False
    g.run_stoploss = True
    g.hold_list = []
    g.yesterday_HL_list = []  # 真正的昨日涨停列表（无未来）
    g.target_list = []
    g.need_rebuy = False

    # 【核心新增】记录每只股票的卖出价
    g.sell_price_record = {}  # key: code, value: 卖出价

    # 策略参数
    g.stock_num = 5
    g.stoploss_strategy = 3
    g.stoploss_limit = 0.88    # -12%止损
    g.stoploss_market = 0.94   # 指数-6%清仓（改为用开盘价对比）
    g.take_profit_ratio = 1.20 # 盈利≥20%止盈
    g.buy_fall_ratio = 0.90    # 比卖出价跌10%才能买回

    g.HV_control = False

    # 定时任务
    run_daily(prepare_stock_list, '9:05')
    run_daily(sell_stocks, '10:00')
    run_daily(rebuy_after_sell, '10:30')
    run_weekly(weekly_adjustment, 1, '10:30')
    run_daily(trade_afternoon, '14:30')
    run_daily(close_account, '14:50')
    run_weekly(print_position_info, 5, '15:10')

# ==============================
# 9:05 准备股票池（修复未来函数）
# ==============================
def prepare_stock_list(context):
    g.hold_list = [p.security for p in context.portfolio.positions.values()]
    g.yesterday_HL_list = []

    if not g.hold_list:
        return
    
    # 修复核心：明确取【真正的昨日】数据（用end_date限定）
    # 获取当前日期的前一天（交易日）
    yesterday_date = context.current_dt.date() - timedelta(days=1)
    # 确保取到的是昨日已收盘的日线数据
    price_panel = get_price(
        g.hold_list, 
        frequency='daily', 
        fields=['close','high_limit'], 
        end_date=yesterday_date,  # 关键：限定结束日期为昨日
        count=1,  # 只取1天（昨日）
        panel=True
    )
    
    df = price_panel.to_frame().reset_index()
    df.rename(columns={'minor':'code'}, inplace=True)
    if df.empty:
        return
    
    # 遍历判断昨日是否涨停
    for code, group in df.groupby('code'):
        close = group['close'].iloc[0]
        high_limit = group['high_limit'].iloc[0]
        if abs(close - high_limit) < 0.01:  # 涨停判断
            g.yesterday_HL_list.append(code)

    g.no_trading_today_signal = today_is_between(context)

# ==============================
# 选股：科创板小市值 + 过滤黑名单（跌够10%才放行）
# ==============================
def get_stock_list(context):
    q = query(valuation.code).filter(
        valuation.code.like('68%')
    ).order_by(valuation.market_cap.asc())
    df = get_fundamentals(q)
    if df.empty:
        return []
    initial_list = df['code'].tolist()

    initial_list = filter_new_stock(context, initial_list)
    initial_list = filter_st_stock(initial_list)
    initial_list = filter_paused_stock(initial_list)
    initial_list = filter_limitup_stock(context, initial_list)
    initial_list = filter_limitdown_stock(context, initial_list)

    # 【关键过滤：跌够10%才能买】
    final_list = []
    current_data = get_current_data()
    for stock in initial_list:
        # 没卖过 → 直接放行
        if stock not in g.sell_price_record:
            final_list.append(stock)
            continue
        
        # 卖过 → 必须当前价 ≤ 卖出价 * 0.9
        sell_price = g.sell_price_record[stock]
        now_price = current_data[stock].last_price
        
        if now_price <= sell_price * g.buy_fall_ratio:
            final_list.append(stock)
            # 满足条件后清除记录，下次不再限制
            del g.sell_price_record[stock]
            log.info(f"【解禁】{stock} 已跌够10%，允许买入")

    stock_list = final_list[:100]
    final_list = stock_list[:2 * g.stock_num]
    return final_list

# ==============================
# 10:00 卖出（止盈20% + 止损）→ 记录卖出价（修复未来函数）
# ==============================
def sell_stocks(context):
    if not g.run_stoploss or g.no_trading_today_signal:
        return

    market_drop = False
    if g.stoploss_strategy in (2, 3):
        # 修复：用指数【当日开盘价】和【当前价】对比（无未来）
        idx_data = get_current_data()['000688.XSHG']
        idx_open = idx_data.day_open  # 当日开盘价（已确定，无未来）
        idx_current = idx_data.last_price  # 实时价格（无未来）
        if idx_current / idx_open <= g.stoploss_market:
            market_drop = True

    sold_any = False
    current_data = get_current_data()

    for stock in list(context.portfolio.positions.keys()):
        pos = context.portfolio.positions[stock]
        last_price = current_data[stock].last_price

        # 止盈 ≥20% 卖出（用成本价对比当前价，无未来）
        if last_price >= pos.avg_cost * g.take_profit_ratio:
            log.info(f"【止盈20%】卖出 {stock}")
            close_position(context, stock)
            # 记录卖出价
            g.sell_price_record[stock] = last_price
            sold_any = True
            continue

        # 市场止损
        if market_drop:
            log.info(f"【市场止损】卖出 {stock}")
            close_position(context, stock)
            g.sell_price_record[stock] = last_price
            sold_any = True
            continue

        # 个股止损
        if last_price < pos.avg_cost * g.stoploss_limit:
            log.info(f"【个股止损】卖出 {stock}")
            close_position(context, stock)
            g.sell_price_record[stock] = last_price
            sold_any = True
            continue

    if sold_any:
        g.need_rebuy = True
        log.info(f"卖出记录：{g.sell_price_record}")

# ==============================
# 10:30 补仓（只买符合条件的）
# ==============================
def rebuy_after_sell(context):
    if g.no_trading_today_signal:
        return
    if not g.need_rebuy:
        return

    log.info("=== 10:30 补仓买入（需跌10%）===")
    g.target_list = get_stock_list(context)
    current_count = len(context.portfolio.positions)
    need_buy_count = g.stock_num - current_count

    if need_buy_count > 0 and len(g.target_list) > 0:
        candidates = [s for s in g.target_list if s not in context.portfolio.positions]
        buy_list = candidates[:need_buy_count]
        buy_security(context, buy_list)

    g.need_rebuy = False

# ==============================
# 每周一调仓
# ==============================
def weekly_adjustment(context):
    if g.no_trading_today_signal:
        return

    g.target_list = get_stock_list(context)
    target_list = g.target_list[:g.stock_num]
    if not target_list:
        return

    # 卖出不在目标里的
    current_data = get_current_data()
    for stock in g.hold_list:
        if stock not in target_list and stock not in g.yesterday_HL_list:
            log.info(f"【调仓卖出】{stock}")
            close_position(context, stock)
            # 记录卖出价
            g.sell_price_record[stock] = current_data[stock].last_price

    # 买入
    buy_list = [s for s in target_list if s not in context.portfolio.positions]
    buy_security(context, buy_list)

# ==============================
# 14:30 破板卖出
# ==============================
def check_limit_up(context):
    if not g.yesterday_HL_list:
        return
    current_data = get_current_data()
    for stock in g.yesterday_HL_list:
        if stock not in context.portfolio.positions:
            continue
        last = current_data[stock].last_price
        high_limit = current_data[stock].high_limit
        if last < high_limit - 0.01:
            log.info(f"【破板卖出】{stock}")
            close_position(context, stock)
            g.sell_price_record[stock] = last

def trade_afternoon(context):
    if g.no_trading_today_signal:
        return
    check_limit_up(context)

# ==============================
# 过滤函数
# ==============================
def filter_paused_stock(lst):
    cur = get_current_data()
    return [s for s in lst if not cur[s].paused]

def filter_st_stock(lst):
    cur = get_current_data()
    return [s for s in lst if not cur[s].is_st]

def filter_limitup_stock(context, lst):
    cur = get_current_data()
    return [s for s in lst if (s in context.portfolio.positions) or (cur[s].last_price < cur[s].high_limit - 0.01)]

def filter_limitdown_stock(context, lst):
    cur = get_current_data()
    return [s for s in lst if (s in context.portfolio.positions) or (cur[s].last_price > cur[s].low_limit + 0.01)]

def filter_new_stock(context, lst):
    out = []
    for s in lst:
        try:
            start_date = get_security_info(s).start_date
            days = (context.current_dt.date() - start_date).days
            if days > 375:
                out.append(s)
        except:
            continue
    return out

# ==============================
# 交易函数
# ==============================
def close_position(context, stock):
    if stock not in context.portfolio.positions:
        return
    cur = get_current_data()[stock]
    if stock.startswith('68'):
        order_target_value(stock, 0, LimitOrderStyle(cur.last_price * 0.98))
    else:
        order_target_value(stock, 0)

def buy_security(context, target_list):
    to_buy = [s for s in target_list if s not in context.portfolio.positions]
    if not to_buy:
        return
    cash = context.portfolio.cash
    per = cash / len(to_buy)
    cur = get_current_data()
    for s in to_buy:
        if s.startswith('68'):
            order_target_value(s, per, LimitOrderStyle(cur[s].last_price * 1.02))
        else:
            order_target_value(s, per)
        log.info(f"买入 {s}")

# ==============================
# 空仓 & 打印
# ==============================
def today_is_between(context):
    if not g.pass_april:
        return False
    return context.current_dt.month in (1,4)

def close_account(context):
    if g.no_trading_today_signal:
        current_data = get_current_data()
        for s in list(context.portfolio.positions.keys()):
            close_position(context, s)
            g.sell_price_record[s] = current_data[s].last_price

def print_position_info(context):
    log.info("=== 持仓信息 ===")
    log.info(f"总资产：{context.portfolio.total_value:.2f}")
    log.info(f"限制买入（需跌10%）：{g.sell_price_record}")