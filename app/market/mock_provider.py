import random
from app.models import StockSnapshot, TechnicalSnapshot, KeyLevels, PeerMove


COMPANY = {
    "NVDA": ("NVIDIA", "Semiconductors"),
    "AMD": ("Advanced Micro Devices", "Semiconductors"),
    "AAPL": ("Apple", "Consumer Electronics"),
    "TSLA": ("Tesla", "Electric Vehicles"),
    "MSFT": ("Microsoft", "Software"),
    "SPY": ("SPDR S&P 500 ETF", "Index ETF"),
    "QQQ": ("Invesco QQQ Trust", "Index ETF"),
}


BASE_PRICE = {
    "NVDA": 128.42,
    "AMD": 164.88,
    "AAPL": 193.10,
    "TSLA": 176.45,
    "MSFT": 430.22,
    "SPY": 520.10,
    "QQQ": 445.30,
}


def get_snapshot(symbol: str) -> StockSnapshot:
    symbol = symbol.upper()
    company, sector = COMPANY.get(symbol, (symbol, "Unknown"))
    base = BASE_PRICE.get(symbol, 100.0)

    today_change = round(random.uniform(-4.2, 4.2), 2)
    five_day = round(today_change + random.uniform(-3, 3), 2)
    twenty_day = round(five_day + random.uniform(-8, 8), 2)
    volume_ratio = round(random.uniform(0.6, 3.2), 2)

    price = round(base * (1 + today_change / 100), 2)
    ma20_relation = "above" if price >= base * 0.99 else "below"
    ma50_relation = "above" if price >= base * 0.97 else "below"
    trend_5d = "uptrend" if five_day > 1.5 else "downtrend" if five_day < -1.5 else "range"
    trend_20d = "uptrend" if twenty_day > 4 else "downtrend" if twenty_day < -4 else "range"
    rsi = round(min(88, max(18, 50 + today_change * 5 + random.uniform(-8, 8))), 1)
    macd = "bullish" if today_change > 0.6 else "bearish" if today_change < -0.6 else "neutral"

    support_1 = round(price * 0.985, 2)
    support_2 = round(price * 0.965, 2)
    resistance_1 = round(price * 1.012, 2)
    resistance_2 = round(price * 1.03, 2)

    peer_candidates = {
        "NVDA": ["AMD", "AVGO", "SMH"],
        "AMD": ["NVDA", "AVGO", "SMH"],
        "TSLA": ["RIVN", "LCID", "XLY"],
        "AAPL": ["MSFT", "QQQ", "XLK"],
        "MSFT": ["AAPL", "QQQ", "XLK"],
    }.get(symbol, ["SPY", "QQQ"])

    return StockSnapshot(
        symbol=symbol,
        company=company,
        current_price=price,
        today_change_pct=today_change,
        five_day_change_pct=five_day,
        twenty_day_change_pct=twenty_day,
        volume_vs_20d_avg=volume_ratio,
        sector=sector,
        sector_change_pct=round(random.uniform(-2, 2.5), 2),
        spy_change_pct=round(random.uniform(-1.2, 1.2), 2),
        qqq_change_pct=round(random.uniform(-1.5, 1.6), 2),
        technical=TechnicalSnapshot(
            trend_5d=trend_5d,
            trend_20d=trend_20d,
            price_vs_ma20=ma20_relation,
            price_vs_ma50=ma50_relation,
            rsi_14=rsi,
            macd=macd,
            vwap_position="above" if today_change > 0 else "below",
        ),
        key_levels=KeyLevels(
            support=[support_1, support_2],
            resistance=[resistance_1, resistance_2],
        ),
        recent_news=[],
        peer_moves=[
            PeerMove(symbol=p, change_pct=round(random.uniform(-3, 3), 2))
            for p in peer_candidates
        ],
    )
