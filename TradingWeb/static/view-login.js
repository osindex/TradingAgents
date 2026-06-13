import { api, ApiError } from './api.js';
import { esc } from './util.js';
import { setUser } from './app.js';

export function render(root) {
  root.innerHTML = `
    <div class="login-wrap view-enter">
      <div class="card login-card">
        <div class="login-logo">
          <div class="brand-mark">TA</div>
          <div class="login-title">TradingAgents <em>Web</em></div>
          <div class="login-sub">多智能体 LLM 股票分析平台</div>
        </div>
        <form id="login-form" novalidate>
          <div class="field">
            <label class="field-label" for="login-username">用户名</label>
            <input class="input" id="login-username" name="username" autocomplete="username" required>
          </div>
          <div class="field">
            <label class="field-label" for="login-password">密码</label>
            <input class="input" id="login-password" name="password" type="password" autocomplete="current-password" required>
          </div>
          <div id="login-error"></div>
          <button class="btn btn-primary btn-lg" id="login-btn" type="submit">登 录</button>
        </form>
      </div>
    </div>`;

  const form = root.querySelector('#login-form');
  const btn = root.querySelector('#login-btn');
  const errBox = root.querySelector('#login-error');
  root.querySelector('#login-username').focus();

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const username = root.querySelector('#login-username').value.trim();
    const password = root.querySelector('#login-password').value;
    errBox.innerHTML = '';
    if (!username || !password) {
      errBox.innerHTML = `<div class="banner banner-error">请输入用户名和密码</div>`;
      return;
    }
    btn.disabled = true;
    btn.innerHTML = `<span class="spinner"></span>登录中…`;
    try {
      const data = await api('/api/login', {
        method: 'POST',
        body: { username, password },
        noAuthRedirect: true,
      });
      setUser(data && data.username ? data.username : username);
      location.hash = '#/new';
    } catch (err) {
      const msg = err instanceof ApiError && err.status === 401
        ? '用户名或密码错误'
        : (err && err.message) || '登录失败，请稍后重试';
      errBox.innerHTML = `<div class="banner banner-error">${esc(msg)}</div>`;
      btn.disabled = false;
      btn.textContent = '登 录';
    }
  });
}
