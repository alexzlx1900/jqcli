# 克隆来源：七星高照ETF轮动优化版
# 重构版本：七星高照ETF轮动-风控重构版
# 调整重点：
# 1. 盈利保护只作用于已有盈利的持仓，未持仓标的不再复用该逻辑。
# 2. ETF 池增加资产类别、溢价数据策略、上市天数与流动性检查。
# 3. 跨境/商品/LOF 等溢价敏感品种缺失溢价数据时不再直接放行。
# 4. 下单改为目标市值语义，保留交易前检查与更清晰日志。
# 5. 拆分配置、过滤、评分、调仓模块，清理未使用变量和硬编码。

import datetime
import math

import numpy as np
import pandas as pd
from jqdata import *

# 上传选股结果 upload_stock_selections(g.strategy_name, target_list)
# 上传持仓明细 update_positions(g.strategy_name, context)
from jq_trader_api import *

g.strategy_name = "七星高照ETF轮动策略"
order = push_order(order, g.strategy_name)
order_target = push_order_target(order_target, g.strategy_name)
order_value = push_order_value(order_value, g.strategy_name)
order_target_value = push_order_target_value(order_target_value, g.strategy_name)


ETF_UNIVERSE = [
    ("518880.XSHG", "黄金ETF", "commodity"),
    ("159980.XSHE", "有色ETF", "commodity"),
    ("159985.XSHE", "豆粕ETF", "commodity"),
    ("501018.XSHG", "南方原油", "commodity"),
    ("161226.XSHE", "白银LOF", "commodity"),
    ("159981.XSHE", "能源化工ETF", "commodity"),
    ("513100.XSHG", "纳指ETF", "overseas"),
    ("159509.XSHE", "纳指科技ETF", "overseas"),
    ("513290.XSHG", "纳指生物ETF", "overseas"),
    ("513500.XSHG", "标普500ETF", "overseas"),
    ("159529.XSHE", "标普消费", "overseas"),
    ("513400.XSHG", "道琼斯ETF", "overseas"),
    ("513520.XSHG", "日经225ETF", "overseas"),
    ("513030.XSHG", "德国30ETF", "overseas"),
    ("513080.XSHG", "法国ETF", "overseas"),
    ("513310.XSHG", "中韩半导体ETF", "overseas"),
    ("513730.XSHG", "东南亚ETF", "overseas"),
    ("159792.XSHE", "港股互联ETF", "hongkong"),
    ("513130.XSHG", "恒生科技", "hongkong"),
    ("513050.XSHG", "中概互联网ETF", "hongkong"),
    ("159920.XSHE", "恒生ETF", "hongkong"),
    ("513690.XSHG", "港股红利", "hongkong"),
    ("510300.XSHG", "沪深300ETF", "domestic"),
    ("510500.XSHG", "中证500ETF", "domestic"),
    ("510050.XSHG", "上证50ETF", "domestic"),
    ("510210.XSHG", "上证ETF", "domestic"),
    ("159915.XSHE", "创业板ETF", "domestic"),
    ("588080.XSHG", "科创50ETF", "domestic"),
    ("512100.XSHG", "中证1000ETF", "domestic"),
    ("563360.XSHG", "A500ETF", "domestic"),
    ("563300.XSHG", "中证2000ETF", "domestic"),
    ("512890.XSHG", "红利低波ETF", "style"),
    ("159967.XSHE", "创业板成长ETF", "style"),
    ("512040.XSHG", "价值ETF", "style"),
    ("159201.XSHE", "自由现金流ETF", "style"),
    ("511380.XSHG", "可转债ETF", "bond"),
    ("511010.XSHG", "国债ETF", "bond"),
    ("511220.XSHG", "城投债ETF", "bond"),
]


def initialize(context):
    set_option("avoid_future_data", True)
    set_option("use_real_price", True)
    set_slippage(PriceRelatedSlippage(0.0002), type="fund")
    set_order_cost(
        OrderCost(
            open_tax=0,
            close_tax=0,
            open_commission=0.0002,
            close_commission=0.0002,
            close_today_commission=0,
            min_commission=5,
        ),
        type="fund",
    )
    set_benchmark("000300.XSHG")

    log.set_level("order", "error")
    log.set_level("system", "error")
    log.set_level("strategy", "debug")

    configure_strategy()
    schedule_jobs()
    log_config_summary()


