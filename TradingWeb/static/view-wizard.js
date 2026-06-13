import { api, ApiError } from './api.js';
import { getOptions, getModels, getProviderProfiles } from './state.js';
import { esc, isCryptoTicker, loadingHtml, skeletonHtml } from './util.js';

const STEP_LABELS = ['标的与日期', '分析师团队', '研究深度', 'LLM 厂商', '模型选择', '确认'];
const CUSTOM = '__custom__';

const ANALYST_DESC = {
  market: '技术指标 · 价格走势 · K线形态',
  social: '社交媒体 · 舆情与情绪追踪',
  news: '全球新闻 · 宏观事件解读',
  fundamentals: '财务报表 · 估值与基本面',
};

export function render(root) {
  let opts = null;
  let step = 1;
  let models = null;       // 当前厂商的模型列表
  let modelsProvider = ''; // models 对应的 provider key
  let destroyed = false;

  const data = {
    ticker: '',
    analysis_date: '',
    analysts: new Set(),
    research_depth: null,
    provider: '',
    provider_profile_id: null,
    backend_url: '',
    thinkingValue: null,
    quick: null, quickCustom: '',
    deep: null, deepCustom: '',
    language: null, languageCustom: '',
  };

  root.innerHTML = `<div class="wizard">${skeletonHtml(5)}</div>`;

  getOptions()
    .then((o) => {
      if (destroyed) return;
      opts = o;
      initDefaults();
      draw();
    })
    .catch((err) => {
      if (destroyed) return;
      root.innerHTML = `<div class="wizard view-enter">
        <div class="banner banner-error">加载配置失败：${esc(err.message)}</div>
        <button class="btn" id="wz-retry">重试</button></div>`;
      root.querySelector('#wz-retry').addEventListener('click', () => render(root));
    });

  function initDefaults() {
    const d = opts.defaults || {};
    data.ticker = (d.ticker || 'SPY').toUpperCase();
    data.analysis_date = d.analysis_date || new Date().toISOString().slice(0, 10);
    data.analysts = new Set((opts.analysts || []).map((a) => a.key));
    data.research_depth = opts.depths && opts.depths.length ? opts.depths[0].value : 1;
    const p = (opts.providers || [])[0];
    const profile = (opts.provider_profiles || [])[0];
    if (profile) {
      data.provider_profile_id = profile.id;
      data.provider = profile.provider_key || '';
      data.backend_url = profile.base_url || '';
      data.thinkingValue = profile.google_thinking_level || profile.openai_reasoning_effort || profile.anthropic_effort || null;
      data.quick = profile.quick_think_llm || null;
      data.deep = profile.deep_think_llm || null;
      getModels(data.provider).catch(() => {});
    } else if (p) {
      data.provider = p.key;
      data.backend_url = p.base_url || '';
      data.thinkingValue = p.thinking ? p.thinking.default : null;
      getModels(p.key).catch(() => {});
    }
    data.language = (opts.languages || [])[0] || '中文';
  }

  function currentProvider() {
    return (opts.providers || []).find((p) => p.key === data.provider) || null;
  }
  function crypto() {
    return isCryptoTicker(data.ticker);
  }

  /* ============ 渲染 ============ */

  function draw() {
    if (destroyed) return;
    root.innerHTML = `
      <div class="wizard view-enter">
        <h1 class="page-title"><span class="accent-bar"></span>新建分析</h1>
        ${stepperHtml()}
        <div class="card">
          <div class="wizard-body">
            ${stepBodyHtml()}
            <div id="wz-error"></div>
          </div>
          <div class="wizard-footer">
            <span class="wizard-step-count">步骤 ${step} / 6</span>
            <div style="display:flex;gap:12px">
              <button class="btn" id="wz-prev" ${step === 1 ? 'disabled' : ''}>上一步</button>
              <button class="btn btn-primary" id="wz-next">${step === 6 ? '开始分析' : '下一步'}</button>
            </div>
          </div>
        </div>
      </div>`;
    bindCommon();
    bindStep();
  }

  function stepperHtml() {
    return `<div class="stepper">${STEP_LABELS.map((label, i) => {
      const n = i + 1;
      const cls = n < step ? 'done' : n === step ? 'current' : '';
      return `<div class="stepper-item ${cls}">
        <div class="stepper-dot">${n < step ? '✓' : n}</div>
        <div class="stepper-label">${esc(label)}</div>
      </div>`;
    }).join('')}</div>`;
  }

  function stepBodyHtml() {
    switch (step) {
      case 1: return step1Html();
      case 2: return step2Html();
      case 3: return step3Html();
      case 4: return step4Html();
      case 5: return step5Html();
      case 6: return step6Html();
    }
    return '';
  }

  /* ---------- ① 标的与日期 ---------- */
  function step1Html() {
    return `
      <h2 class="wizard-step-title">标的与日期</h2>
      <p class="wizard-step-sub">输入要分析的股票 / 加密资产代码与分析日期</p>
      <div class="form-2col">
        <div class="field">
          <label class="field-label" for="f-ticker">股票代码
            <span id="crypto-badge">${crypto() ? '<span class="crypto-badge">加密资产</span>' : ''}</span>
          </label>
          <input class="input mono" id="f-ticker" value="${esc(data.ticker)}"
                 placeholder="SPY / 0700.HK / BTC-USD" autocomplete="off" spellcheck="false"
                 style="text-transform:uppercase">
          <div class="field-hint">支持美股、港股（.HK）及加密资产（如 BTC-USD）</div>
        </div>
        <div class="field">
          <label class="field-label" for="f-date">分析日期</label>
          <input class="input mono" id="f-date" type="date" value="${esc(data.analysis_date)}">
        </div>
      </div>`;
  }

  /* ---------- ② 分析师团队 ---------- */
  function step2Html() {
    const isCrypto = crypto();
    const cards = (opts.analysts || []).map((a) => {
      const disabled = isCrypto && !a.crypto_supported;
      const checked = data.analysts.has(a.key) && !disabled;
      return `
        <label class="opt-card ${checked ? 'checked' : ''} ${disabled ? 'disabled' : ''}"
               ${disabled ? 'title="加密资产不支持基本面分析"' : ''} data-analyst="${esc(a.key)}">
          <input type="checkbox" value="${esc(a.key)}" ${checked ? 'checked' : ''} ${disabled ? 'disabled' : ''}>
          <div class="opt-card-title">${esc(a.label)}</div>
          <div class="opt-card-desc">${esc(ANALYST_DESC[a.key] || '')}</div>
          <span class="opt-check"></span>
        </label>`;
    }).join('');
    return `
      <h2 class="wizard-step-title">分析师团队</h2>
      <p class="wizard-step-sub">选择参与本次分析的分析师（至少一位）${isCrypto ? ' · 当前为加密资产' : ''}</p>
      <div class="opt-grid">${cards}</div>`;
  }

  /* ---------- ③ 研究深度 ---------- */
  function step3Html() {
    const cards = (opts.depths || []).map((d) => {
      const checked = String(data.research_depth) === String(d.value);
      return `
        <label class="opt-card ${checked ? 'checked' : ''}" data-depth="${esc(String(d.value))}">
          <input type="radio" name="depth" value="${esc(String(d.value))}" ${checked ? 'checked' : ''}>
          <div class="opt-card-title">${esc(d.label)}</div>
          <div class="opt-card-desc">${esc(d.description || '')}</div>
          <span class="opt-check"></span>
        </label>`;
    }).join('');
    return `
      <h2 class="wizard-step-title">研究深度</h2>
      <p class="wizard-step-sub">辩论轮次越多，分析越深入，耗时与成本也越高</p>
      <div class="opt-grid cols-3">${cards}</div>`;
  }

  /* ---------- ④ LLM 厂商 ---------- */
  function step4Html() {
    const p = currentProvider();
    const options = (opts.provider_profiles || []).map((pr) =>
      `<option value="${esc(String(pr.id))}" ${String(pr.id) === String(data.provider_profile_id) ? 'selected' : ''}>${esc(pr.name)} · ${esc(pr.provider_key)}</option>`
    ).join('');
    let thinkingHtml = '';
    if (p && p.thinking) {
      const chips = (p.thinking.options || []).map((o) => {
        const checked = String(data.thinkingValue) === String(o.value);
        return `<label class="radio-chip ${checked ? 'checked' : ''}">
          <input type="radio" name="thinking" value="${esc(String(o.value))}" ${checked ? 'checked' : ''}>
          ${esc(o.label)}</label>`;
      }).join('');
      thinkingHtml = `
        <div class="field" id="thinking-group">
          <label class="field-label">${esc(p.thinking.label)}</label>
          <div class="radio-row">${chips}</div>
        </div>`;
    }
    return `
      <h2 class="wizard-step-title">接入商配置</h2>
      <p class="wizard-step-sub">选择一个存储在 SQLite 中的 provider profile</p>
      <div class="field">
        <label class="field-label" for="f-profile">接入商</label>
        <select class="select" id="f-profile">${options}</select>
        ${currentProfile() && currentProfile().base_url ? `<div class="field-hint">默认网关：<span class="mono">${esc(currentProfile().base_url)}</span></div>` : ''}
      </div>
      <div class="field">
        <label class="field-label" for="f-backend">网关地址（profile 覆盖项）</label>
        <input class="input mono" id="f-backend" value="${esc(data.backend_url)}" placeholder="https://…" spellcheck="false">
      </div>
      ${thinkingHtml}`;
  }

  /* ---------- ⑤ 模型选择 ---------- */
  function step5Html() {
    if (!models || modelsProvider !== data.provider) {
      return `
        <h2 class="wizard-step-title">模型选择</h2>
        <p class="wizard-step-sub">正在加载 ${esc(providerLabel())} 的可用模型…</p>
        <div id="models-loading">${loadingHtml('加载模型列表…')}</div>`;
    }
    const allowCustom = models.allow_custom !== false;
    const sel = (list, current, id) => {
      const opt = (list || []).map((m) =>
        `<option value="${esc(m.value)}" ${m.value === current ? 'selected' : ''}>${esc(m.label)}</option>`
      ).join('');
      const customOpt = allowCustom
        ? `<option value="${CUSTOM}" ${current === CUSTOM ? 'selected' : ''}>自定义模型ID…</option>` : '';
      return `<select class="select" id="${id}">${opt}${customOpt}</select>`;
    };
    const langs = (opts.languages || []).map((l) =>
      `<option value="${esc(l)}" ${l === data.language ? 'selected' : ''}>${esc(l)}</option>`
    ).join('') + `<option value="${CUSTOM}" ${data.language === CUSTOM ? 'selected' : ''}>自定义…</option>`;
    return `
      <h2 class="wizard-step-title">模型选择</h2>
      <p class="wizard-step-sub">为不同任务阶段选择合适的模型 · 厂商：${esc(providerLabel())}</p>
      <div class="form-2col">
        <div class="field">
          <label class="field-label" for="f-quick">快速思考模型</label>
          ${sel(models.quick, data.quick, 'f-quick')}
          <input class="input mono ${data.quick === CUSTOM ? '' : 'hidden'}" id="f-quick-custom"
                 value="${esc(data.quickCustom)}" placeholder="输入模型 ID" spellcheck="false" style="margin-top:8px">
          <div class="field-hint">用于数据整理、工具调用等轻量任务</div>
        </div>
        <div class="field">
          <label class="field-label" for="f-deep">深度思考模型</label>
          ${sel(models.deep, data.deep, 'f-deep')}
          <input class="input mono ${data.deep === CUSTOM ? '' : 'hidden'}" id="f-deep-custom"
                 value="${esc(data.deepCustom)}" placeholder="输入模型 ID" spellcheck="false" style="margin-top:8px">
          <div class="field-hint">用于研究辩论、决策推理等复杂任务</div>
        </div>
      </div>
      <div class="field" style="max-width:380px">
        <label class="field-label" for="f-lang">输出语言</label>
        <select class="select" id="f-lang">${langs}</select>
        <input class="input ${data.language === CUSTOM ? '' : 'hidden'}" id="f-lang-custom"
               value="${esc(data.languageCustom)}" placeholder="输入输出语言，如 日本語" style="margin-top:8px">
      </div>`;
  }

  /* ---------- ⑥ 确认 ---------- */
  function step6Html() {
    const p = currentProvider();
    const analystLabels = (opts.analysts || [])
      .filter((a) => data.analysts.has(a.key))
      .map((a) => a.label).join('、');
    const depth = (opts.depths || []).find((d) => String(d.value) === String(data.research_depth));
    const rows = [
      ['标的', `<span class="mono">${esc(data.ticker)}</span>${crypto() ? '<span class="crypto-badge">加密资产</span>' : ''}`],
      ['分析日期', `<span class="mono">${esc(data.analysis_date)}</span>`],
      ['分析师团队', esc(analystLabels)],
      ['研究深度', esc(depth ? depth.label : String(data.research_depth))],
      ['LLM 厂商', esc(p ? p.label : data.provider)],
      ['网关地址', `<span class="mono">${esc(data.backend_url)}</span>`],
      ['快速思考模型', `<span class="mono">${esc(resolvedQuick())}</span>`],
      ['深度思考模型', `<span class="mono">${esc(resolvedDeep())}</span>`],
      ['输出语言', esc(resolvedLanguage())],
    ];
    if (p && p.thinking) {
      const o = (p.thinking.options || []).find((x) => String(x.value) === String(data.thinkingValue));
      rows.splice(6, 0, [p.thinking.label, esc(o ? o.label : String(data.thinkingValue))]);
    }
    return `
      <h2 class="wizard-step-title">确认配置</h2>
      <p class="wizard-step-sub">请核对以下信息，点击「开始分析」后任务将进入执行队列</p>
      <table class="summary-table">
        ${rows.map(([k, v]) => `<tr><th>${esc(k)}</th><td>${v}</td></tr>`).join('')}
      </table>`;
  }

  function providerLabel() {
    const p = currentProfile();
    if (p) return `${p.name} · ${p.provider_key}`;
    const pr = currentProvider();
    return pr ? pr.label : data.provider;
  }
  function currentProfile() {
    return (opts.provider_profiles || []).find((p) => String(p.id) === String(data.provider_profile_id)) || null;
  }
  function resolvedQuick() {
    return data.quick === CUSTOM ? data.quickCustom.trim() : (data.quick || '');
  }
  function resolvedDeep() {
    return data.deep === CUSTOM ? data.deepCustom.trim() : (data.deep || '');
  }
  function resolvedLanguage() {
    return data.language === CUSTOM ? data.languageCustom.trim() : (data.language || '');
  }

  /* ============ 事件绑定 ============ */

  function bindCommon() {
    root.querySelector('#wz-prev').addEventListener('click', () => {
      if (step > 1) { collectStep(); step--; draw(); }
    });
    root.querySelector('#wz-next').addEventListener('click', onNext);
  }

  function bindStep() {
    if (step === 1) {
      const t = root.querySelector('#f-ticker');
      t.addEventListener('input', () => {
        data.ticker = t.value.toUpperCase().trim();
        const badge = root.querySelector('#crypto-badge');
        if (badge) badge.innerHTML = crypto() ? '<span class="crypto-badge">加密资产</span>' : '';
      });
      root.querySelector('#f-date').addEventListener('change', (e) => {
        data.analysis_date = e.target.value;
      });
    } else if (step === 2) {
      root.querySelectorAll('.opt-card[data-analyst]').forEach((card) => {
        const input = card.querySelector('input');
        input.addEventListener('change', () => {
          card.classList.toggle('checked', input.checked);
          if (input.checked) data.analysts.add(input.value);
          else data.analysts.delete(input.value);
        });
      });
    } else if (step === 3) {
      root.querySelectorAll('.opt-card[data-depth]').forEach((card) => {
        const input = card.querySelector('input');
        input.addEventListener('change', () => {
          root.querySelectorAll('.opt-card[data-depth]').forEach((c) => c.classList.remove('checked'));
          card.classList.add('checked');
          data.research_depth = input.value;
        });
      });
    } else if (step === 4) {
      const sel = root.querySelector('#f-profile');
      sel.addEventListener('change', () => {
        data.provider_profile_id = Number(sel.value);
        const profile = currentProfile();
        data.provider = profile && profile.provider_key ? profile.provider_key : data.provider;
        data.backend_url = profile && profile.base_url ? profile.base_url : '';
        data.thinkingValue = profile && (profile.google_thinking_level || profile.openai_reasoning_effort || profile.anthropic_effort) || null;
        if (profile) {
          data.quick = profile.quick_think_llm || data.quick;
          data.deep = profile.deep_think_llm || data.deep;
        }
        models = null; modelsProvider = '';
        getModels(data.provider).catch(() => {});
        draw();
      });
      root.querySelector('#f-backend').addEventListener('input', (e) => {
        data.backend_url = e.target.value.trim();
      });
      root.querySelectorAll('#thinking-group input[name="thinking"]').forEach((r) => {
        r.addEventListener('change', () => {
          data.thinkingValue = r.value;
          root.querySelectorAll('#thinking-group .radio-chip').forEach((c) =>
            c.classList.toggle('checked', c.querySelector('input').checked));
        });
      });
    } else if (step === 5) {
      if (!models || modelsProvider !== data.provider) {
        loadModelsForStep();
        return;
      }
      const bindModelSel = (selId, customId, field, customField) => {
        const sel = root.querySelector(selId);
        const custom = root.querySelector(customId);
        sel.addEventListener('change', () => {
          data[field] = sel.value;
          custom.classList.toggle('hidden', sel.value !== CUSTOM);
          if (sel.value === CUSTOM) custom.focus();
        });
        custom.addEventListener('input', () => { data[customField] = custom.value; });
      };
      bindModelSel('#f-quick', '#f-quick-custom', 'quick', 'quickCustom');
      bindModelSel('#f-deep', '#f-deep-custom', 'deep', 'deepCustom');
      bindModelSel('#f-lang', '#f-lang-custom', 'language', 'languageCustom');
    }
  }

  function loadModelsForStep() {
    const provider = data.provider;
    getModels(provider)
      .then((m) => {
        if (destroyed || step !== 5 || data.provider !== provider) return;
        models = m;
        modelsProvider = provider;
        if (!data.quick && m.quick && m.quick.length) data.quick = m.quick[0].value;
        if (!data.deep && m.deep && m.deep.length) data.deep = m.deep[0].value;
        draw();
      })
      .catch((err) => {
        if (destroyed || step !== 5) return;
        const box = root.querySelector('#models-loading');
        if (box) box.innerHTML = `<div class="banner banner-error">模型列表加载失败：${esc(err.message)}</div>
          <button class="btn btn-sm" id="models-retry">重试</button>`;
        const retry = root.querySelector('#models-retry');
        if (retry) retry.addEventListener('click', () => loadModelsForStep());
      });
  }

  /* ============ 取值 / 校验 / 提交 ============ */

  function collectStep() {
    if (step === 1) {
      const t = root.querySelector('#f-ticker');
      const d = root.querySelector('#f-date');
      if (t) data.ticker = t.value.toUpperCase().trim();
      if (d) data.analysis_date = d.value;
      if (crypto()) {
        // 加密资产自动剔除不支持的分析师
        (opts.analysts || []).forEach((a) => {
          if (!a.crypto_supported) data.analysts.delete(a.key);
        });
      }
    } else if (step === 4) {
      const b = root.querySelector('#f-backend');
      if (b) data.backend_url = b.value.trim();
    }
  }

  function validateStep() {
    switch (step) {
      case 1:
        if (!data.ticker) return '请输入股票代码';
        if (!data.analysis_date) return '请选择分析日期';
        return null;
      case 2: {
        const isCrypto = crypto();
        const valid = (opts.analysts || []).filter(
          (a) => data.analysts.has(a.key) && (!isCrypto || a.crypto_supported)
        );
        if (!valid.length) return '请至少选择一位分析师';
        return null;
      }
      case 3:
        if (data.research_depth == null || data.research_depth === '') return '请选择研究深度';
        return null;
      case 4:
        if (!data.provider) return '请选择 LLM 厂商';
        return null;
      case 5:
        if (!models || modelsProvider !== data.provider) return '模型列表尚未加载完成，请稍候';
        if (!resolvedQuick()) return '请选择或填写快速思考模型';
        if (!resolvedDeep()) return '请选择或填写深度思考模型';
        if (!resolvedLanguage()) return '请选择或填写输出语言';
        return null;
    }
    return null;
  }

  function showError(msg) {
    const box = root.querySelector('#wz-error');
    if (box) box.innerHTML = msg ? `<div class="banner banner-error" style="margin-top:16px">${esc(msg)}</div>` : '';
  }

  async function onNext() {
    collectStep();
    const err = validateStep();
    if (err) { showError(err); return; }
    showError('');
    if (step < 6) {
      step++;
      draw();
      return;
    }
    await submit();
  }

  async function submit() {
    const btn = root.querySelector('#wz-next');
    const prevBtn = root.querySelector('#wz-prev');
    btn.disabled = true;
    prevBtn.disabled = true;
    btn.innerHTML = `<span class="spinner"></span>创建中…`;
    const isCrypto = crypto();
    const analysts = (opts.analysts || [])
      .filter((a) => data.analysts.has(a.key) && (!isCrypto || a.crypto_supported))
      .map((a) => a.key);
    const body = {
      ticker: data.ticker,
      analysis_date: data.analysis_date,
      analysts,
      research_depth: Number(data.research_depth),
      provider_profile_id: data.provider_profile_id,
      llm_provider: data.provider,
      backend_url: data.backend_url,
      quick_think_llm: resolvedQuick(),
      deep_think_llm: resolvedDeep(),
      output_language: resolvedLanguage(),
    };
    const p = currentProvider();
    if (p && p.thinking && data.thinkingValue != null) {
      body[p.thinking.config_key] = data.thinkingValue;
    }
    try {
      const res = await api('/api/runs', { method: 'POST', body });
      location.hash = `#/runs/${res.id}`;
    } catch (e) {
      showError(e instanceof ApiError ? e.detail : (e && e.message) || '创建失败');
      btn.disabled = false;
      prevBtn.disabled = false;
      btn.textContent = '开始分析';
    }
  }

  return () => { destroyed = true; };
}
