# 克隆自聚宽文章：https://www.joinquant.com/post/68653
# 标题：强势科创板小市值v1.2严格风控 + 低回撤交易系统
# 作者：zptzz

# 导入函数库
from jqdata import *
from jqfactor import *
import numpy as np
import pandas as pd
from datetime import time, datetime, timedelta


STAR_MARKET_PREFIX = '68'
STAR_MARKET_INDEX = '000688.XSHG'
LIMIT_PRICE_BUFFER = 0.01
SELL_LIMIT_PRICE_RATIO = 0.98
BUY_LIMIT_PRICE_RATIO = 1.02


# 初始化函数
def initialize(context):
    set_option('avoid_future_data', True)
    set_benchmark('000001.XSHG')
    set_option('use_real_price', True)
    set_slippage(FixedSlippage(3 / 10000))
    set_order_cost(
        OrderCost(
            open_tax=0,
            close_tax=0.001,
            open_commission=2.5 / 10000,
            close_commission=2.5 / 10000,
            close_today_commission=0,
            min_commission=5,
        ),
        type='stock',
    )

    log.set_level('order', 'error')
    log.set_level('system', 'error')
    log.set_level('strategy', 'debug')

    init_global_state()
    init_strategy_params()
    schedule_jobs()


def init_global_state():
    g.no_trading_today_signal = False
    g.pass_april = False
    g.run_stoploss = True
    g.hold_list = []
    g.yesterday_HL_list = []
    g.target_list = []
    g.need_rebuy = False
    g.sell_price_record = {}


def init_strategy_params():
    g.stock_num = 5
    g.stoploss_strategy = 3
    g.stoploss_limit = 0.88
    g.stoploss_market = 0.94
    g.take_profit_ratio = 1.20
    g.buy_fall_ratio = 0.90
    g.HV_control = False


def schedule_jobs():
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
    g.hold_list = position_codes(context)
    g.yesterday_HL_list = []

    if not g.hold_list:
        return

    g.yesterday_HL_list = get_yesterday_limit_up_codes(context, g.hold_list)
    g.no_trading_today_signal = today_is_between(context)


def get_yesterday_limit_up_codes(context, stock_list):
    yesterday_date = context.current_dt.date() - timedelta(days=1)
    price_data = get_price(
        stock_list,
        frequency='daily',
        fields=['close', 'high_limit'],
        end_date=yesterday_date,
        count=1,
        panel=False,
    )

    df = normalize_price_frame(price_data, stock_list)
    if df.empty:
        return []

    limit_up_codes = []
    for code, group in df.groupby('code'):
        close = group['close'].iloc[0]
        high_limit = group['high_limit'].iloc[0]
        if abs(close - high_limit) < LIMIT_PRICE_BUFFER:
            limit_up_codes.append(code)
    return limit_up_codes


def normalize_price_frame(price_data, stock_list):
    if isinstance(price_data, pd.DataFrame):
        df = price_data.reset_index()
    else:
        df = price_data.to_frame().reset_index()

    if 'code' not in df.columns and 'minor' in df.columns:
        df.rename(columns={'minor': 'code'}, inplace=True)
    if 'code' not in df.columns and len(stock_list) == 1:
        df['code'] = stock_list[0]
    return df


# ==============================
# 选股：科创板小市值 + 过滤黑名单（跌够10%才放行）
# ==============================
def get_stock_list(context):
    initial_list = get_star_market_small_cap_codes()
    if not initial_list:
        return []

    initial_list = apply_stock_filters(context, initial_list)
    final_list = apply_rebuy_price_filter(initial_list)

    stock_list = final_list[:100]
    return stock_list[:2 * g.stock_num]


def get_star_market_small_cap_codes():
    q = query(valuation.code).filter(
        valuation.code.like('68%')
    ).order_by(valuation.market_cap.asc())
    df = get_fundamentals(q)
    if df.empty:
        return []
    return df['code'].tolist()


def apply_stock_filters(context, stock_list):
    stock_list = filter_new_stock(context, stock_list)
    stock_list = filter_st_stock(stock_list)
    stock_list = filter_paused_stock(stock_list)
    stock_list = filter_limitup_stock(context, stock_list)
    stock_list = filter_limitdown_stock(context, stock_list)
    return stock_list


def apply_rebuy_price_filter(stock_list):
    final_list = []
    current_data = get_current_data()
    for stock in stock_list:
        if stock not in g.sell_price_record:
            final_list.append(stock)
            continue

        sell_price = g.sell_price_record[stock]
        now_price = current_data[stock].last_price
        if now_price <= sell_price * g.buy_fall_ratio:
            final_list.append(stock)
            del g.sell_price_record[stock]
            log.info(f"【解禁】{stock} 已跌够10%，允许买入")
    return final_list


