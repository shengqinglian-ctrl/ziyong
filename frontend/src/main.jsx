import React, { useEffect, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { Alert, Button, Card, ConfigProvider, Form, Input, InputNumber, Layout, Menu, Modal, Popconfirm, Select, Space, Table, Tag, Typography, message } from 'antd';
import { Activity, Bell, Bot, Database, MessageSquare, Newspaper, RefreshCw, Send, Settings, Star } from 'lucide-react';
import 'antd/dist/reset.css';
import './style.css';

const API_BASE = import.meta.env.VITE_API_BASE || '';
const AUTO_REFRESH_INTERVAL_MS = 30000;

async function api(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
    ...options,
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || response.statusText);
  }
  return response.json();
}

function App() {
  const [active, setActive] = useState('dashboard');
  const [quotes, setQuotes] = useState([]);
  const [capitalFlows, setCapitalFlows] = useState([]);
  const [watchlists, setWatchlists] = useState([]);
  const [rules, setRules] = useState([]);
  const [events, setEvents] = useState([]);
  const [notificationChannels, setNotificationChannels] = useState([]);
  const [collectors, setCollectors] = useState([]);
  const [collectorStatus, setCollectorStatus] = useState(null);
  const [aiStatus, setAiStatus] = useState(null);
  const [info, setInfo] = useState([]);
  const [infoAnalysis, setInfoAnalysis] = useState([]);
  const [chatMessages, setChatMessages] = useState([
    { role: 'assistant', content: '你可以问我自选股行情、资金流、提醒记录、信息中心摘要，或系统配置相关问题。' },
  ]);
  const [chatQuestion, setChatQuestion] = useState('');
  const [chatLoading, setChatLoading] = useState(false);
  const [chatProvider, setChatProvider] = useState(null);
  const [chatModel, setChatModel] = useState('');
  const [loading, setLoading] = useState(false);
  const [stockModal, setStockModal] = useState(false);
  const [ruleModal, setRuleModal] = useState(false);
  const [channelModal, setChannelModal] = useState(false);
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [lastRealtimeAt, setLastRealtimeAt] = useState(null);
  const latestEventIdRef = useRef(null);
  const realtimeBusyRef = useRef(false);
  const [form] = Form.useForm();
  const [ruleForm] = Form.useForm();
  const [channelForm] = Form.useForm();

  async function loadAll({ silent = false } = {}) {
    if (!silent) setLoading(true);
    try {
      const [quoteRows, flowRows, watchlistRows, ruleRows, eventRows, channelRows, collectorRows, collectorStatusRow, aiStatusRow, infoRows, analysisRows] = await Promise.all([
        api('/api/quotes/latest'),
        api('/api/capital-flow/latest'),
        api('/api/watchlists'),
        api('/api/alert-rules'),
        api('/api/alert-events'),
        api('/api/notification-channels'),
        api('/api/collectors'),
        api('/api/collectors/status'),
        api('/api/ai/status'),
        api('/api/info'),
        api('/api/info/analysis'),
      ]);
      setQuotes(quoteRows);
      setCapitalFlows(flowRows);
      setWatchlists(watchlistRows);
      setRules(ruleRows);
      setEvents(eventRows);
      setNotificationChannels(channelRows);
      setCollectors(collectorRows);
      setCollectorStatus(collectorStatusRow);
      setAiStatus(aiStatusRow);
      setInfo(infoRows);
      setInfoAnalysis(analysisRows.items || []);
      notifyNewAlert(eventRows);
    } catch (error) {
      if (!silent) message.error(`加载失败：${error.message}`);
    } finally {
      if (!silent) setLoading(false);
    }
  }

  useEffect(() => {
    loadAll();
  }, []);

  useEffect(() => {
    if (!aiStatus) return;
    const provider = chatProvider || aiStatus.provider || 'local';
    const model = chatModel || (provider === 'github' ? aiStatus.github_model : aiStatus.local_model);
    setChatProvider(provider);
    setChatModel(model || '');
  }, [aiStatus]);

  useEffect(() => {
    if (!autoRefresh) return undefined;
    const timer = window.setInterval(() => {
      loadRealtime({ silent: true });
    }, AUTO_REFRESH_INTERVAL_MS);
    return () => window.clearInterval(timer);
  }, [autoRefresh]);

  function notifyNewAlert(eventRows) {
    if (!eventRows.length) return;
    const newest = eventRows[0];
    if (latestEventIdRef.current === null) {
      latestEventIdRef.current = newest.id;
      return;
    }
    if (newest.id > latestEventIdRef.current) {
      latestEventIdRef.current = newest.id;
      if (newest.severity === 'urgent') {
        message.error(`紧急提醒：${newest.title}`, 8);
      } else if (newest.severity === 'important') {
        message.warning(`重要提醒：${newest.title}`, 8);
      }
    }
  }

  async function ensureDefaultWatchlist() {
    if (watchlists.length > 0) return watchlists[0].id;
    const created = await api('/api/watchlists', { method: 'POST', body: JSON.stringify({ name: '默认自选' }) });
    setWatchlists([created]);
    return created.id;
  }

  async function addStock(values) {
    const watchlistId = await ensureDefaultWatchlist();
    await api(`/api/watchlists/${watchlistId}/stocks`, { method: 'POST', body: JSON.stringify(values) });
    message.success('已添加自选股');
    setStockModal(false);
    form.resetFields();
    await loadAll();
  }

  async function deleteStock(stockCode) {
    const watchlistId = watchlists[0]?.id;
    if (!watchlistId) return;
    await api(`/api/watchlists/${watchlistId}/stocks/${stockCode}`, { method: 'DELETE' });
    message.success('已删除自选股');
    await loadAll();
  }

  async function addRule(values) {
    const params = { value: values.value };
    await api('/api/alert-rules', {
      method: 'POST',
      body: JSON.stringify({ ...values, params }),
    });
    message.success('已创建提醒规则');
    setRuleModal(false);
    ruleForm.resetFields();
    await loadAll();
  }

  async function addNotificationChannel(values) {
    await api('/api/notification-channels', { method: 'POST', body: JSON.stringify(values) });
    message.success('已添加通知通道');
    setChannelModal(false);
    channelForm.resetFields();
    await loadAll();
  }

  async function deleteNotificationChannel(id) {
    await api(`/api/notification-channels/${id}`, { method: 'DELETE' });
    message.success('已删除通知通道');
    await loadAll();
  }

  async function testNotificationChannel(id) {
    await api(`/api/notification-channels/${id}/test`, { method: 'POST' });
    message.success('测试消息已发送');
    await loadAll();
  }

  async function loadRealtime({ silent = true } = {}) {
    try {
      const [quoteRows, flowRows, eventRows, collectorStatusRow] = await Promise.all([
        api('/api/quotes/latest'),
        api('/api/capital-flow/latest'),
        api('/api/alert-events'),
        api('/api/collectors/status'),
      ]);
      setQuotes(quoteRows);
      setCapitalFlows(flowRows);
      setEvents(eventRows);
      setCollectorStatus(collectorStatusRow);
      notifyNewAlert(eventRows);
      setLastRealtimeAt(new Date());
    } catch (error) {
      if (!silent) message.error(`实时状态加载失败：${error.message}`);
    }
  }

  async function refreshQuotes({ silent = false } = {}) {
    if (realtimeBusyRef.current) return;
    realtimeBusyRef.current = true;
    if (!silent) setLoading(true);
    try {
      await api('/api/quotes/refresh', { method: 'POST' });
      setLastRealtimeAt(new Date());
      await loadAll({ silent });
      if (!silent) message.success('已刷新真实行情并执行规则');
    } catch (error) {
      if (!silent) message.error(`刷新失败：${error.message}`);
      await loadRealtime({ silent: true });
    } finally {
      realtimeBusyRef.current = false;
      if (!silent) setLoading(false);
    }
  }

  async function sendChatQuestion() {
    const question = chatQuestion.trim();
    if (!question || chatLoading) return;
    const nextMessages = [...chatMessages, { role: 'user', content: question }];
    setChatMessages(nextMessages);
    setChatQuestion('');
    setChatLoading(true);
    try {
      const result = await api('/api/ai/chat', { method: 'POST', body: JSON.stringify({ question, provider: chatProvider, model: chatModel }) });
      setChatMessages([...nextMessages, { role: 'assistant', content: result.answer, meta: `${result.provider} · ${result.model}` }]);
    } catch (error) {
      setChatMessages([...nextMessages, { role: 'assistant', content: `调用 AI 失败：${error.message}` }]);
    } finally {
      setChatLoading(false);
    }
  }

  function changeChatProvider(provider) {
    setChatProvider(provider);
    setChatModel(provider === 'github' ? (aiStatus?.github_model || '') : (aiStatus?.local_model || ''));
  }

  const menuItems = [
    { key: 'dashboard', icon: <Activity size={18} />, label: '行情看板' },
    { key: 'rules', icon: <Bell size={18} />, label: '提醒规则' },
    { key: 'notifications', icon: <MessageSquare size={18} />, label: '通知通道' },
    { key: 'info', icon: <Newspaper size={18} />, label: '信息中心' },
    { key: 'ai-chat', icon: <Bot size={18} />, label: 'AI 问答' },
    { key: 'collectors', icon: <Database size={18} />, label: '采集器' },
    { key: 'settings', icon: <Settings size={18} />, label: '系统状态' },
  ];

  return (
    <ConfigProvider theme={{ token: { colorPrimary: '#1677ff', borderRadius: 6 } }}>
      <Layout className="app-shell">
        <Layout.Sider width={220} breakpoint="lg" collapsedWidth="0">
          <div className="brand"><Star size={20} /> A-Stock Watcher</div>
          <Menu theme="dark" mode="inline" selectedKeys={[active]} items={menuItems} onClick={({ key }) => setActive(key)} />
        </Layout.Sider>
        <Layout>
          <Layout.Header className="topbar">
            <Typography.Title level={4}>A 股实时分析与信息提醒</Typography.Title>
            <Space>
              <Button icon={<RefreshCw size={16} />} onClick={() => loadAll()} loading={loading}>刷新</Button>
              <Button type="primary" onClick={() => setStockModal(true)}>添加股票</Button>
              <Button onClick={() => setRuleModal(true)}>新建规则</Button>
              <Button onClick={() => setChannelModal(true)}>通知通道</Button>
            </Space>
          </Layout.Header>
          <Layout.Content className="content">
            <Alert className="risk" type="warning" showIcon message="本系统仅根据用户配置规则、公开数据和公开信息进行监控提醒，不构成投资建议。" />
            {active === 'dashboard' && <Dashboard quotes={quotes} capitalFlows={capitalFlows} events={events} loading={loading} onRefresh={refreshQuotes} onDeleteStock={deleteStock} autoRefresh={autoRefresh} onToggleAutoRefresh={setAutoRefresh} lastRealtimeAt={lastRealtimeAt} />}
            {active === 'rules' && <Rules rules={rules} />}
            {active === 'notifications' && <NotificationChannels channels={notificationChannels} onCreate={() => setChannelModal(true)} onTest={testNotificationChannel} onDelete={deleteNotificationChannel} />}
            {active === 'info' && <InfoCenter info={info} analysis={infoAnalysis} aiStatus={aiStatus} />}
            {active === 'ai-chat' && <AiChat aiStatus={aiStatus} messages={chatMessages} question={chatQuestion} provider={chatProvider} model={chatModel} loading={chatLoading} onProviderChange={changeChatProvider} onModelChange={setChatModel} onQuestionChange={setChatQuestion} onSend={sendChatQuestion} />}
            {active === 'collectors' && <Collectors collectors={collectors} status={collectorStatus} />}
            {active === 'settings' && <SystemStatus watchlists={watchlists} rules={rules} collectors={collectors} events={events} />}
          </Layout.Content>
        </Layout>
      </Layout>

      <Modal title="添加自选股" open={stockModal} onCancel={() => setStockModal(false)} onOk={() => form.submit()}>
        <Form form={form} layout="vertical" onFinish={addStock}>
          <Form.Item name="code" label="股票代码" rules={[{ required: true }]}><Input placeholder="600519 或 600519.SH" /></Form.Item>
          <Form.Item name="focus_level" label="关注级别" initialValue="normal"><Select options={[{ value: 'normal', label: '普通' }, { value: 'important', label: '重要' }, { value: 'urgent', label: '紧急' }]} /></Form.Item>
          <Form.Item name="note" label="备注"><Input.TextArea rows={3} /></Form.Item>
        </Form>
      </Modal>

      <Modal title="新建提醒规则" open={ruleModal} onCancel={() => setRuleModal(false)} onOk={() => ruleForm.submit()}>
        <Form form={ruleForm} layout="vertical" onFinish={addRule}>
          <Form.Item name="name" label="规则名称" rules={[{ required: true }]}><Input placeholder="涨幅超过 3%" /></Form.Item>
          <Form.Item name="stock_code" label="股票代码"><Input placeholder="留空代表全部自选股" /></Form.Item>
          <Form.Item name="rule_type" label="规则类型" initialValue="change_percent_above" rules={[{ required: true }]}>
            <Select options={[
              { value: 'price_above', label: '价格大于' },
              { value: 'price_below', label: '价格小于' },
              { value: 'change_percent_above', label: '涨幅超过' },
              { value: 'change_percent_below', label: '跌幅超过' },
              { value: 'turnover_above', label: '成交额超过' },
            ]} />
          </Form.Item>
          <Form.Item name="value" label="阈值" rules={[{ required: true }]}><InputNumber className="full" /></Form.Item>
          <Form.Item name="severity" label="提醒等级" initialValue="normal"><Select options={[{ value: 'normal', label: '普通' }, { value: 'important', label: '重要' }, { value: 'urgent', label: '紧急' }]} /></Form.Item>
          <Form.Item name="cooldown_seconds" label="冷却秒数" initialValue={300}><InputNumber className="full" /></Form.Item>
        </Form>
      </Modal>

      <Modal title="添加通知通道" open={channelModal} onCancel={() => setChannelModal(false)} onOk={() => channelForm.submit()}>
        <Form form={channelForm} layout="vertical" onFinish={addNotificationChannel}>
          <Form.Item name="name" label="名称" rules={[{ required: true }]}><Input placeholder="飞书群提醒" /></Form.Item>
          <Form.Item name="provider" label="平台" initialValue="feishu" rules={[{ required: true }]}>
            <Select options={[
              { value: 'feishu', label: '飞书机器人' },
              { value: 'wecom', label: '企业微信机器人' },
              { value: 'wechat', label: '微信/企业微信机器人' },
            ]} />
          </Form.Item>
          <Form.Item name="webhook_url" label="Webhook URL" rules={[{ required: true }]}><Input.Password placeholder="机器人 webhook 地址" /></Form.Item>
          <Form.Item name="min_severity" label="最低等级" initialValue="normal">
            <Select options={[{ value: 'normal', label: '普通' }, { value: 'important', label: '重要' }, { value: 'urgent', label: '紧急' }]} />
          </Form.Item>
          <Form.Item name="enabled" label="启用" initialValue={true}>
            <Select options={[{ value: true, label: '启用' }, { value: false, label: '停用' }]} />
          </Form.Item>
        </Form>
      </Modal>
    </ConfigProvider>
  );
}