def configure_strategy():
    g.strategy_name = "七星高照ETF轮动策略"
    g.etf_pool = [item[0] for item in ETF_UNIVERSE]
    g.etf_names = {item[0]: item[1] for item in ETF_UNIVERSE}
    g.etf_groups = {item[0]: item[2] for item in ETF_UNIVERSE}
    g.defensive_etf = "511880.XSHG"

    # 组合与动量参数
    g.holdings_num = 3
    g.lookback_days = 25
    g.short_lookback_days = 10
    g.short_momentum_threshold = 0.0
    g.min_score_threshold = 0.0
    g.max_score_threshold = 100.0
    g.max_single_day_drop = 0.03
    g.position_keep_rank = g.holdings_num

    # 数据质量与流动性过滤，避免新上市、低成交额品种主导短窗口回测。
    g.min_listing_days = 80
    g.liquidity_lookback = 20
    g.min_avg_money = 20000000

    # 溢价敏感品种的数据缺失不再直接放行。
    g.enable_premium_filter = True
    g.premium_sensitive_groups = set(["commodity", "overseas", "hongkong"])
    g.premium_thresholds = {
        "commodity": 0.08,
        "overseas": 0.08,
        "hongkong": 0.08,
        "domestic": 0.20,
        "style": 0.20,
        "bond": 0.20,
    }

    # 当日异常放量过滤只拦截“短期涨幅已经过热”的标的。
    g.enable_volume_check = True
    g.volume_lookback = 5
    g.volume_threshold = 2.0
    g.volume_return_limit = 1.0

    # 盈利保护只处理已有盈利持仓，不用于未持仓标的筛选。
    g.enable_profit_protection = True
    g.profit_protection_lookback = 5
    g.profit_protection_drawdown = 0.05
    g.profit_protection_min_profit = 0.03
    g.profit_protection_check_times = ["11:00"]

    g.min_trade_value = 5000
    g.rebalance_tolerance = 0.05
    g.rankings_cache = {"date": None, "data": None}
    g.filter_stats = {}


def schedule_jobs():
    run_daily(log_positions, time="09:10")
    for check_time in g.profit_protection_check_times:
        run_daily(profit_protection_check, time=check_time)
    run_daily(rebalance_sell, time="13:10")
    run_daily(rebalance_buy, time="13:11")


def log_config_summary():
    group_counts = {}
    for code in g.etf_pool:
        group = get_group(code)
        group_counts[group] = group_counts.get(group, 0) + 1
    log.info("========== 七星高照ETF轮动-风控重构版 初始化完成 ==========")
    log.info("ETF数量%s，分组%s，目标持仓%s只，动量窗口%s日", len(g.etf_pool), group_counts, g.holdings_num, g.lookback_days)
    log.info("流动性过滤：上市>%s日，%s日均成交额>%.0f", g.min_listing_days, g.liquidity_lookback, g.min_avg_money)
    log.info("盈利保护：盈利>%.1f%%且%s日高点回撤>%.1f%%触发", g.profit_protection_min_profit * 100, g.profit_protection_lookback, g.profit_protection_drawdown * 100)
    log.info("溢价过滤：敏感分组%s，阈值%s", list(g.premium_sensitive_groups), g.premium_thresholds)


def log_positions(context):
    active_positions = [code for code, pos in context.portfolio.positions.items() if pos.total_amount > 0]
    if not active_positions:
        log.info("当前无ETF持仓")
        return
    for code in active_positions:
        pos = context.portfolio.positions[code]
        log.info(
            "持仓 %s %s 数量%s 成本%.3f 现价%.3f 市值%.2f",
            code,
            get_name(code),
            pos.total_amount,
            pos.avg_cost,
            pos.price,
            pos.value,
        )


def profit_protection_check(context):
    if not g.enable_profit_protection:
        return
    log.info("========== 盈利保护检查开始 ==========")
    for code, pos in list(context.portfolio.positions.items()):
        if not is_managed_etf(code) or pos.total_amount <= 0:
            continue
        triggered, reason = should_take_profit(code, pos)
        if triggered:
            log.info("盈利保护触发：%s %s，原因：%s", code, get_name(code), reason)
            submit_target_value(code, 0, context, reason="profit_protection")
    publish_positions(context, "profit_protection_check")
    log.info("========== 盈利保护检查完成 ==========")


