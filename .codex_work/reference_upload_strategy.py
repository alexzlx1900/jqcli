from jqdata import *
from jqfactor import *
import numpy as np
import pandas as pd
import pickle
import datetime
import lightgbm as lgb
import xgboost as xgb

# 上传选股结果 upload_stock_selections(g.strategy_name, target_list)
# 上传持仓明细 update_positions(g.strategy_name, context)
# from jq_trader_api_test import *
from jq_trader_api import *
g.strategy_name = "中小板-LGB-XGB集成策略"
order = push_order(order, g.strategy_name)
order_target = push_order_target(order_target, g.strategy_name)
order_value = push_order_value(order_value, g.strategy_name)
order_target_value = push_order_target_value(order_target_value, g.strategy_name)

# 初始化函数
def initialize(context):
    # 设定基准
    set_benchmark('399101.XSHE')
    # 用真实价格交易
    set_option('use_real_price', True)
    # 打开防未来函数
    set_option("avoid_future_data", True)
    # 将滑点设置为0.0003
    set_slippage(FixedSlippage(3/10000))
    # 设置交易成本
    set_order_cost(
        OrderCost(open_tax=0, close_tax=0.001, open_commission=0.0003, close_commission=0.0003,
                close_today_commission=0, min_commission=5),
        type='stock'
    )
    # 过滤order中低于error级别的日志
    log.set_level('order', 'error')

    # 全局变量
    # g.stock_num = 5
    g.stock_num = 8
    g.hold_list = []              # 当前持仓的全部股票
    g.yesterday_HL_list = []      # 记录持仓中昨日涨停的股票
    g.pass_months = True          # 是否一四月空仓（当前策略未启用）
    
    # ============================================================
    # 模型选择：手动选择要使用的模型
    # 可选值: 'lightgbm', 'xgboost', 'ensemble'
    # ============================================================
    g.model_type = 'ensemble'  # 修改这里来选择不同的模型

    # 原始因子列表（包含所有可能的因子）
    g.factor_list = ['asset_impairment_loss_ttm', 'cash_flow_to_price_ratio', 'market_cap', 
        'interest_free_current_liability', 'EBITDA', 'financial_assets', 
        'gross_profit_ttm', 'net_working_capital', 'non_recurring_gain_loss', 'EBIT',
        'sales_to_price_ratio', 'AR', 'ARBR', 'ATR6', 'DAVOL10', 'MAWVAD', 'TVMA6', 
        'PSY', 'VOL10', 'VDIFF', 'VEMA26', 'VMACD', 'VOL120', 'VOSC', 'VR', 'WVAD', 
        'arron_down_25', 'arron_up_25', 'BBIC', 'MASS', 'Rank1M', 'single_day_VPT', 
        'single_day_VPT_12', 'single_day_VPT_6', 'Volume1M',
        'capital_reserve_fund_per_share', 'net_asset_per_share', 
        'net_operate_cash_flow_per_share', 'operating_profit_per_share', 
        'total_operating_revenue_per_share', 'surplus_reserve_fund_per_share',
        'ACCA', 'account_receivable_turnover_days', 'account_receivable_turnover_rate', 
        'adjusted_profit_to_total_profit', 'super_quick_ratio', 'MLEV', 
        'debt_to_equity_ratio', 'debt_to_tangible_equity_ratio', 
        'equity_to_fixed_asset_ratio', 'fixed_asset_ratio', 'intangible_asset_ratio', 
        'invest_income_associates_to_total_profit', 'long_debt_to_asset_ratio',
        'long_debt_to_working_capital_ratio', 'net_operate_cash_flow_to_total_liability', 
        'net_operating_cash_flow_coverage', 'non_current_asset_ratio', 
        'operating_profit_to_total_profit', 'roa_ttm', 'roe_ttm', 'Kurtosis120', 
        'Kurtosis20', 'Kurtosis60', 'sharpe_ratio_20', 'sharpe_ratio_60', 
        'Skewness120', 'Skewness20', 'Skewness60', 'Variance120', 'Variance20', 
        'liquidity', 'beta', 'book_to_price_ratio', 'cash_earnings_to_price_ratio', 
        'cube_of_size', 'earnings_to_price_ratio', 'earnings_yield', 'growth', 
        'momentum', 'natural_log_of_market_cap', 'boll_down', 'MFI14', 'MAC10', 
        'fifty_two_week_close_rank', 'price_no_fq'
    ]
    
    # 读取模型和特征列表
    try:
        if g.model_type == 'lightgbm':
            log.info("===== 使用 LightGBM 模型 =====")
            model_data = pickle.loads(read_file('model_lightgbm.pkl'))
            
            # 判断是否为字典格式
            if isinstance(model_data, dict):
                g.model = model_data.get('lgb_model') or model_data.get('model')
                g.model_features = model_data.get('feature_names') or list(g.model.feature_name())
            else:
                # 直接是LightGBM模型对象
                g.model = model_data
                g.model_features = list(g.model.feature_name())
            
            g.xgb_model = None
            g.lgb_model = None
            
        elif g.model_type == 'xgboost':
            log.info("===== 使用 XGBoost 模型 =====")
            model_data = pickle.loads(read_file('model_xgboost.pkl'))
            
            # 判断是否为字典格式
            if isinstance(model_data, dict):
                g.xgb_model = model_data.get('xgb_model') or model_data.get('model')
                g.model_features = model_data.get('feature_names')
            else:
                # 直接是XGBoost Booster对象
                g.xgb_model = model_data
                # XGBoost Booster对象可以通过feature_names属性获取特征
                if hasattr(g.xgb_model, 'feature_names') and g.xgb_model.feature_names:
                    g.model_features = g.xgb_model.feature_names
                else:
                    # 如果没有feature_names，使用原始因子列表
                    g.model_features = g.factor_list
                    log.warning("XGBoost模型中没有feature_names，使用完整因子列表")
            
            g.model = None
            g.lgb_model = None
            
        elif g.model_type == 'ensemble':
            log.info("===== 使用集成模型 (LightGBM + XGBoost) =====")
            ensemble_data = pickle.loads(read_file('model_ensemble.pkl'))
            
            if isinstance(ensemble_data, dict):
                g.lgb_model = ensemble_data.get('lgb_model')
                g.xgb_model = ensemble_data.get('xgb_model')
                g.model_features = ensemble_data.get('feature_names')
                
                # 如果没有feature_names，尝试从LightGBM模型获取
                if not g.model_features and g.lgb_model:
                    g.model_features = list(g.lgb_model.feature_name())
            else:
                raise ValueError("集成模型文件格式不正确，应为字典格式")
            
            g.model = None
            
        else:
            raise ValueError("无效的模型类型，请选择 'lightgbm', 'xgboost' 或 'ensemble'")
        
        # 确保model_features是列表且不为空
        if g.model_features is None:
            g.model_features = g.factor_list
            log.warning("未找到特征列表，使用完整因子列表")
        elif not isinstance(g.model_features, list):
            g.model_features = list(g.model_features)
            
        log.info("成功加载模型，特征数量: {}".format(len(g.model_features)))
        log.info("特征列表前10个: {}".format(g.model_features[:10]))
        
    except Exception as e:
        log.error("模型加载失败: {}".format(e))
        import traceback
        log.error("详细错误: {}".format(traceback.format_exc()))
        g.model = None
        g.model_features = g.factor_list  # 使用完整因子列表作为后备
        g.xgb_model = None
        g.lgb_model = None

    # 调度
    # run_daily(prepare_stock_list, '9:05')
    # run_weekly(weekly_adjustment, weekday=1, time='10:30')
    # run_daily(check_limit_up, '14:00')
    
    # 调度
    run_daily(prepare_stock_list, '9:05')
    run_daily(show_select_result, '9:15')
    run_monthly(weekly_adjustment, 1, '14:00')   # 每月1日调仓
    run_monthly(weekly_adjustment, 11, '14:00')  # 每月15日调仓
    run_daily(show_select_result, '14:30')
    run_daily(check_limit_up, '10:30')
    run_daily(check_limit_up, '14:15')
    