function formatYi(value) {
  if (value === null || value === undefined) return '-';
  return `${(value / 100000000).toFixed(2)} 亿`;
}

function formatPercent(value) {
  if (value === null || value === undefined) return '-';
  return `${value.toFixed(2)}%`;
}

function flowClass(value) {
  if (value > 0) return 'up';
  if (value < 0) return 'down';
  return '';
}

function Dashboard({ quotes, capitalFlows, events, loading, onRefresh, onDeleteStock, autoRefresh, onToggleAutoRefresh, lastRealtimeAt }) {
  const flowByCode = Object.fromEntries(capitalFlows.map(flow => [flow.stock_code, flow]));
  const quoteRows = quotes.map(quote => ({ ...quote, capital_flow: flowByCode[quote.stock_code] }));
  return (
    <Space direction="vertical" size={16} className="full">
      <Alert
        className="realtime-bar"
        type={autoRefresh ? 'success' : 'info'}
        showIcon
        message={autoRefresh ? `实时监控中，每 30 秒刷新一次${lastRealtimeAt ? `，上次刷新 ${lastRealtimeAt.toLocaleTimeString()}` : ''}` : '实时监控已暂停'}
        action={<Button size="small" onClick={() => onToggleAutoRefresh(!autoRefresh)}>{autoRefresh ? '暂停' : '开启'}</Button>}
      />
      <Card title="实时行情" extra={<Button onClick={() => onRefresh()} loading={loading}>刷新真实行情</Button>}>
        <Table rowKey="stock_code" dataSource={quoteRows} pagination={false} columns={[
          { title: '代码', dataIndex: 'stock_code' },
          { title: '名称', dataIndex: 'name' },
          { title: '最新价', dataIndex: 'latest_price' },
          { title: '涨跌幅', dataIndex: 'change_percent', render: v => <span className={v >= 0 ? 'up' : 'down'}>{v ?? '-'}%</span> },
          { title: '成交额', dataIndex: 'turnover', render: v => v ? `${(v / 100000000).toFixed(2)} 亿` : '-' },
          { title: '主力净流入', dataIndex: 'capital_flow', render: flow => <span className={flowClass(flow?.main_net_inflow)}>{formatYi(flow?.main_net_inflow)}</span> },
          { title: '主力净占比', dataIndex: 'capital_flow', render: flow => <span className={flowClass(flow?.main_net_ratio)}>{formatPercent(flow?.main_net_ratio)}</span> },
          { title: '数据源', dataIndex: 'source_name' },
          { title: '状态', dataIndex: 'delay_status', render: v => <Tag>{v}</Tag> },
          { title: '更新时间', dataIndex: 'quote_time', render: v => new Date(v).toLocaleString() },
          {
            title: '操作',
            render: (_, row) => (
              <Popconfirm title="删除这只自选股？" okText="删除" cancelText="取消" onConfirm={() => onDeleteStock(row.stock_code)}>
                <Button size="small" danger>删除</Button>
              </Popconfirm>
            ),
          },
        ]} />
      </Card>
      <Card title="实时资金流向">
        <Table rowKey="stock_code" dataSource={capitalFlows} pagination={false} columns={[
          { title: '代码', dataIndex: 'stock_code' },
          { title: '名称', dataIndex: 'name' },
          { title: '主力净流入', dataIndex: 'main_net_inflow', render: v => <span className={flowClass(v)}>{formatYi(v)}</span> },
          { title: '净占比', dataIndex: 'main_net_ratio', render: v => <span className={flowClass(v)}>{formatPercent(v)}</span> },
          { title: '超大单', dataIndex: 'super_large_net_inflow', render: v => <span className={flowClass(v)}>{formatYi(v)}</span> },
          { title: '大单', dataIndex: 'large_net_inflow', render: v => <span className={flowClass(v)}>{formatYi(v)}</span> },
          { title: '中单', dataIndex: 'medium_net_inflow', render: v => <span className={flowClass(v)}>{formatYi(v)}</span> },
          { title: '小单', dataIndex: 'small_net_inflow', render: v => <span className={flowClass(v)}>{formatYi(v)}</span> },
          { title: '5日主力', dataIndex: 'five_day_main_net_inflow', render: v => <span className={flowClass(v)}>{formatYi(v)}</span> },
          { title: '更新时间', dataIndex: 'flow_time', render: v => new Date(v).toLocaleString() },
        ]} />
      </Card>
      <Card title="最近提醒">
        <Table rowKey="id" dataSource={events} pagination={{ pageSize: 5 }} columns={[
          { title: '标题', dataIndex: 'title' },
          { title: '等级', dataIndex: 'severity', render: v => <Tag color={v === 'urgent' ? 'red' : v === 'important' ? 'orange' : 'blue'}>{v}</Tag> },
          { title: '股票', dataIndex: 'stock_code' },
          { title: '状态', dataIndex: 'send_status' },
          { title: '时间', dataIndex: 'triggered_at', render: v => new Date(v).toLocaleString() },
        ]} />
      </Card>
    </Space>
  );
}