def should_take_profit(code, position):
    current_price = get_last_price(code)
    if current_price <= 0 or position.avg_cost <= 0:
        return False, "价格或成本无效"

    profit = current_price / position.avg_cost - 1
    if profit < g.profit_protection_min_profit:
        return False, "浮盈不足"

    hist = attribute_history(code, g.profit_protection_lookback, "1d", ["high"], skip_paused=True)
    if hist is None or hist.empty:
        return False, "历史高点不足"

    recent_high = max(float(hist["high"].max()), current_price)
    drawdown = 1 - current_price / recent_high
    if drawdown >= g.profit_protection_drawdown:
        reason = "浮盈%.2f%%，%s日高点%.3f，当前%.3f，回撤%.2f%%" % (
            profit * 100,
            g.profit_protection_lookback,
            recent_high,
            current_price,
            drawdown * 100,
        )
        return True, reason
    return False, "回撤未触发"


def rebalance_sell(context):
    log.info("========== 卖出检查开始 ==========")
    ranked = get_cached_rankings(context)
    target_etfs = select_target_etfs(ranked)
    target_set = set(target_etfs)
    keep_set = set(item["code"] for item in ranked[:g.position_keep_rank])

    if not target_etfs and is_tradeable(g.defensive_etf, "buy")[0]:
        target_set = set([g.defensive_etf])
        log.info("无进攻目标，卖出阶段切换为防御目标：%s %s", g.defensive_etf, get_name(g.defensive_etf))

    for code, pos in list(context.portfolio.positions.items()):
        if not is_managed_etf(code) or pos.total_amount <= 0:
            continue
        if code in target_set:
            continue
        if code in keep_set:
            log.info("保留持仓：%s %s 仍在前%s名", code, get_name(code), g.position_keep_rank)
            continue
        submit_target_value(code, 0, context, reason="not_in_target")
    publish_positions(context, "rebalance_sell")
    log.info("========== 卖出检查完成 ==========")


def rebalance_buy(context):
    log.info("========== 买入/调仓开始 ==========")
    ranked = get_cached_rankings(context)
    target_etfs = select_target_etfs(ranked)

    if not target_etfs:
        if is_tradeable(g.defensive_etf, "buy")[0]:
            target_etfs = [g.defensive_etf]
            log.info("进入防御模式：%s %s", g.defensive_etf, get_name(g.defensive_etf))
        else:
            log.info("无进攻目标且防御ETF不可买，保持现金")
            publish_stock_selections([], "no_target")
            publish_positions(context, "rebalance_buy_no_target")
            return

    publish_stock_selections(target_etfs, "rebalance_buy")
    pending_sells = get_pending_sell_positions(target_etfs, context)
    if pending_sells:
        log.info("仍有非目标持仓待卖出，暂停买入：%s", [(code, get_name(code)) for code in pending_sells])
        publish_positions(context, "rebalance_buy_pending_sells")
        return

    target_value = context.portfolio.total_value / len(target_etfs)
    log.info("目标组合：%s，单只目标市值%.2f", [(code, get_name(code)) for code in target_etfs], target_value)
    for code in target_etfs:
        current_value = get_position_value(code, context)
        if current_value == 0 or abs(current_value - target_value) > target_value * g.rebalance_tolerance:
            submit_target_value(code, target_value, context, reason="rebalance")
        else:
            log.debug("%s %s 偏离不足%.1f%%，不调仓", code, get_name(code), g.rebalance_tolerance * 100)
    publish_positions(context, "rebalance_buy")
    log.info("========== 买入/调仓完成 ==========")


def get_cached_rankings(context):
    today = context.current_dt.date()
    if g.rankings_cache["date"] != today:
        g.filter_stats = {}
        ranked = rank_etfs(context)
        g.rankings_cache = {"date": today, "data": ranked}
        log_filter_summary()
    else:
        ranked = g.rankings_cache["data"]
        log.debug("使用当日ETF排名缓存，共%s只", len(ranked))
    return ranked


