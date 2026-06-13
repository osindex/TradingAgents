import { api } from './api.js';
import { state } from './state.js';
import { esc, loadingHtml } from './util.js';
import * as viewLogin from './view-login.js';
import * as viewWizard from './view-wizard.js';
import * as viewRun from './view-run.js';
import * as viewHistory from './view-history.js';
import * as viewProfiles from './view-profiles.js';

const root = document.getElementById('view-root');
const navbar = document.getElementById('navbar');
let cleanup = null;
let booted = false;

/* ============ 导航栏 ============ */

export function setUser(username) {
  state.user = username || null;
  renderNavbar();
}

function renderNavbar() {
  if (!state.user) {
    navbar.classList.add('hidden');
    navbar.innerHTML = '';
    return;
  }
  navbar.classList.remove('hidden');
  const isAdmin = state.user === 'admin';
  navbar.innerHTML = `
    <a class="brand" href="#/new">
      <span class="brand-mark">TA</span>
      TradingAgents&nbsp;<span class="brand-suffix">Web</span>
    </a>
    <nav class="nav-links">
      <a class="nav-link" data-route="new" href="#/new">新建分析</a>
      ${isAdmin ? '<a class="nav-link" data-route="profiles" href="#/profiles">接入商管理</a>' : ''}
      <a class="nav-link" data-route="runs" href="#/runs">历史记录</a>
    </nav>
    <span class="nav-spacer"></span>
    <span class="nav-user">${esc(state.user)}</span>
    <button class="btn btn-sm btn-ghost" id="logout-btn">退出登录</button>`;
  navbar.querySelector('#logout-btn').addEventListener('click', logout);
  highlightNav();
}

function highlightNav() {
  const hash = location.hash || '';
  navbar.querySelectorAll('.nav-link').forEach((a) => {
    const r = a.dataset.route;
    const active = (r === 'new' && hash.startsWith('#/new'))
      || (r === 'profiles' && hash.startsWith('#/profiles') && state.user === 'admin')
      || (r === 'runs' && hash.startsWith('#/runs'));
    a.classList.toggle('active', active);
  });
}

async function logout() {
  try {
    await api('/api/logout', { method: 'POST', noAuthRedirect: true });
  } catch (e) { /* 即使失败也回到登录页 */ }
  setUser(null);
  location.hash = '#/login';
}

/* ============ 路由 ============ */

function route() {
  if (!booted) return;
  if (cleanup) {
    try { cleanup(); } catch (e) { /* ignore */ }
    cleanup = null;
  }

  const hash = location.hash || '#/new';

  if (hash === '#/login' || hash.startsWith('#/login?')) {
    navbar.classList.add('hidden');
    cleanup = viewLogin.render(root) || null;
    return;
  }

  // 未登录一律回登录页
  if (!state.user) {
    location.hash = '#/login';
    return;
  }
  renderNavbar();

  const runMatch = hash.match(/^#\/runs\/([^/?#]+)/);
  if (runMatch) {
    cleanup = viewRun.render(root, decodeURIComponent(runMatch[1])) || null;
  } else if (hash === '#/profiles' || hash.startsWith('#/profiles?')) {
    cleanup = viewProfiles.render(root) || null;
  } else if (hash === '#/runs' || hash.startsWith('#/runs?')) {
    cleanup = viewHistory.render(root) || null;
  } else if (hash === '#/new' || hash.startsWith('#/new?')) {
    cleanup = viewWizard.render(root) || null;
  } else {
    location.hash = '#/new';
    return;
  }
  highlightNav();
}

/* ============ 启动 ============ */

async function boot() {
  root.innerHTML = loadingHtml('正在加载…');
  try {
    const me = await api('/api/me', { noAuthRedirect: true });
    state.user = me && me.username ? me.username : null;
  } catch (e) {
    state.user = null;
  }
  booted = true;
  renderNavbar();
  const hash = location.hash;
  if (!state.user) {
    if (hash === '#/login') route();
    else location.hash = '#/login'; // 触发 hashchange -> route()
    return;
  }
  if (!hash || hash === '#' || hash === '#/' || hash === '#/login') {
    location.hash = '#/new'; // 触发 hashchange -> route()
    return;
  }
  route();
}

window.addEventListener('hashchange', route);
boot();