function Rules({ rules }) {
  return <Card title="提醒规则"><Table rowKey="id" dataSource={rules} columns={[
    { title: '名称', dataIndex: 'name' },
    { title: '股票', dataIndex: 'stock_code', render: v => v || '全部' },
    { title: '类型', dataIndex: 'rule_type' },
    { title: '参数', dataIndex: 'params', render: v => JSON.stringify(v) },
    { title: '等级', dataIndex: 'severity' },
    { title: '冷却', dataIndex: 'cooldown_seconds', render: v => `${v}s` },
  ]} /></Card>;
}

function NotificationChannels({ channels, onCreate, onTest, onDelete }) {
  return (
    <Card title="通知通道" extra={<Button type="primary" onClick={onCreate}>添加通道</Button>}>
      <Table rowKey="id" dataSource={channels} columns={[
        { title: '名称', dataIndex: 'name' },
        { title: '平台', dataIndex: 'provider', render: v => <Tag>{v}</Tag> },
        { title: 'Webhook', dataIndex: 'webhook_url_masked' },
        { title: '最低等级', dataIndex: 'min_severity' },
        { title: '启用', dataIndex: 'enabled', render: v => <Tag color={v ? 'green' : 'default'}>{v ? '启用' : '停用'}</Tag> },
        {
          title: '操作',
          render: (_, row) => (
            <Space>
              <Button size="small" onClick={() => onTest(row.id)}>测试</Button>
              <Button size="small" danger onClick={() => onDelete(row.id)}>删除</Button>
            </Space>
          ),
        },
      ]} />
    </Card>
  );
}

