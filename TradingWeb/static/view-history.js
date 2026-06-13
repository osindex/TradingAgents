import { api } from './api.js';
import { esc, fmtDateTime, fmtDuration, statusBadge, decisionBadge, skeletonHtml } from './util.js';

const LIMIT = 20;

export function render(root) {
  let destroyed = false;
  let offset = 0;
  let total = 0;

  load();

  async function load() {
    root.innerHTML = `<div class="view-enter">
      <h1 class="page-title"><span class="accent-bar"></span>历史记录</h1>
      ${skeletonHtml(6)}</div>`;
    let data;
    try {
      data = await api(`/api/runs?limit=${LIMIT}&offset=${offset}`);
    } catch (e) {
      if (destroyed) return;
      root.innerHTML = `<div class="view-enter">
        <h1 class="page-title"><span class="accent-bar"></span>历史记录</h1>
        <div class="banner banner-error">加载失败：${esc(e.message)}</div>
        <button class="btn" id="hist-retry">重试</button></div>`;
      root.querySelector('#hist-retry').addEventListener('click', load);
      return;
    }
    if (destroyed) return;
    total = data.total || 0;
    draw(data.runs || []);
  }

  function draw(runs) {
    const page = Math.floor(offset / LIMIT) + 1;
    const pages = Math.max(1, Math.ceil(total / LIMIT));

    let bodyHtml;
    if (!runs.length && offset === 0) {
      bodyHtml = `
        <div class="card empty-state view-enter">
          <div class="empty-icon">📊</div>
          <p>暂无分析记录，去新建一个吧</p>
          <a class="btn btn-primary" href="#/new">新建分析</a>
        </div>`;
    } else {
      const rows = runs.map((r) => `
        <tr data-id="${esc(String(r.id))}">
          <td class="cell-ticker">${esc(r.ticker)}${r.asset_type === 'crypto' ? '<span class="crypto-badge">加密</span>' : ''}</td>
          <td class="cell-dim mono">${esc(r.analysis_date)}</td>
          <td class="cell-model">${esc(r.llm_provider || '—')} / <span class="mono">${esc(r.deep_think_llm || '—')}</span></td>
          <td>${statusBadge(r.status)}</td>
          <td>${r.decision ? decisionBadge(r.decision) : '<span class="cell-dim">—</span>'}</td>
          <td class="cell-dim mono">${esc(fmtDateTime(r.created_at))}</td>
          <td class="cell-dim mono">${esc(fmtDuration(r.created_at, r.finished_at))}</td>
          <td class="cell-actions">
            <button class="btn btn-sm btn-ghost act-view" data-id="${esc(String(r.id))}">查看</button>
            <button class="btn btn-sm btn-danger act-del" data-id="${esc(String(r.id))}">删除</button>
          </td>
        </tr>`).join('');
      bodyHtml = `
        <div class="card table-card view-enter">
          <table class="runs-table">
            <thead><tr>
              <th>标的</th><th>分析日期</th><th>厂商 / 深度模型</th><th>状态</th>
              <th>决策</th><th>创建时间</th><th>耗时</th><th style="text-align:right">操作</th>
            </tr></thead>
            <tbody>${rows}</tbody>
          </table>
        </div>
        <div class="pager">
          <span class="pager-info">共 ${total} 条 · 第 ${page} / ${pages} 页</span>
          <button class="btn btn-sm" id="pg-prev" ${offset <= 0 ? 'disabled' : ''}>上一页</button>
          <button class="btn btn-sm" id="pg-next" ${offset + LIMIT >= total ? 'disabled' : ''}>下一页</button>
        </div>`;
    }

    root.innerHTML = `<div class="view-enter">
      <h1 class="page-title"><span class="accent-bar"></span>历史记录</h1>
      <div id="hist-error"></div>
      ${bodyHtml}</div>`;

    bind();
  }

  function bind() {
    root.querySelectorAll('.runs-table tbody tr').forEach((tr) => {
      tr.addEventListener('click', (e) => {
        if (e.target.closest('button')) return;
        location.hash = `#/runs/${tr.dataset.id}`;
      });
    });
    root.querySelectorAll('.act-view').forEach((b) =>
      b.addEventListener('click', () => { location.hash = `#/runs/${b.dataset.id}`; }));
    root.querySelectorAll('.act-del').forEach((b) =>
      b.addEventListener('click', () => onDelete(b)));
    const prev = root.querySelector('#pg-prev');
    const next = root.querySelector('#pg-next');
    if (prev) prev.addEventListener('click', () => { offset = Math.max(0, offset - LIMIT); load(); });
    if (next) next.addEventListener('click', () => { offset += LIMIT; load(); });
  }

  async function onDelete(btn) {
    if (!window.confirm('确定要删除这条分析记录吗？该操作不可恢复。')) return;
    btn.disabled = true;
    btn.textContent = '删除中…';
    try {
      await api(`/api/runs/${encodeURIComponent(btn.dataset.id)}`, { method: 'DELETE' });
      // 当前页删空时回退一页
      if (offset > 0 && offset >= total - 1) offset = Math.max(0, offset - LIMIT);
      load();
    } catch (e) {
      const box = root.querySelector('#hist-error');
      if (box) box.innerHTML = `<div class="banner banner-error">删除失败：${esc(e.message)}</div>`;
      btn.disabled = false;
      btn.textContent = '删除';
    }
  }

  return () => { destroyed = true; };
}
