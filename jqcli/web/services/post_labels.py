from __future__ import annotations

from typing import Any


POSITIVE_TERMS = ("思路", "逻辑", "选股", "择时", "风控", "调仓", "因子", "权重", "止损", "仓位", "代码")
SIMPLE_TUNING_TERMS = ("调参", "参数优化", "改参数", "微调")
COMBO_TERMS = ("组合策略", "拼接", "集合", "多个策略")


def labels_for_post(post: dict[str, Any]) -> list[dict[str, Any]]:
    labels: list[dict[str, Any]] = []
    content = str(post.get("content") or "")
    content_len = len(content)
    positive_hits = sum(1 for term in POSITIVE_TERMS if term in content)
    tuning_hits = sum(1 for term in SIMPLE_TUNING_TERMS if term in content)
    combo_hits = sum(1 for term in COMBO_TERMS if term in content)
    period = post.get("period_years")
    sharpe = post.get("sharpe")

    if post.get("is_original_candidate"):
        labels.append({"label": "原创候选", "score": 1, "reason": "命中原创候选数据集"})
    if content_len >= 350 and positive_hits >= 3:
        labels.append({"label": "详细思路", "score": positive_hits, "reason": f"正文长度 {content_len}，策略描述关键词 {positive_hits} 个"})
    if tuning_hits:
        labels.append({"label": "简单调参", "score": tuning_hits, "reason": "正文包含调参类描述"})
    if combo_hits:
        labels.append({"label": "简单组合", "score": combo_hits, "reason": "正文包含组合/拼接类描述"})
    if "def initialize" in content or "handle_data" in content:
        labels.append({"label": "代码为主", "score": 1, "reason": "正文包含策略代码"})
    if period is not None and float(period) > 1:
        labels.append({"label": "回测大于1年", "score": float(period), "reason": f"回测约 {period} 年"})
    if period is not None and float(period) > 3:
        labels.append({"label": "回测大于3年", "score": float(period), "reason": f"回测约 {period} 年"})
    if sharpe is not None and float(sharpe) > 2:
        labels.append({"label": "夏普偏高", "score": float(sharpe), "reason": f"夏普 {sharpe}"})
    if sharpe is not None and float(sharpe) > 5:
        labels.append({"label": "疑似过拟合", "score": float(sharpe), "reason": f"夏普 {sharpe} 异常偏高"})
    if content_len < 200:
        labels.append({"label": "信息不足", "score": content_len, "reason": f"正文长度 {content_len}"})
    return labels
