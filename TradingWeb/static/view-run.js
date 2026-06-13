import { api } from './api.js';
import {
  esc, fmtTime, statusBadge, decisionBadge, renderMarkdown,
  orderedAgents, AGENT_LABELS, AGENT_STATUS_LABELS, REPORT_TABS, skeletonHtml,
} from './util.js';

const POLL_MS = 2000;
const LOG_TRUNCATE = 240;
const LS_LOG_COLLAPSED = 'ta.logCollapsed';

const KIND_META = {
  message:       { icon: '💬', label: '消息' },
  tool_call:     { icon: '🛠', label: '工具调用' },
  report_update: { icon: '📄', label: '报告更新' },
  status:        { icon: '⚙', label: '状态' },
  error:         { icon: '⚠', label: '错误' },
  info:          { icon: 'ℹ', label: '信息' },
};

export function render(root, id) {
  let destroyed = false;
  let timer = null;
  let lastStepId = 0;
  let run = null;
  let reports = {};
  let agentStatuses = {};
  let status = '';
  let decision = null;
  let activeTab = null;
  let stepCount = 0;
  let feedHover = false;
  let renderedTabContent = {}; // tab key -> 已渲染的原始 md（避免重复渲染）

  root.innerHTML = skeletonHtml(5);

  init();

  async function init() {
    try {
      run = await api(`/api/runs/${encodeURIComponent(id)}`);
    } catch (e) {
      if (destroyed) return;
      root.innerHTML = `<div class="view-enter">
        <div class="banner banner-error">加载失败：${esc(e.message)}</div>
        <a class="btn" href="#/runs">返回历史记录</a></div>`;
      return;
    }
    if (destroyed) return;
    reports = run.reports || {};
    agentStatuses = run.agent_statuses || {};
    status = run.status;
    decision = run.decision || null;
    activeTab = pickDefaultTab();
    drawShell();
    renderHeader();
    renderAgents();
    renderTabs();
    renderTabContent();
    renderErrorBlock();
    // 拉取日志：进行中的任务进入轮询；已结束的任务只拉一次
    if (isActive()) schedulePoll(0);
    else fetchStepsOnce();
  }

  function isActive() {
    return status === 'pending' || status === 'running';
  }

  function pickDefaultTab() {
    for (const [key] of REPORT_TABS) {
      if (reports[key]) return key;
    }
    return REPORT_TABS[0][0];
  }

  /* ============ 骨架 ============ */

  function drawShell() {
    const collapsed = localStorage.getItem(LS_LOG_COLLAPSED) === '1';
    root.innerHTML = `
      <div class="view-enter">
        <div class="run-header">
          <span class="run-ticker">${esc(run.ticker)}</span>
          <span class="run-date">${esc(run.analysis_date)}</span>
          ${run.asset_type === 'crypto' ? '<span class="crypto-badge">加密资产</span>' : ''}
          <span id="run-status"></span>
          <span id="run-decision"></span>
          <span class="nav-spacer"></span>
          <span id="offline-banner" class="badge badge-amber hidden"><span class="dot pulse"></span>连接中断，正在重试…</span>
        </div>
        <div id="run-error-block"></div>
        <div class="run-layout">
          <aside class="card agent-board">
            <h3 class="panel-title">智能体状态</h3>
            <div class="agent-rows" id="agent-rows"></div>
          </aside>
          <section style="min-width:0">
            <div class="card report-panel">
              <div class="tabs" id="tabs"></div>
              <div class="tab-content" id="tab-content"></div>
            </div>
            <div class="card log-panel ${collapsed ? 'collapsed' : ''}" id="log-panel">
              <div class="log-header" id="log-header">
                <span class="log-caret">▼</span>
                <h3 class="panel-title">执行日志</h3>
                <span class="log-count" id="log-count">0 条</span>
                <label class="log-autoscroll" id="log-autoscroll-wrap">
                  <input type="checkbox" id="log-autoscroll" checked>自动滚动
                </label>
              </div>
              <div class="log-feed" id="log-feed"></div>
            </div>
          </section>
        </div>
      </div>`;

    const logHeader = root.querySelector('#log-header');
    const logPanel = root.querySelector('#log-panel');
    logHeader.addEventListener('click', (e) => {
      if (e.target.closest('#log-autoscroll-wrap')) return;
      logPanel.classList.toggle('collapsed');
      localStorage.setItem(LS_LOG_COLLAPSED, logPanel.classList.contains('collapsed') ? '1' : '0');
    });
    const feed = root.querySelector('#log-feed');
    feed.addEventListener('mouseenter', () => { feedHover = true; });
    feed.addEventListener('mouseleave', () => { feedHover = false; });
  }

  /* ============ 局部渲染 ============ */

  function renderHeader() {
    const st = root.querySelector('#run-status');
    const de = root.querySelector('#run-decision');
    if (st) st.innerHTML = statusBadge(status);
    if (de) de.innerHTML = decision ? decisionBadge(decision) : '';
  }

  function renderAgents() {
    const box = root.querySelector('#agent-rows');
    if (!box) return;
    box.innerHTML = orderedAgents(agentStatuses).map(([key, st]) => {
      const label = AGENT_LABELS[key] || key;
      const stLabel = AGENT_STATUS_LABELS[st] || st;
      return `<div class="agent-row ${esc(st)}">
        <span class="agent-name">${esc(label)}</span>
        <span class="agent-pill ${esc(st)}"><span class="dot"></span>${esc(stLabel)}</span>
      </div>`;
    }).join('');
  }

  function renderTabs() {
    const box = root.querySelector('#tabs');
    if (!box) return;
    box.innerHTML = REPORT_TABS.map(([key, label]) => {
      const has = !!reports[key];
      return `<button class="tab ${key === activeTab ? 'active' : ''}" data-tab="${esc(key)}"
        ${has ? '' : 'disabled title="暂无内容"'}>${esc(label)}</button>`;
    }).join('');
    box.querySelectorAll('.tab').forEach((btn) => {
      btn.addEventListener('click', () => {
        activeTab = btn.dataset.tab;
        renderTabs();
        renderTabContent();
      });
    });
  }

  function renderTabContent() {
    const box = root.querySelector('#tab-content');
    if (!box) return;
    const md = reports[activeTab];
    if (!md) {
      box.innerHTML = `<div class="tab-empty">该报告尚未生成${isActive() ? '，分析进行中…' : ''}</div>`;
      renderedTabContent[activeTab] = null;
      return;
    }
    if (renderedTabContent[activeTab] === md) return; // 内容未变化，跳过重渲染
    box.innerHTML = `<div class="md-body">${renderMarkdown(md)}</div>`;
    renderedTabContent[activeTab] = md;
  }

  function renderErrorBlock() {
    const box = root.querySelector('#run-error-block');
    if (!box) return;
    if (status !== 'error' || !run || !run.error) { box.innerHTML = ''; return; }
    const text = String(run.error);
    const firstLine = text.split('\n')[0];
    box.innerHTML = `
      <div class="card error-block" id="error-block">
        <div class="error-block-title">⚠ 分析执行失败</div>
        <div class="error-summary">${esc(firstLine)}</div>
        <pre class="error-trace">${esc(text)}</pre>
        <button class="btn btn-sm btn-ghost error-toggle" id="error-toggle">展开</button>
      </div>`;
    const block = box.querySelector('#error-block');
    const toggle = box.querySelector('#error-toggle');
    toggle.addEventListener('click', () => {
      block.classList.toggle('expanded');
      toggle.textContent = block.classList.contains('expanded') ? '收起' : '展开';
    });
  }

  /* ============ 日志 ============ */

  function appendSteps(steps) {
    if (!steps || !steps.length) return;
    const feed = root.querySelector('#log-feed');
    if (!feed) return;
    const frag = document.createDocumentFragment();
    for (const s of steps) {
      frag.appendChild(buildStepNode(s));
    }
    feed.appendChild(frag);
    stepCount += steps.length;
    const count = root.querySelector('#log-count');
    if (count) count.textContent = `${stepCount} 条`;
    const auto = root.querySelector('#log-autoscroll');
    if (auto && auto.checked && !feedHover) feed.scrollTop = feed.scrollHeight;
  }

  function buildStepNode(s) {
    const kind = KIND_META[s.kind] || KIND_META.info;
    const item = document.createElement('div');
    item.className = `log-item k-${s.kind || 'info'}`;

    const ts = document.createElement('span');
    ts.className = 'log-ts';
    ts.textContent = fmtTime(s.ts);

    const k = document.createElement('span');
    k.className = `log-kind k-${s.kind || 'info'}`;
    k.textContent = `${kind.icon} ${kind.label}`;

    const agent = document.createElement('span');
    agent.className = 'log-agent';
    agent.textContent = s.agent ? (AGENT_LABELS[s.agent] || s.agent) : '';
    if (s.agent) agent.title = s.agent;

    const content = document.createElement('span');
    content.className = 'log-content';
    const full = String(s.content == null ? '' : s.content);
    if (full.length > LOG_TRUNCATE) {
      content.classList.add('truncated');
      content.textContent = full.slice(0, LOG_TRUNCATE) + '…';
      const hint = document.createElement('span');
      hint.className = 'expand-hint';
      hint.textContent = '[展开]';
      content.appendChild(hint);
      content.addEventListener('click', () => {
        const expanded = content.classList.toggle('expanded');
        if (expanded) {
          content.textContent = full;
        } else {
          content.textContent = full.slice(0, LOG_TRUNCATE) + '…';
          content.appendChild(hint);
        }
      });
    } else {
      content.textContent = full;
    }

    item.append(ts, k, agent, content);
    return item;
  }

  async function fetchStepsOnce() {
    try {
      const d = await api(`/api/runs/${encodeURIComponent(id)}/steps?after_id=0`);
      if (destroyed) return;
      appendSteps(d.steps);
    } catch (e) { /* 历史日志加载失败时静默 */ }
  }

  /* ============ 轮询 ============ */

  function schedulePoll(delay = POLL_MS) {
    if (destroyed) return;
    timer = setTimeout(poll, delay);
  }

  async function poll() {
    if (destroyed) return;
    let d;
    try {
      d = await api(`/api/runs/${encodeURIComponent(id)}/steps?after_id=${lastStepId}`);
    } catch (e) {
      setOffline(true);
      schedulePoll(POLL_MS);
      return;
    }
    if (destroyed) return;
    setOffline(false);

    if (d.steps && d.steps.length) {
      appendSteps(d.steps);
      lastStepId = d.steps[d.steps.length - 1].id;
    }
    // 合并报告（仅更新变化的 tab）
    let reportsChanged = false;
    if (d.reports) {
      for (const [key, val] of Object.entries(d.reports)) {
        if (val && reports[key] !== val) { reports[key] = val; reportsChanged = true; }
      }
    }
    if (d.agent_statuses) { agentStatuses = d.agent_statuses; renderAgents(); }
    const statusChanged = d.status && d.status !== status;
    if (statusChanged) status = d.status;
    if (d.decision && d.decision !== decision) decision = d.decision;
    renderHeader();
    if (reportsChanged) {
      renderTabs();
      renderTabContent();
    }

    if (isActive()) {
      schedulePoll(POLL_MS);
    } else {
      // 任务结束：补取完整详情（错误信息 / 结束时间等）
      try {
        run = await api(`/api/runs/${encodeURIComponent(id)}`);
        if (destroyed) return;
        reports = Object.assign({}, reports, run.reports || {});
        decision = run.decision || decision;
        status = run.status;
        agentStatuses = run.agent_statuses || agentStatuses;
        renderHeader();
        renderAgents();
        renderTabs();
        renderTabContent();
        renderErrorBlock();
      } catch (e) { /* 忽略 */ }
    }
  }

  function setOffline(off) {
    const b = root.querySelector('#offline-banner');
    if (b) b.classList.toggle('hidden', !off);
  }

  return () => {
    destroyed = true;
    if (timer) clearTimeout(timer);
  };
}