def rank_etfs(context):
    ranked = []
    for code in g.etf_pool:
        passed, reason = precheck_candidate(code, context)
        if not passed:
            count_filter(reason)
            continue

        metrics = calculate_momentum_score(code, context)
        if metrics is None:
            count_filter("score_unavailable")
            continue

        score = metrics["score"]
        if not (g.min_score_threshold < score < g.max_score_threshold):
            count_filter("score_out_of_range")
            continue

        ranked.append(metrics)

    ranked.sort(key=lambda item: item["score"], reverse=True)
    for index, item in enumerate(ranked[:5], start=1):
        log.info(
            "排名%s %s %s 分数%.4f 年化%.2f%% R2=%.4f 短动量%.2f%%",
            index,
            item["code"],
            item["name"],
            item["score"],
            item["annualized_return"] * 100,
            item["r_squared"],
            item["short_annualized"] * 100,
        )
    return ranked


def precheck_candidate(code, context):
    tradeable, reason = is_tradeable(code, "buy")
    if not tradeable:
        return False, reason

    quality_ok, reason = check_data_quality(code, context)
    if not quality_ok:
        return False, reason

    premium_ok, reason = check_premium_risk(code, context)
    if not premium_ok:
        return False, reason

    return True, "ok"


def check_data_quality(code, context):
    info = safe_security_info(code)
    if info is not None and getattr(info, "start_date", None):
        listed_days = (context.current_dt.date() - info.start_date).days
        if listed_days < g.min_listing_days:
            log.debug("%s %s 上市%s日 < %s日，过滤", code, get_name(code), listed_days, g.min_listing_days)
            return False, "new_listing"

    hist = attribute_history(code, g.liquidity_lookback, "1d", ["money"], skip_paused=True)
    if hist is None or hist.empty or len(hist) < max(5, min(g.liquidity_lookback, 10)):
        log.debug("%s %s 成交额数据不足，过滤", code, get_name(code))
        return False, "liquidity_data_missing"

    avg_money = float(hist["money"].mean())
    if avg_money < g.min_avg_money:
        log.debug("%s %s %s日均成交额%.0f < %.0f，过滤", code, get_name(code), g.liquidity_lookback, avg_money, g.min_avg_money)
        return False, "low_liquidity"
    return True, "ok"


def check_premium_risk(code, context):
    if not g.enable_premium_filter:
        return True, "premium_disabled"

    group = get_group(code)
    threshold = g.premium_thresholds.get(group, 0.20)
    prev_date = get_previous_trade_date(context.current_dt.date())
    premium, price, nav, nav_date = get_premium_rate(code, prev_date)

    if premium is None:
        if group in g.premium_sensitive_groups:
            log.info("%s %s 属于%s，溢价数据缺失，过滤", code, get_name(code), group)
            return False, "premium_missing_sensitive"
        log.debug("%s %s 溢价数据缺失，非敏感分组放行", code, get_name(code))
        return True, "premium_missing_allowed"

    if premium > threshold:
        log.info(
            "%s %s 溢价%.2f%% > 阈值%.2f%%，价格%.3f 净值%.3f 净值日%s，过滤",
            code,
            get_name(code),
            premium * 100,
            threshold * 100,
            price,
            nav,
            nav_date,
        )
        return False, "premium_too_high"
    return True, "ok"


def calculate_momentum_score(code, context):
    try:
        lookback = max(g.lookback_days, g.short_lookback_days) + 20
        hist = attribute_history(code, lookback, "1d", ["close", "high"], skip_paused=True)
        if hist is None or hist.empty or len(hist) < g.lookback_days + 1:
            return None

        current_price = get_last_price(code)
        if current_price <= 0:
            return None

        prices = np.append(hist["close"].values, current_price)
        if has_recent_large_drop(prices):
            log.info("%s %s 近3日单日跌幅超过%.1f%%，过滤", code, get_name(code), g.max_single_day_drop * 100)
            return None

        if g.enable_volume_check and is_overheated_by_volume(code, prices, context):
            return None

        short_annualized = calc_annualized_return(prices, g.short_lookback_days)
        if short_annualized < g.short_momentum_threshold:
            log.debug("%s %s 短期动量%.2f%% < 0，过滤", code, get_name(code), short_annualized * 100)
            return None

        annualized, r_squared = calc_regression_momentum(prices, g.lookback_days)
        score = annualized * r_squared
        return {
            "code": code,
            "name": get_name(code),
            "group": get_group(code),
            "annualized_return": annualized,
            "r_squared": r_squared,
            "short_annualized": short_annualized,
            "score": score,
        }
    except Exception as exc:
        log.warning("计算动量失败：%s %s，错误：%s", code, get_name(code), exc)
        return None


