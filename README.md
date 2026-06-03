# A-Stock Watcher

A 股实时分析与信息收集提醒系统 MVP 骨架。

当前实现聚焦可运行的第一版工程边界：

- FastAPI 后端服务
- SQLite 本地持久化
- 自选股、行情、提醒规则、提醒事件、采集源、信息中心 API
- 后端自动行情采集，默认每 30 秒刷新自选股并执行提醒规则
- 实时资金流向采集与展示，包含主力、超大单、大单、中单、小单净流入
- 飞书、企业微信 webhook 通知通道，提醒触发后可自动推送消息
- 可选模型增强分析：支持本地 7B（Ollama）和 GitHub Models
- React + Ant Design Web 页面
- Mock 行情采集器，用于本地验证规则触发链路
- Docker Compose 本地启动

## 快速启动

```bash
cd /root/a-stock-watcher
docker compose up --build
```

访问：

- Web: http://localhost:5173
- API: http://localhost:8000/docs

## 本地开发

后端：

```bash
cd /root/a-stock-watcher/backend
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

前端：

```bash
cd /root/a-stock-watcher/frontend
npm install
npm run dev
```

## MVP 验收路径

1. 打开 Web 页面。
2. 点击“添加股票”，录入 `600519` / `贵州茅台`。
3. 点击“新建规则”，选择“涨幅超过”，阈值填 `0`。
4. 在行情看板点击“模拟刷新行情”。
5. 查看行情数据和最近提醒。

## 已保留的扩展点

- `backend/app/collectors/base.py`：采集器统一接口。
- `backend/app/collectors/mock_quote.py`：示例行情采集器。
- `backend/app/rules/engine.py`：规则判断入口。
- `backend/app/notifications/providers.py`：飞书和企业微信 Provider 初版。
- `collector_sources.parser_config`：预留 CSS Selector、XPath、JSON Path、字段映射配置。
- `ASW_AUTO_QUOTE_REFRESH_ENABLED` / `ASW_AUTO_QUOTE_REFRESH_SECONDS`：控制后端自动行情采集开关和间隔。
- `ASW_ANALYSIS_MODEL_PROVIDER`：`local`、`github` 或 `disabled`。
- `ASW_LOCAL_MODEL_BASE_URL` / `ASW_LOCAL_MODEL_NAME`：本地模型地址和模型名，默认 `http://127.0.0.1:11434` / `qwen2.5:7b`。
- `ASW_GITHUB_MODELS_TOKEN` / `ASW_GITHUB_MODELS_MODEL`：GitHub Models token 和模型名。Token 只放环境变量，不要写入代码。
- `ASW_ANALYSIS_CACHE_TTL_SECONDS`：模型分析缓存时间，默认 900 秒。
- `ASW_NOTIFICATION_COOLDOWN_SECONDS`：通知发送去重冷却时间，默认 300 秒。

## 合规边界

系统仅用于公开数据监控和用户规则提醒，不自动下单，不承诺收益，不对外分发未授权行情数据，不绕过登录、验证码、付费墙或访问控制。
