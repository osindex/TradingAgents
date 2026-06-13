/** 通用工具：转义、格式化、状态映射、markdown 渲染 */

export function esc(s) {
  return String(s == null ? '' : s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

/** ISO-8601 UTC -> 本地时间（zh-CN） */
export function fmtDateTime(iso) {
  if (!iso) return '—';
  const d = parseUtc(iso);
  if (isNaN(d.getTime())) return String(iso);
  return d.toLocaleString('zh-CN', {
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false,
  });
}

export function fmtTime(iso) {
  if (!iso) return '';
  const d = parseUtc(iso);
  if (isNaN(d.getTime())) return String(iso);
  return d.toLocaleTimeString('zh-CN', {
    hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false,
  });
}

function parseUtc(iso) {
  let s = String(iso);
  // 无时区后缀的 ISO 字符串按 UTC 处理
  if (!/[zZ]|[+-]\d{2}:?\d{2}$/.test(s)) s += 'Z';
  return new Date(s);
}

/** 耗时 created_at -> finished_at */
export function fmtDuration(startIso, endIso) {
  if (!startIso || !endIso) return '—';
  const ms = parseUtc(endIso) - parseUtc(startIso);
  if (!isFinite(ms) || ms < 0) return '—';
  const sec = Math.round(ms / 1000);
  if (sec < 60) return `${sec}秒`;
  const min = Math.floor(sec / 60);
  if (min < 60) return `${min}分${sec % 60}秒`;
  return `${Math.floor(min / 60)}小时${min % 60}分`;
}

export function isCryptoTicker(ticker) {
  return /-(USD|USDT|USDC|BTC|ETH)$/i.test(String(ticker || '').trim());
}

/* ---------------- 状态 / 决策 ---------------- */

export const RUN_STATUS = {
  pending:   { label: '排队中', cls: 'badge-grey',  pulse: false },
  running:   { label: '运行中', cls: 'badge-cyan',  pulse: true },
  completed: { label: '已完成', cls: 'badge-green', pulse: false },
  error:     { label: '失败',   cls: 'badge-red',   pulse: false },
};

export function statusBadge(status) {
  const meta = RUN_STATUS[status] || { label: status || '未知', cls: 'badge-grey', pulse: false };
  return `<span class="badge ${meta.cls}"><span class="dot${meta.pulse ? ' pulse' : ''}"></span>${esc(meta.label)}</span>`;
}

export function decisionBadge(decision) {
  if (!decision) return '';
  const d = String(decision).toUpperCase();
  let cls = 'badge-grey';
  if (/SELL|卖出/.test(d)) cls = 'badge-red';
  else if (/BUY|买入/.test(d)) cls = 'badge-green';
  else if (/HOLD|持有/.test(d)) cls = 'badge-amber';
  return `<span class="badge ${cls}" title="最终决策"><span class="dot"></span>${esc(decision)}</span>`;
}

/* ---------------- Agent 映射 ---------------- */

export const AGENT_LABELS = {
  'Market Analyst': '市场分析师',
  'Social Analyst': '情绪分析师',
  'Social Media Analyst': '情绪分析师',
  'News Analyst': '新闻分析师',
  'Fundamentals Analyst': '基本面分析师',
  'Bull Researcher': '多头研究员',
  'Bear Researcher': '空头研究员',
  'Research Manager': '研究经理',
  'Trader': '交易员',
  'Aggressive Analyst': '激进风控',
  'Risky Analyst': '激进风控',
  'Neutral Analyst': '中立风控',
  'Conservative Analyst': '保守风控',
  'Safe Analyst': '保守风控',
  'Portfolio Manager': '投资组合经理',
};

export const AGENT_ORDER = [
  'Market Analyst', 'Social Analyst', 'Social Media Analyst', 'News Analyst',
  'Fundamentals Analyst', 'Bull Researcher', 'Bear Researcher', 'Research Manager',
  'Trader', 'Aggressive Analyst', 'Risky Analyst', 'Neutral Analyst',
  'Conservative Analyst', 'Safe Analyst', 'Portfolio Manager',
];

export const AGENT_STATUS_LABELS = {
  pending: '等待',
  in_progress: '进行中',
  completed: '已完成',
  error: '出错',
};

/** 按固定顺序返回 [key, status] 列表，仅包含响应中出现的 agent */
export function orderedAgents(agentStatuses) {
  if (!agentStatuses) return [];
  const keys = Object.keys(agentStatuses);
  const ordered = AGENT_ORDER.filter((k) => keys.includes(k));
  for (const k of keys) if (!ordered.includes(k)) ordered.push(k);
  return ordered.map((k) => [k, agentStatuses[k]]);
}

/* ---------------- 报告 Tab ---------------- */

export const REPORT_TABS = [
  ['market_report', '市场分析'],
  ['sentiment_report', '情绪分析'],
  ['news_report', '新闻分析'],
  ['fundamentals_report', '基本面分析'],
  ['investment_plan', '研究决议'],
  ['trader_investment_plan', '交易计划'],
  ['final_trade_decision', '最终决策'],
];

/* ---------------- Markdown ---------------- */

/** 渲染 markdown 为安全 HTML；marked 不可用时降级为转义后的 <pre> */
export function renderMarkdown(md) {
  const text = String(md == null ? '' : md);
  if (typeof window !== 'undefined' && window.marked && typeof window.marked.parse === 'function') {
    try {
      return sanitizeHtml(window.marked.parse(text));
    } catch (e) {
      /* fall through to fallback */
    }
  }
  return `<pre class="md-fallback">${esc(text)}</pre>`;
}

function sanitizeHtml(html) {
  const tpl = document.createElement('template');
  tpl.innerHTML = html;
  tpl.content
    .querySelectorAll('script, style, iframe, object, embed, link, meta, form, base')
    .forEach((n) => n.remove());
  tpl.content.querySelectorAll('*').forEach((el) => {
    for (const attr of [...el.attributes]) {
      const name = attr.name.toLowerCase();
      if (name.startsWith('on')) el.removeAttribute(attr.name);
      else if ((name === 'href' || name === 'src' || name === 'xlink:href')
               && /^\s*(javascript|data|vbscript):/i.test(attr.value)) {
        el.removeAttribute(attr.name);
      }
    }
    if (el.tagName === 'A') {
      el.setAttribute('target', '_blank');
      el.setAttribute('rel', 'noopener noreferrer');
    }
  });
  return tpl.innerHTML;
}

/* ---------------- 通用 UI 片段 ---------------- */

export function loadingHtml(text = '加载中…') {
  return `<div class="loading-center"><div class="spinner"></div><div>${esc(text)}</div></div>`;
}

export function skeletonHtml(rows = 4) {
  let h = '<div class="view-enter">';
  for (let i = 0; i < rows; i++) {
    const w = 100 - (i % 3) * 18;
    h += `<div class="skeleton" style="height:46px;margin-bottom:12px;width:${w}%"></div>`;
  }
  return h + '</div>';
}
