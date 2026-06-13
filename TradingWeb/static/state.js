import { api } from './api.js';

/** 全局共享状态 */
export const state = {
  user: null,        // 当前登录用户名
  options: null,     // GET /api/options 缓存
  modelsCache: {},   // provider -> GET /api/options/models 缓存
};

export async function getOptions(force = false) {
  if (!state.options || force) {
    state.options = await api('/api/options');
  }
  return state.options;
}

export async function getModels(provider) {
  if (!state.modelsCache[provider]) {
    state.modelsCache[provider] = await api(
      `/api/options/models?provider=${encodeURIComponent(provider)}`
    );
  }
  return state.modelsCache[provider];
}