def calc_regression_momentum(price_series, lookback_days):
    recent = price_series[-(lookback_days + 1):]
    if len(recent) < 2 or np.any(recent <= 0):
        return 0.0, 0.0
    y = np.log(recent)
    x = np.arange(len(y))
    weights = np.linspace(1, 2, len(y))
    slope, intercept = np.polyfit(x, y, 1, w=weights)
    annualized = math.exp(slope * 250) - 1
    fitted = slope * x + intercept
    ss_res = np.sum(weights * (y - fitted) ** 2)
    ss_tot = np.sum(weights * (y - np.mean(y)) ** 2)
    r_squared = 1 - ss_res / ss_tot if ss_tot != 0 else 0.0
    return annualized, max(0.0, r_squared)


def calc_annualized_return(price_series, lookback_days):
    if len(price_series) < lookback_days + 1:
        return 0.0
    start_price = price_series[-(lookback_days + 1)]
    end_price = price_series[-1]
    if start_price <= 0 or end_price <= 0:
        return 0.0
    period_return = end_price / start_price - 1
    return (1 + period_return) ** (250.0 / lookback_days) - 1


def has_recent_large_drop(price_series):
    if len(price_series) < 4:
        return False
    for offset in [1, 2, 3]:
        today_price = price_series[-offset]
        prev_price = price_series[-offset - 1]
        if prev_price > 0 and today_price / prev_price - 1 < -g.max_single_day_drop:
            return True
    return False


def is_overheated_by_volume(code, price_series, context):
    ratio = get_intraday_volume_ratio(code, context)
    if ratio is None:
        return False
    annualized = calc_regression_momentum(price_series, g.lookback_days)[0]
    if annualized > g.volume_return_limit:
        log.info(
            "%s %s 当日成交量放大%.2f倍且年化动量%.2f%%，过滤",
            code,
            get_name(code),
            ratio,
            annualized * 100,
        )
        return True
    return False


def get_intraday_volume_ratio(code, context):
    hist = attribute_history(code, g.volume_lookback, "1d", ["volume"], skip_paused=True)
    if hist is None or hist.empty or len(hist) < g.volume_lookback:
        return None
    avg_volume = float(hist["volume"].mean())
    if avg_volume <= 0:
        return None

    today = context.current_dt.date()
    df = get_price(code, start_date=today, end_date=context.current_dt, frequency="1m", fields=["volume"], skip_paused=False, fq="pre")
    if df is None or df.empty:
        return None
    ratio = float(df["volume"].sum()) / avg_volume
    return ratio if ratio > g.volume_threshold else None


def select_target_etfs(ranked):
    targets = []
    for item in ranked:
        if len(targets) >= g.holdings_num:
            break
        targets.append(item["code"])
        log.info("候选目标%s：%s %s 分数%.4f", len(targets), item["code"], item["name"], item["score"])
    return targets


def get_pending_sell_positions(target_etfs, context):
    target_set = set(target_etfs)
    pending = []
    for code, pos in context.portfolio.positions.items():
        if is_managed_etf(code) and pos.total_amount > 0 and code not in target_set:
            pending.append(code)
    return pending


def submit_target_value(code, target_value, context, reason):
    tradeable, block_reason = is_tradeable(code, "buy" if target_value > get_position_value(code, context) else "sell")
    if not tradeable:
        log.info("跳过下单：%s %s，原因：%s", code, get_name(code), block_reason)
        return False

    current_value = get_position_value(code, context)
    diff_value = target_value - current_value
    if 0 < abs(diff_value) < g.min_trade_value:
        log.info("跳过下单：%s %s，差额%.2f < 最小交易额%.2f", code, get_name(code), abs(diff_value), g.min_trade_value)
        return False

    price = get_last_price(code)
    if price <= 0:
        log.info("跳过下单：%s %s，价格无效", code, get_name(code))
        return False
    estimated_lots = int(abs(diff_value) / price) // 100
    if estimated_lots <= 0:
        log.info("跳过下单：%s %s，目标差额不足100份，当前%.2f -> 目标%.2f", code, get_name(code), current_value, target_value)
        return False

    if diff_value < 0:
        position = context.portfolio.positions.get(code)
        closeable = position.closeable_amount if position else 0
        if closeable <= 0:
            log.info("跳过卖出：%s %s，无可卖数量", code, get_name(code))
            return False

    order_result = order_target_value(code, target_value)
    if order_result:
        log.info(
            "提交目标市值订单：%s %s 当前%.2f -> 目标%.2f，原因%s",
            code,
            get_name(code),
            current_value,
            target_value,
            reason,
        )
        return True

    log.warning("下单失败：%s %s 当前%.2f -> 目标%.2f，原因%s", code, get_name(code), current_value, target_value, reason)
    return False


