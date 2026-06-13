import { api } from './api.js';
import { esc, loadingHtml, skeletonHtml } from './util.js';

function blankForm() {
  return {
    id: null,
    name: '',
    provider_key: 'openai',
    base_url: '',
    api_key_env: '',
    quick_think_llm: '',
    deep_think_llm: '',
    output_language: 'English',
    google_thinking_level: '',
    openai_reasoning_effort: '',
    anthropic_effort: '',
    enabled: true,
  };
}

export function render(root) {
  let destroyed = false;
  let profiles = [];
  let editing = blankForm();

  root.innerHTML = `<div class="view-enter">${skeletonHtml(4)}</div>`;
  load();

  async function load() {
    try {
      const data = await api('/api/provider-profiles');
      profiles = data.profiles || [];
      if (!destroyed) draw();
    } catch (e) {
      if (destroyed) return;
      root.innerHTML = `<div class="view-enter"><div class="banner banner-error">加载接入商失败：${esc(e.message)}</div></div>`;
    }
  }

  function draw() {
    root.innerHTML = `
      <div class="view-enter">
        <h1 class="page-title"><span class="accent-bar"></span>接入商管理</h1>
        <div class="grid-2">
          <div class="card">
            <div class="panel-title">已有接入商</div>
            <div id="profiles-list"></div>
          </div>
          <div class="card">
            <div class="panel-title">${editing.id ? '编辑接入商' : '新增接入商'}</div>
            <form id="profile-form" class="form-stack">
              ${input('name', '名称', editing.name)}
              ${select('provider_key', 'provider', ['openai','anthropic','google','xai','deepseek','qwen','qwen-cn','glm','glm-cn','minimax','minimax-cn','openrouter','ollama','azure'], editing.provider_key)}
              ${input('base_url', 'base_url', editing.base_url)}
              ${input('api_key_env', 'API key 环境变量', editing.api_key_env)}
              ${input('quick_think_llm', '快速模型', editing.quick_think_llm)}
              ${input('deep_think_llm', '深度模型', editing.deep_think_llm)}
              ${input('output_language', '输出语言', editing.output_language)}
              ${input('google_thinking_level', 'Google thinking', editing.google_thinking_level)}
              ${input('openai_reasoning_effort', 'OpenAI reasoning', editing.openai_reasoning_effort)}
              ${input('anthropic_effort', 'Anthropic effort', editing.anthropic_effort)}
              <label class="field-label"><input type="checkbox" id="enabled" ${editing.enabled ? 'checked' : ''}> 启用</label>
              <div id="profile-error"></div>
              <div style="display:flex;gap:12px;flex-wrap:wrap">
                <button class="btn btn-primary" type="submit">${editing.id ? '保存' : '创建'}</button>
                <button class="btn" type="button" id="profile-reset">重置</button>
              </div>
            </form>
          </div>
        </div>
      </div>`;
    renderList();
    bind();
  }

  function input(name, label, value) {
    return `<div class="field"><label class="field-label" for="${esc(name)}">${esc(label)}</label><input class="input mono" id="${esc(name)}" value="${esc(value || '')}"></div>`;
  }

  function select(name, label, options, value) {
    const opts = options.map((o) => `<option value="${esc(o)}" ${o === value ? 'selected' : ''}>${esc(o)}</option>`).join('');
    return `<div class="field"><label class="field-label" for="${esc(name)}">${esc(label)}</label><select class="select" id="${esc(name)}">${opts}</select></div>`;
  }

  function renderList() {
    const box = root.querySelector('#profiles-list');
    if (!box) return;
    if (!profiles.length) {
      box.innerHTML = `<div class="banner">暂无接入商，先创建一个吧。</div>`;
      return;
    }
    box.innerHTML = profiles.map((p) => `
      <div class="profile-row">
        <div>
          <div><strong>${esc(p.name)}</strong> <span class="cell-dim">${esc(p.provider_key)}</span></div>
          <div class="cell-dim mono">${esc(p.base_url || '默认 endpoint')}</div>
          <div class="cell-dim mono">quick=${esc(p.quick_think_llm || '—')} · deep=${esc(p.deep_think_llm || '—')}</div>
        </div>
        <div style="display:flex;gap:8px;flex-wrap:wrap">
          <button class="btn btn-sm" data-edit="${p.id}">编辑</button>
          <button class="btn btn-sm btn-danger" data-del="${p.id}">删除</button>
        </div>
      </div>`).join('');
  }

  function bind() {
    root.querySelector('#profile-form').addEventListener('submit', onSubmit);
    root.querySelector('#profile-reset').addEventListener('click', () => { editing = blankForm(); draw(); });
    root.querySelectorAll('[data-edit]').forEach((btn) => btn.addEventListener('click', () => {
      const p = profiles.find((x) => String(x.id) === String(btn.dataset.edit));
      if (!p) return;
      editing = { ...blankForm(), ...p };
      draw();
    }));
    root.querySelectorAll('[data-del]').forEach((btn) => btn.addEventListener('click', async () => {
      if (!confirm('删除这个接入商？')) return;
      await api(`/api/provider-profiles/${btn.dataset.del}`, { method: 'DELETE' });
      await load();
    }));
  }

  async function onSubmit(e) {
    e.preventDefault();
    const err = root.querySelector('#profile-error');
    err.innerHTML = '';
    const form = root.querySelector('#profile-form');
    const body = {
      name: form.querySelector('#name').value.trim(),
      provider_key: form.querySelector('#provider_key').value,
      base_url: form.querySelector('#base_url').value.trim() || null,
      api_key_env: form.querySelector('#api_key_env').value.trim() || null,
      quick_think_llm: form.querySelector('#quick_think_llm').value.trim(),
      deep_think_llm: form.querySelector('#deep_think_llm').value.trim(),
      output_language: form.querySelector('#output_language').value.trim() || 'English',
      google_thinking_level: form.querySelector('#google_thinking_level').value.trim() || null,
      openai_reasoning_effort: form.querySelector('#openai_reasoning_effort').value.trim() || null,
      anthropic_effort: form.querySelector('#anthropic_effort').value.trim() || null,
      enabled: form.querySelector('#enabled').checked,
    };
    try {
      if (editing.id) await api(`/api/provider-profiles/${editing.id}`, { method: 'PUT', body });
      else await api('/api/provider-profiles', { method: 'POST', body });
      editing = blankForm();
      await load();
    } catch (ex) {
      err.innerHTML = `<div class="banner banner-error">${esc(ex.message)}</div>`;
    }
  }

  return () => { destroyed = true; };
}