# ==============================
# 10:00 卖出（止盈20% + 止损）→ 记录卖出价（修复未来函数）
# ==============================
def sell_stocks(context):
    if not g.run_stoploss or g.no_trading_today_signal:
        return

    market_drop = is_market_stoploss_triggered()
    sold_any = False
    current_data = get_current_data()

    for stock in list(context.portfolio.positions.keys()):
        pos = context.portfolio.positions[stock]
        last_price = current_data[stock].last_price

        if last_price >= pos.avg_cost * g.take_profit_ratio:
            log.info(f"【止盈20%】卖出 {stock}")
            if sell_and_record(context, stock, last_price):
                sold_any = True
            continue

        if market_drop:
            log.info(f"【市场止损】卖出 {stock}")
            if sell_and_record(context, stock, last_price):
                sold_any = True
            continue

        if last_price < pos.avg_cost * g.stoploss_limit:
            log.info(f"【个股止损】卖出 {stock}")
            if sell_and_record(context, stock, last_price):
                sold_any = True
            continue

    if sold_any:
        g.need_rebuy = True
        log.info(f"卖出记录：{g.sell_price_record}")


def is_market_stoploss_triggered():
    if g.stoploss_strategy not in (2, 3):
        return False

    idx_data = get_current_data()[STAR_MARKET_INDEX]
    idx_open = idx_data.day_open
    idx_current = idx_data.last_price
    return idx_current / idx_open <= g.stoploss_market


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

    current_data = get_current_data()
    submitted_sell_count = 0
    for stock in g.hold_list:
        if stock not in target_list and stock not in g.yesterday_HL_list:
            log.info(f"【调仓卖出】{stock}")
            if sell_and_record(context, stock, current_data[stock].last_price):
                submitted_sell_count += 1

    available_slots = max(0, g.stock_num - len(context.portfolio.positions) + submitted_sell_count)
    buy_list = [s for s in target_list if s not in context.portfolio.positions][:available_slots]
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

        last_price = current_data[stock].last_price
        high_limit = current_data[stock].high_limit
        if last_price < high_limit - LIMIT_PRICE_BUFFER:
            log.info(f"【破板卖出】{stock}")
            sell_and_record(context, stock, last_price)


def trade_afternoon(context):
    if g.no_trading_today_signal:
        return
    check_limit_up(context)


# ==============================
# 过滤函数
# ==============================
def filter_paused_stock(stock_list):
    cur = get_current_data()
    return [s for s in stock_list if not cur[s].paused]


def filter_st_stock(stock_list):
    cur = get_current_data()
    return [s for s in stock_list if not cur[s].is_st]


def filter_limitup_stock(context, stock_list):
    cur = get_current_data()
    return [
        s for s in stock_list
        if (s in context.portfolio.positions) or (cur[s].last_price < cur[s].high_limit - LIMIT_PRICE_BUFFER)
    ]


def filter_limitdown_stock(context, stock_list):
    cur = get_current_data()
    return [
        s for s in stock_list
        if (s in context.portfolio.positions) or (cur[s].last_price > cur[s].low_limit + LIMIT_PRICE_BUFFER)
    ]


def filter_new_stock(context, stock_list):
    out = []
    for stock in stock_list:
        try:
            start_date = get_security_info(stock).start_date
            days = (context.current_dt.date() - start_date).days
            if days > 375:
                out.append(stock)
        except:
            continue
    return out


# ==============================
# 交易函数
# ==============================
def close_position(context, stock):
    if stock not in context.portfolio.positions:
        return False

    cur = get_current_data()[stock]
    if cur.paused:
        log.info(f"【停牌跳过卖出】{stock} 今日停牌，延后处理")
        return False

    if is_star_market_stock(stock):
        order_target_value(stock, 0, LimitOrderStyle(cur.last_price * SELL_LIMIT_PRICE_RATIO))
    else:
        order_target_value(stock, 0)
    return True


def buy_security(context, target_list):
    to_buy = [s for s in target_list if s not in context.portfolio.positions]
    if not to_buy:
        return

    cash = context.portfolio.cash
    per = cash / len(to_buy)
    cur = get_current_data()
    for stock in to_buy:
        if is_star_market_stock(stock):
            order_target_value(stock, per, LimitOrderStyle(cur[stock].last_price * BUY_LIMIT_PRICE_RATIO))
        else:
            order_target_value(stock, per)
        log.info(f"买入 {stock}")


def sell_and_record(context, stock, price):
    if not close_position(context, stock):
        return False
    g.sell_price_record[stock] = price
    return True


def is_star_market_stock(stock):
    return stock.startswith(STAR_MARKET_PREFIX)


def position_codes(context):
    return [p.security for p in context.portfolio.positions.values()]


# ==============================
# 空仓 & 打印
# ==============================
def today_is_between(context):
    if not g.pass_april:
        return False
    return context.current_dt.month in (1, 4)


def close_account(context):
    if g.no_trading_today_signal:
        current_data = get_current_data()
        for stock in list(context.portfolio.positions.keys()):
            sell_and_record(context, stock, current_data[stock].last_price)


def print_position_info(context):
    log.info("=== 持仓信息 ===")
    log.info(f"总资产：{context.portfolio.total_value:.2f}")
    log.info(f"限制买入（需跌10%）：{g.sell_price_record}")