# 1-1 准备股票池
def prepare_stock_list(context):
    # 获取已持有列表
    g.hold_list = []
    for position in list(context.portfolio.positions.values()):
        stock = position.security
        g.hold_list.append(stock)

    # 获取昨日涨停列表（上一交易日）
    if g.hold_list:
        df = get_price(g.hold_list, end_date=context.previous_date, frequency='daily',
                    fields=['close', 'high_limit'], count=1, panel=False, fill_paused=False)
        df = df[df['close'] == df['high_limit']]
        g.yesterday_HL_list = list(df.code) if len(df) > 0 else []
    else:
        g.yesterday_HL_list = []
        
# 显示当前选股结果
def show_select_result(context):
    log.info(f"<<<<<<<<< 当前选股结果：>>>>>>>>>>")
    target_list = get_stock_list(context)
    current_data = get_current_data()
    for stock_code in target_list:
        stock_name = current_data[stock_code].name
        log.info(f"{stock_code} {stock_name}")
    upload_stock_selections(g.strategy_name, target_list)    

# 1-2 选股模块（支持三种模型）
def get_stock_list(context):
    yesterday = context.previous_date
    
    # 初始股票池：中小综指（上一交易日的成分）
    stocks = get_index_stocks('399101.XSHE', yesterday)

    # 过滤
    initial_list = filter_kcbj_stock(stocks)
    initial_list = filter_st_stock(initial_list)
    initial_list = filter_paused_stock(initial_list)
    initial_list = filter_new_stock(context, initial_list)
    initial_list = filter_limitup_stock(context, initial_list)
    initial_list = filter_limitdown_stock(context, initial_list)
    
    # initial_list = [stock for stock in initial_list if stock not in ['002193.XSHE', '002513.XSHE']]

    # 检查模型是否加载成功
    if g.model_features is None or len(g.model_features) == 0:
        log.error("模型特征列表为空，无法进行预测")
        return []

    if not initial_list:
        log.info("过滤后无可用股票")
        return []

    # 获取模型所需的因子
    req_factors = [f for f in g.model_features if f in g.factor_list]
    
    if not req_factors:
        log.error("没有可用的因子数据")
        return []

    # 获取因子横截面数据
    try:
        factor_data = get_factor_values(initial_list, req_factors, end_date=yesterday, count=1)
    except Exception as e:
        log.error("获取因子数据失败: {}".format(e))
        return []

    # 组装为DataFrame
    df_jq_factor_value = pd.DataFrame(index=initial_list)
    for f in req_factors:
        df_jq_factor_value[f] = list(factor_data[f].T.iloc[:, 0])

    # 按模型特征名完整对齐
    df_jq_factor_value = df_jq_factor_value.reindex(columns=g.model_features)
    
    # 填充缺失值（使用0或中位数）
    df_jq_factor_value = df_jq_factor_value.fillna(0)

    # 模型推理
    try:
        if g.model_type == 'lightgbm':
            # LightGBM预测
            if g.model is None:
                log.error("LightGBM模型未加载")
                return []
            tar = g.model.predict(df_jq_factor_value)
            
        elif g.model_type == 'xgboost':
            # XGBoost预测
            if g.xgb_model is None:
                log.error("XGBoost模型未加载")
                return []
            dmatrix = xgb.DMatrix(df_jq_factor_value)
            tar = g.xgb_model.predict(dmatrix)
            
        elif g.model_type == 'ensemble':
            # 集成模型：平均两个模型的预测
            if g.lgb_model is None or g.xgb_model is None:
                log.error("集成模型未完全加载")
                return []
            lgb_pred = g.lgb_model.predict(df_jq_factor_value)
            dmatrix = xgb.DMatrix(df_jq_factor_value)
            xgb_pred = g.xgb_model.predict(dmatrix)
            tar = (lgb_pred + xgb_pred) / 2

    except Exception as e:
        log.error("模型预测失败: {}".format(e))
        import traceback
        log.error("详细错误信息: {}".format(traceback.format_exc()))
        return []

    # 排序并截取TopN
    df = df_jq_factor_value.copy()
    df['total_score'] = list(tar)
    df = df.sort_values(by=['total_score'], ascending=False)
    lst = df.index.tolist()
    lst = lst[:min(g.stock_num, len(lst))]
    
    # 输出Top股票及其得分
    if len(lst) > 0:
        log.info("=== Top {} 股票预测得分 ===".format(len(lst)))
        for i, stock in enumerate(lst, 1):
            score = df.loc[stock, 'total_score']
            log.info("{}. {} - 得分: {:.4f}".format(i, stock, score))
    
    return lst

