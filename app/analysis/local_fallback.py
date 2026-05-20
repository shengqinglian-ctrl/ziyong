from app.models import StockSnapshot, StockAnalysis, MoveExplanation, RecentStatus, WatchNext


def local_analysis(snapshot: StockSnapshot, trigger_reasons: list[str] | None = None) -> StockAnalysis:
    trigger_reasons = trigger_reasons or []

    bullish_score = 0
    bearish_score = 0

    if snapshot.today_change_pct > 1:
        bullish_score += 1
    if snapshot.today_change_pct < -1:
        bearish_score += 1
    if snapshot.volume_vs_20d_avg >= 2 and snapshot.today_change_pct > 0:
        bullish_score += 1
    if snapshot.volume_vs_20d_avg >= 2 and snapshot.today_change_pct < 0:
        bearish_score += 1
    if snapshot.technical.price_vs_ma20 == "above":
        bullish_score += 1
    else:
        bearish_score += 1
    if snapshot.technical.macd == "bullish":
        bullish_score += 1
    if snapshot.technical.macd == "bearish":
        bearish_score += 1
    if snapshot.sector_change_pct > 0:
        bullish_score += 1
    if snapshot.sector_change_pct < 0:
        bearish_score += 1

    if bullish_score > bearish_score + 1:
        bias = "bullish"
    elif bearish_score > bullish_score + 1:
        bias = "bearish"
    else:
        bias = "neutral"

    if snapshot.twenty_day_change_pct > 4:
        trend = "uptrend"
    elif snapshot.twenty_day_change_pct < -4:
        trend = "downtrend"
    elif snapshot.five_day_change_pct > 2 and snapshot.twenty_day_change_pct <= 0:
        trend = "rebound"
    elif snapshot.five_day_change_pct < -2 and snapshot.twenty_day_change_pct >= 0:
        trend = "pullback"
    else:
        trend = "range"

    momentum = "strong" if abs(snapshot.today_change_pct) >= 3 and snapshot.volume_vs_20d_avg >= 2 else (
        "positive" if bullish_score > bearish_score else "weak" if bearish_score > bullish_score else "neutral"
    )

    risk = "high" if snapshot.technical.rsi_14 >= 75 or snapshot.technical.rsi_14 <= 25 else (
        "medium" if snapshot.volume_vs_20d_avg >= 2 or abs(snapshot.today_change_pct) >= 2.5 else "low"
    )

    supporting = []
    if trigger_reasons:
        supporting.extend(trigger_reasons)
    supporting.extend([
        f"今日涨跌幅为 {snapshot.today_change_pct:.2f}%",
        f"成交量为 20 日均量的 {snapshot.volume_vs_20d_avg:.2f} 倍",
        f"板块涨跌幅为 {snapshot.sector_change_pct:.2f}%",
        f"MACD 状态为 {snapshot.technical.macd}",
        f"价格相对 MA20 为 {snapshot.technical.price_vs_ma20}",
    ])

    if snapshot.recent_news:
        uncertain = ["已检测到新闻输入，需要结合新闻来源继续核实。"]
    else:
        uncertain = ["当前样本没有公司新闻输入，涨跌归因主要来自价格、成交量、技术面、板块和大盘数据。"]

    main_reason = "涨跌主要由量价变化、技术位置和板块环境共同驱动"
    if bias == "bullish":
        main_reason = "上涨更可能来自放量、技术面改善或板块配合"
    elif bias == "bearish":
        main_reason = "下跌更可能来自卖压放大、技术面转弱或板块拖累"

    summary = (
        f"{snapshot.symbol} 近期状态为 {trend}，当前动能为 {momentum}。"
        f"今日涨跌 {snapshot.today_change_pct:.2f}%，20 日表现 {snapshot.twenty_day_change_pct:.2f}%。"
        f"RSI 为 {snapshot.technical.rsi_14:.1f}，风险等级 {risk}。"
    )

    return StockAnalysis(
        symbol=snapshot.symbol,
        bias=bias,
        confidence=0.62,
        move_explanation=MoveExplanation(
            main_reason=main_reason,
            supporting_factors=supporting[:8],
            uncertain_factors=uncertain,
        ),
        recent_status=RecentStatus(
            trend=trend,
            momentum=momentum,
            risk_level=risk,
            summary=summary,
        ),
        watch_next=WatchNext(
            support=snapshot.key_levels.support,
            resistance=snapshot.key_levels.resistance,
            triggers=[
                f"放量突破 {snapshot.key_levels.resistance[0]}",
                f"跌破 {snapshot.key_levels.support[0]}",
                "成交量突然放大或快速萎缩",
                "板块或大盘方向发生明显变化",
            ],
        ),
    )