function InfoCenter({ info, analysis, aiStatus }) {
  return (
    <Space direction="vertical" size={16} className="full">
      <Card title="信息分析" extra={<Tag>{aiStatus?.enabled ? `${aiStatus.provider} 模型增强` : '规则分析'}</Tag>}>
        <div className="analysis-grid">
          {analysis.map(item => (
            <div className="analysis-panel" key={item.stock_code}>
              <div className="analysis-head">
                <div>
                  <Typography.Text strong>{item.name}</Typography.Text>
                  <Typography.Text type="secondary"> {item.stock_code}</Typography.Text>
                </div>
                <Tag color={item.change_percent >= 0 ? 'red' : 'green'}>{item.stance}</Tag>
              </div>
              <div className="analysis-metrics">
                <span>热度 {item.heat_score}</span>
                <span>最新价 {item.latest_price ?? '-'}</span>
                <span>涨跌幅 {item.change_percent ?? '-'}%</span>
              </div>
              <div className="analysis-copy analysis-focus">
                <Typography.Text type="secondary">涨跌分析</Typography.Text>
                {item.model_summary && <div className="model-summary">{item.model_summary}</div>}
                {(item.detailed_analysis || []).map(section => (
                  <div className="analysis-section" key={section.title}>
                    <Typography.Text strong>{section.title}</Typography.Text>
                    {(section.items || []).map(line => <div key={line}>{line}</div>)}
                  </div>
                ))}
              </div>
              <div className="analysis-copy">
                <Typography.Text type="secondary">驱动</Typography.Text>
                {(item.drivers || []).map(driver => <div key={driver}>{driver}</div>)}
              </div>
              <div className="analysis-copy">
                <Typography.Text type="secondary">风险</Typography.Text>
                {(item.risks || []).map(risk => <div key={risk}>{risk}</div>)}
              </div>
            </div>
          ))}
        </div>
      </Card>
      <Card title="信息中心">
        <Table rowKey="id" dataSource={info} columns={[
          { title: '标题', dataIndex: 'title' },
          { title: '来源', dataIndex: 'source_name' },
          { title: '事件', dataIndex: 'event_type' },
          { title: '重要性', dataIndex: 'importance_score' },
          { title: '标签', dataIndex: 'tags', render: tags => (tags || []).map(tag => <Tag key={tag}>{tag}</Tag>) },
          { title: '发布时间', dataIndex: 'published_at', render: v => new Date(v).toLocaleString() },
        ]} />
      </Card>
    </Space>
  );
}