# 1-3 整体调整持仓
def weekly_adjustment(context):
    # 获取应买入列表
    target_list = get_stock_list(context)

    # 调仓卖出：不在目标且非昨日涨停的卖出
    for stock in g.hold_list:
        if (stock not in target_list) and (stock not in g.yesterday_HL_list):
            log.info("卖出[%s]" % (stock))
            position = context.portfolio.positions.get(stock, None)
            if position:
                close_position(position)
        else:
            log.info("已持有[%s]" % (stock))

    # 调仓买入：等权买入至目标数量
    position_count = len(context.portfolio.positions)
    target_num = len(target_list)
    if target_num > position_count:
        per_value = context.portfolio.cash / float(target_num - position_count) if (target_num - position_count) > 0 else 0.0
        for stock in target_list:
            pos = context.portfolio.positions.get(stock, None)
            already_holding = (pos is not None and pos.total_amount > 0)
            if not already_holding:
                if per_value > 0 and open_position(stock, per_value):
                    if len(context.portfolio.positions) >= target_num:
                        break
                    
    update_positions(g.strategy_name, context)

# 1-4 调整昨日涨停股票（涨停打开则卖出）
def check_limit_up(context):
    now_time = context.current_dt
    if g.yesterday_HL_list:
        for stock in g.yesterday_HL_list:
            current_data = get_price(stock, end_date=now_time, frequency='1m',
                                    fields=['close', 'high_limit'],
                                    skip_paused=False, fq='pre', count=1,
                                    panel=False, fill_paused=True)
            if len(current_data) > 0:
                close_px = current_data.iloc[0]['close']
                high_lim = current_data.iloc[0]['high_limit']
                if close_px < high_lim:
                    log.info("[%s]涨停打开，卖出" % (stock))
                    position = context.portfolio.positions.get(stock, None)
                    if position:
                        close_position(position)
                else:
                    log.info("[%s]涨停，继续持有" % (stock))
    
    update_positions(g.strategy_name, context)

