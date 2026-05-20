# Stock AI Feishu MVP

这是一个股票实时分析工具的第一版 MVP 骨架。

它已经包含：

- FastAPI 后端
- 模拟行情数据源
- 技术指标计算
- OpenAI API 分析模块
- 飞书/Lark 自定义机器人推送
- 定时扫描 watchlist
- 手动分析接口
- Docker 配置

当前版本默认使用模拟行情，方便先跑通全链路。后续可以把 `app/market/mock_provider.py` 替换成真实行情源，比如 Alpaca、Polygon、IBKR、Finnhub 等。

## 1. 本地启动

```bash
cp .env.example .env
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

打开：

```text
http://127.0.0.1:8000/docs
```

## 2. 配置环境变量

编辑 `.env`：

```bash
OPENAI_API_KEY=你的 OpenAI API Key
OPENAI_MODEL=gpt-5.1-mini
FEISHU_WEBHOOK_URL=你的飞书机器人 webhook
ENABLE_FEISHU_PUSH=true
ENABLE_OPENAI_ANALYSIS=true
```

如果你暂时没有 key，可以保持：

```bash
ENABLE_OPENAI_ANALYSIS=false
ENABLE_FEISHU_PUSH=false
```

这样系统会用本地规则生成模拟分析，不会调用外部服务。

## 3. 手动分析一只股票

```bash
curl -X POST http://127.0.0.1:8000/analyze/NVDA
```

返回内容包含：

- 当前价格
- 今日涨跌
- 成交量倍率
- 趋势状态
- AI 解释
- 支撑压力
- 风险提示
- 下一步观察点

## 4. 测试飞书推送

```bash
curl -X POST http://127.0.0.1:8000/notify/test
```

## 5. 启动自动扫描

服务启动后会自动扫描 watchlist。默认列表在：

```text
app/config.py
```

默认股票：

```text
NVDA, AAPL, TSLA, AMD, MSFT, SPY, QQQ
```

触发条件在：

```text
app/analysis/rules.py
```

默认规则：

- 涨跌幅绝对值 >= 2.5%
- 成交量 >= 20 日均量 2 倍
- RSI >= 70 或 RSI <= 30
- 价格突破阻力位或跌破支撑位

触发后会生成分析，并在开启飞书推送时发到群里。

## 6. 后续接真实行情

替换这个文件：

```text
app/market/mock_provider.py
```

保持输出结构不变即可。

需要真实行情时，新 provider 需要返回：

```json
{
  "symbol": "NVDA",
  "company": "NVIDIA",
  "current_price": 128.42,
  "today_change_pct": 3.2,
  "five_day_change_pct": 6.8,
  "twenty_day_change_pct": 14.5,
  "volume_vs_20d_avg": 2.6,
  "sector": "Semiconductors",
  "sector_change_pct": 1.9,
  "spy_change_pct": 0.4,
  "qqq_change_pct": 0.8,
  "technical": {
    "trend_5d": "uptrend",
    "trend_20d": "uptrend",
    "price_vs_ma20": "above",
    "price_vs_ma50": "above",
    "rsi_14": 72,
    "macd": "bullish",
    "vwap_position": "above"
  },
  "key_levels": {
    "support": [129.2, 126.8],
    "resistance": [130.5, 134.0]
  },
  "recent_news": [],
  "peer_moves": []
}
```

## 7. 注意事项

本工具只用于行情整理、技术指标分析和信息提醒，不构成投资建议。
AI 输出必须基于输入数据，不允许编造新闻、价格、财报或宏观事件。