function AiChat({ aiStatus, messages, question, provider, model, loading, onProviderChange, onModelChange, onQuestionChange, onSend }) {
  function handleKeyDown(event) {
    if (event.key === 'Enter' && (event.metaKey || event.ctrlKey)) {
      onSend();
    }
  }

  const providerOptions = (aiStatus?.available_providers || [
    { value: 'local', label: '本地 Ollama', configured: true },
    { value: 'github', label: 'GitHub Models', configured: aiStatus?.github_token_configured },
  ]).map(item => ({
    value: item.value,
    label: `${item.label}${item.configured ? '' : '（未配置）'}`,
  }));

  return (
    <Card
      title="AI 问答机器人"
      extra={<Tag color={provider ? 'green' : 'default'}>{provider ? `${provider} · ${model || '-'}` : 'AI 未启用'}</Tag>}
    >
      {!aiStatus?.enabled && (
        <Alert
          className="chat-alert"
          type="warning"
          showIcon
          message="需要先配置 ASW_ANALYSIS_MODEL_PROVIDER，并确保本地 Ollama 或 GitHub Models 可用。"
        />
      )}
      <div className="chat-controls">
        <Space wrap>
          <span>模型来源</span>
          <Select
            value={provider}
            options={providerOptions}
            onChange={onProviderChange}
            className="chat-provider"
          />
          <span>模型名</span>
          <Input
            value={model}
            onChange={event => onModelChange(event.target.value)}
            placeholder={provider === 'github' ? 'openai/gpt-4.1-mini' : 'qwen2.5:7b'}
            className="chat-model"
          />
        </Space>
      </div>
      <div className="chat-window">
        {messages.map((item, index) => (
          <div className={`chat-row ${item.role}`} key={`${item.role}-${index}`}>
            <div className="chat-bubble">
              <Typography.Paragraph>{item.content}</Typography.Paragraph>
              {item.meta && <Typography.Text type="secondary">{item.meta}</Typography.Text>}
            </div>
          </div>
        ))}
      </div>
      <Space.Compact className="chat-input">
        <Input.TextArea
          autoSize={{ minRows: 2, maxRows: 5 }}
          value={question}
          onChange={event => onQuestionChange(event.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="输入问题，例如：帮我总结当前自选股风险，或 600519 最近提醒有哪些？"
        />
        <Button type="primary" icon={<Send size={16} />} loading={loading} onClick={onSend}>发送</Button>
      </Space.Compact>
    </Card>
  );
}

function Collectors({ collectors, status }) {
  const quoteRefresh = status?.quote_refresh;
  const capitalFlow = status?.capital_flow;
  return (
    <Space direction="vertical" size={16} className="full">
      <Card title="自动行情采集">
        <Space wrap>
          <Tag color={quoteRefresh?.enabled ? 'green' : 'default'}>{quoteRefresh?.enabled ? '已启用' : '未启用'}</Tag>
          <span>间隔 {quoteRefresh?.interval_seconds ?? '-'}s</span>
          <span>状态 {quoteRefresh?.status ?? '-'}</span>
          <span>最近入库 {quoteRefresh?.records ?? 0} 条</span>
          <span>下次运行 {quoteRefresh?.next_run_time ? new Date(quoteRefresh.next_run_time).toLocaleString() : '-'}</span>
        </Space>
        {quoteRefresh?.last_error && <Alert className="collector-alert" type="warning" showIcon message={quoteRefresh.last_error} />}
      </Card>
      <Card title="实时资金流向采集">
        <Space wrap>
          <Tag color={capitalFlow?.status === 'ok' ? 'green' : capitalFlow?.status === 'error' ? 'orange' : 'default'}>{capitalFlow?.status ?? 'idle'}</Tag>
          <span>来源 {capitalFlow?.source ?? '-'}</span>
          <span>最近入库 {capitalFlow?.records ?? 0} 条</span>
          <span>最近成功 {capitalFlow?.last_success_at ? new Date(capitalFlow.last_success_at).toLocaleString() : '-'}</span>
        </Space>
        {capitalFlow?.last_error && <Alert className="collector-alert" type="warning" showIcon message={capitalFlow.last_error} />}
      </Card>
      <Card title="采集源管理"><Table rowKey="id" dataSource={collectors} columns={[
        { title: '名称', dataIndex: 'name' },
        { title: '类型', dataIndex: 'source_type' },
        { title: '频率', dataIndex: 'frequency_seconds', render: v => `${v}s` },
        { title: '可信度', dataIndex: 'trust_level' },
        { title: '启用', dataIndex: 'enabled', render: v => <Tag color={v ? 'green' : 'default'}>{v ? '启用' : '停用'}</Tag> },
        { title: '最近成功', dataIndex: 'last_success_at', render: v => v ? new Date(v).toLocaleString() : '-' },
        { title: '失败原因', dataIndex: 'last_failure_reason', render: v => v || '-' },
      ]} /></Card>
    </Space>
  );
}

function SystemStatus({ watchlists, rules, collectors, events }) {
  return <div className="stats">
    <Card><Typography.Title level={3}>{watchlists.length}</Typography.Title><span>自选分组</span></Card>
    <Card><Typography.Title level={3}>{rules.length}</Typography.Title><span>提醒规则</span></Card>
    <Card><Typography.Title level={3}>{collectors.length}</Typography.Title><span>采集源</span></Card>
    <Card><Typography.Title level={3}>{events.length}</Typography.Title><span>提醒事件</span></Card>
  </div>;
}

createRoot(document.getElementById('root')).render(<App />);
