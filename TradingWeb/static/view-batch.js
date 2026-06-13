import { api } from './api.js';
import { esc, loadingHtml, skeletonHtml, statusBadge } from './util.js';

export function render(root) {
  let destroyed = false;
  let queue = [];

  root.innerHTML = `<div class="view-enter">${skeletonHtml(4)}</div>`;
  draw();

  function draw() {
    if (destroyed) return;
    root.innerHTML = `
      <div class="view-enter">
        <h1 class="page-title"><span class="accent-bar"></span>批量运行队列</h1>
        <div class="grid-2">
          <div class="card card-pad">
            <div class="panel-title">提交批量 ticker</div>
            <div class="field">
              <label class="field-label" for="batch-tickers">Ticker 列表</label>
              <textarea class="input mono" id="batch-tickers" rows="8" placeholder="SPY\nAAPL\nMSFT"></textarea>
              <div class="field-hint">每行一个 ticker；提交后会依次创建 run 并显示在队列中。</div>
            </div>
            <div class="field" style="display:flex;gap:8px;flex-wrap:wrap">
              <button class="btn btn-primary" id="batch-submit">开始批量运行</button>
              <button class="btn" id="batch-refresh">刷新队列</button>
            </div>
            <div id="batch-error"></div>
          </div>
          <div class="card card-pad">
            <div class="panel-title">队列状态</div>
            <div id="batch-status">${loadingHtml('等待提交…')}</div>
          </div>
        </div>
      </div>`;
    bind();
  }

  function bind() {
    root.querySelector('#batch-submit').addEventListener('click', onSubmit);
    root.querySelector('#batch-refresh').addEventListener('click', refreshQueue);
  }

  async function onSubmit() {
    const box = root.querySelector('#batch-error');
    const raw = root.querySelector('#batch-tickers').value;
    const tickers = raw.split(/\r?\n/).map((s) => s.trim().toUpperCase()).filter(Boolean);
    if (!tickers.length) {
      box.innerHTML = `<div class="banner banner-error">请输入至少一个 ticker</div>`;
      return;
    }
    box.innerHTML = '';
    const body = {
      tickers,
      analysis_date: new Date().toISOString().slice(0, 10),
      analysts: ['market', 'news'],
      research_depth: 1,
      provider_profile_id: null,
      llm_provider: 'openai',
      backend_url: '',
      quick_think_llm: 'gpt-5.4-mini',
      deep_think_llm: 'gpt-5.5',
      output_language: 'Chinese',
      checkpoint_enabled: false,
    };
    const res = await api('/api/runs/batch', { method: 'POST', body });
    queue = (res.ids || []).map((id, idx) => ({ id, ticker: tickers[idx], status: 'pending' }));
    renderQueue();
    pollQueue();
  }

  function renderQueue() {
    const box = root.querySelector('#batch-status');
    if (!box) return;
    if (!queue.length) {
      box.innerHTML = `<div class="banner">暂无队列。提交 ticker 后会显示在这里。</div>`;
      return;
    }
    box.innerHTML = queue.map((item) => `
      <div class="profile-row">
        <div>
          <div><strong>${esc(item.ticker)}</strong> <span class="cell-dim mono">#${esc(String(item.id))}</span></div>
          <div class="cell-dim">${statusBadge(item.status)}</div>
        </div>
        <div style="display:flex;gap:8px;flex-wrap:wrap">
          <button class="btn btn-sm btn-ghost" data-open="${esc(String(item.id))}">查看</button>
          <button class="btn btn-sm btn-danger" data-cancel="${esc(String(item.id))}" data-confirm="确认中止该队列任务？">中止</button>
        </div>
      </div>`).join('');
    box.querySelectorAll('[data-open]').forEach((b) => b.addEventListener('click', () => { location.hash = `#/runs/${b.dataset.open}`; }));
    box.querySelectorAll('[data-cancel]').forEach((b) => b.addEventListener('click', () => cancelRun(b.dataset.cancel)));
  }

  async function refreshQueue() {
    if (!queue.length) {
      renderQueue();
      return;
    }
    const updated = await Promise.all(queue.map(async (item) => {
      try {
        const d = await api(`/api/runs/${encodeURIComponent(item.id)}`);
        return { ...item, status: d.status, decision: d.decision };
      } catch {
        return item;
      }
    }));
    queue = updated;
    renderQueue();
  }

  async function pollQueue() {
    await refreshQueue();
    if (destroyed) return;
    if (queue.some((q) => q.status === 'pending' || q.status === 'running')) {
      setTimeout(() => pollQueue(), 2000);
    }
  }

  async function cancelRun(id) {
    const btn = root.querySelector(`[data-cancel="${esc(String(id))}"]`);
    const msg = btn && btn.getAttribute('data-confirm') ? btn.getAttribute('data-confirm') : '确认中止该队列任务？';
    if (!confirm(msg)) return;
    await api(`/api/runs/${encodeURIComponent(id)}/cancel`, { method: 'POST' });
    await refreshQueue();
  }

  return () => { destroyed = true; };
}