# 3-1 交易模块-自定义下单
def order_target_value_(security, value):
    if value == 0:
        log.debug("Selling out %s" % (security))
    else:
        log.debug("Order %s to value %f" % (security, value))
    return order_target_value(security, value)

# 3-2 交易模块-开仓
def open_position(security, value):
    order_obj = order_target_value_(security, value)
    if order_obj is not None and order_obj.filled > 0:
        return True
    return False

# 3-3 交易模块-平仓
def close_position(position):
    security = position.security
    order_obj = order_target_value_(security, 0)
    if order_obj is not None:
        if (order_obj.status == OrderStatus.held) and (order_obj.filled == order_obj.amount):
            return True
    return False

# 2-1 过滤停牌股票
def filter_paused_stock(stock_list):
    current_data = get_current_data()
    return [stock for stock in stock_list if not current_data[stock].paused]

# 2-2 过滤ST及其他具有退市标签的股票
def filter_st_stock(stock_list):
    current_data = get_current_data()
    return [stock for stock in stock_list
            if not current_data[stock].is_st
            and 'ST' not in current_data[stock].name
            and '*' not in current_data[stock].name
            and '退' not in current_data[stock].name]

# 2-3 过滤科创板/北交所/创业板（保留主板与中小板）
def filter_kcbj_stock(stock_list):
    res = []
    for stock in stock_list:
        if (stock[:2] == '68') or (stock[0] in ['4', '8']) or (stock[0] == '3'):
            continue
        res.append(stock)
    return res

# 2-4 过滤涨停的股票
def filter_limitup_stock(context, stock_list):
    if not stock_list:
        return []
    last_prices = history(1, unit='1m', field='close', security_list=stock_list)
    current_data = get_current_data()
    res = []
    for stock in stock_list:
        in_pos = (stock in context.portfolio.positions.keys())
        if in_pos:
            res.append(stock)
        else:
            try:
                if last_prices[stock][-1] < current_data[stock].high_limit:
                    res.append(stock)
            except Exception:
                res.append(stock)
    return res

# 2-5 过滤跌停的股票
def filter_limitdown_stock(context, stock_list):
    if not stock_list:
        return []
    last_prices = history(1, unit='1m', field='close', security_list=stock_list)
    current_data = get_current_data()
    res = []
    for stock in stock_list:
        in_pos = (stock in context.portfolio.positions.keys())
        if in_pos:
            res.append(stock)
        else:
            try:
                if last_prices[stock][-1] > current_data[stock].low_limit:
                    res.append(stock)
            except Exception:
                res.append(stock)
    return res

# 2-6 过滤次新股（上市满375天）
def filter_new_stock(context, stock_list):
    yesterday = context.previous_date
    return [stock for stock in stock_list
            if not (yesterday - get_security_info(stock).start_date < datetime.timedelta(days=375))]
