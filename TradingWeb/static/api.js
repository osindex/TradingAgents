/**
 * 集中式 fetch 封装：
 * - cookie 认证（same-origin）
 * - 401 自动跳转登录（可通过 noAuthRedirect 关闭）
 * - JSON 错误统一抛出 ApiError
 */
export class ApiError extends Error {
  constructor(status, detail) {
    super(detail || `请求失败 (${status})`);
    this.name = 'ApiError';
    this.status = status;
    this.detail = detail;
  }
}

export async function api(path, { method = 'GET', body, noAuthRedirect = false } = {}) {
  let res;
  try {
    res = await fetch(path, {
      method,
      credentials: 'same-origin',
      headers: body !== undefined ? { 'Content-Type': 'application/json' } : undefined,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  } catch (e) {
    throw new ApiError(0, '网络连接失败，请检查网络');
  }

  if (res.status === 204) return null;

  let data = null;
  try {
    const text = await res.text();
    if (text) data = JSON.parse(text);
  } catch (e) {
    data = null;
  }

  if (!res.ok) {
    if (res.status === 401 && !noAuthRedirect) {
      if (location.hash !== '#/login') location.hash = '#/login';
    }
    const detail = data && data.detail != null ? String(data.detail) : `请求失败 (${res.status})`;
    throw new ApiError(res.status, detail);
  }
  return data;
}
