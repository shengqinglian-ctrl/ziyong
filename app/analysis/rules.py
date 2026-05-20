from app.models import StockSnapshot


def should_trigger(snapshot: StockSnapshot) -> tuple[bool, list[str]]:
    reasons: list[str] = []

    if abs(snapshot.today_change_pct) >= 2.5:
        direction = "上涨" if snapshot.today_change_pct > 0 else "下跌"
        reasons.append(f"今日{direction}{abs(snapshot.today_change_pct):.2f}%")

    if snapshot.volume_vs_20d_avg >= 2.0:
        reasons.append(f"成交量达到 20 日均量的 {snapshot.volume_vs_20d_avg:.2f} 倍")

    if snapshot.technical.rsi_14 >= 70:
        reasons.append(f"RSI 为 {snapshot.technical.rsi_14:.1f}，接近或进入过热区")

    if snapshot.technical.rsi_14 <= 30:
        reasons.append(f"RSI 为 {snapshot.technical.rsi_14:.1f}，接近或进入超卖区")

    if snapshot.current_price >= min(snapshot.key_levels.resistance):
        reasons.append("价格接近或突破短线阻力位")

    if snapshot.current_price <= max(snapshot.key_levels.support):
        reasons.append("价格接近或跌破短线支撑位")

    return bool(reasons), reasons