def publish_stock_selections(target_list, source):
    try:
        upload_stock_selections(g.strategy_name, target_list)
        log.info("已上送选股结果：策略%s 来源%s 标的%s", g.strategy_name, source, target_list)
    except Exception as exc:
        log.warning("上送选股结果失败：策略%s 来源%s 错误%s", g.strategy_name, source, exc)


def publish_positions(context, source):
    try:
        update_positions(g.strategy_name, context)
        log.info("已上送持仓明细：策略%s 来源%s", g.strategy_name, source)
    except Exception as exc:
        log.warning("上送持仓明细失败：策略%s 来源%s 错误%s", g.strategy_name, source, exc)


def is_tradeable(code, direction):
    try:
        data = get_current_data()[code]
    except Exception:
        return False, "no_current_data"

    if data.paused:
        return False, "paused"
    price = data.last_price
    if price is None or price <= 0:
        return False, "invalid_price"
    if direction == "buy" and price >= data.high_limit:
        return False, "high_limit"
    if direction == "sell" and price <= data.low_limit:
        return False, "low_limit"
    return True, "ok"


def get_premium_rate(code, date, max_back_days=5):
    price_df = get_price(code, start_date=date, end_date=date, frequency="daily", fields=["close"])
    if price_df is None or price_df.empty:
        return None, None, None, None

    market_price = float(price_df["close"].iloc[0])
    start_date = date - datetime.timedelta(days=max_back_days * 2)
    trade_days = get_trade_days(start_date=start_date, end_date=date)
    trade_days = [pd.to_datetime(day).date() for day in trade_days]

    for nav_date in reversed(trade_days):
        nav = get_unit_nav(code, nav_date)
        if nav is not None and nav > 0:
            premium = (market_price - nav) / nav
            if nav_date != date:
                log.debug("%s 使用%s净值计算%s溢价", code, nav_date, date)
            return premium, market_price, nav, nav_date
    return None, market_price, None, None


def get_unit_nav(code, date):
    try:
        df = get_extras("unit_net_value", code, start_date=date, end_date=date, df=True)
        if df is not None and not df.empty and code in df.columns and not pd.isna(df[code].iloc[0]):
            return float(df[code].iloc[0])
    except Exception:
        pass

    try:
        q = query(finance.FUND_NET_VALUE).filter(
            finance.FUND_NET_VALUE.code == code,
            finance.FUND_NET_VALUE.day == date,
        )
        df = finance.run_query(q)
        if df is not None and not df.empty and not pd.isna(df["net_value"].iloc[0]):
            return float(df["net_value"].iloc[0])
    except Exception:
        pass
    return None


def get_previous_trade_date(today):
    trade_days = get_trade_days(end_date=today, count=2)
    if len(trade_days) >= 2:
        return pd.to_datetime(trade_days[0]).date()
    return today


def get_position_value(code, context):
    position = context.portfolio.positions.get(code)
    if position is None or position.total_amount <= 0:
        return 0.0
    return float(position.value)


def get_last_price(code):
    try:
        price = get_current_data()[code].last_price
        return float(price) if price is not None else 0.0
    except Exception:
        return 0.0


def get_name(code):
    try:
        return get_current_data()[code].name
    except Exception:
        return g.etf_names.get(code, "未知")


def get_group(code):
    return g.etf_groups.get(code, "unknown")


def is_managed_etf(code):
    return code in g.etf_pool or code == g.defensive_etf


def safe_security_info(code):
    try:
        return get_security_info(code)
    except Exception:
        return None


def count_filter(reason):
    g.filter_stats[reason] = g.filter_stats.get(reason, 0) + 1


def log_filter_summary():
    if g.filter_stats:
        log.info("过滤统计：%s", g.filter_stats)
    else:
        log.info("本轮无过滤项")
