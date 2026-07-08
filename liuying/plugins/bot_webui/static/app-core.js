// 流萤本体 WebUI 核心模块
// 提供 API 调用、全局状态、渲染框架、导航与初始化

const API = "/bot";

let state = {
  // 鉴权：流萤采用超级用户 QQ 作为 query 参数（非 cookie 登录）
  logged: false, qq: "",
  // 视图与加载状态
  view: "dashboard", loading: false, alert: null,
  // 主题与移动端导航
  theme: "dark", mobileNavOpen: false,
  // 各视图数据缓存
  status: null,
  system: null,
  bots: null,
  plugins: null, pluginBotId: "", pluginMenuFilter: "", pluginSearch: "",
  groups: null, groupStatusFilter: "", groupSearch: "",
  tasks: null, taskGroupFilter: "",
  logs: null, logFile: "", logLines: 400, logContent: null,
  stats: null, statsLimit: 100,
};

// ========== API 调用 ==========

const _apiInflight = new Map();

async function api(path, opts = {}) {
  const method = (opts.method || "GET").toUpperCase();
  const headers = { ...(opts.headers || {}) };
  // 自动注入超级用户 QQ 作为 auth_uid query 参数（写操作鉴权需要）
  const params = { ...(opts.params || {}) };
  if (state.qq && (method !== "GET" || opts.auth)) {
    if (!params.auth_uid) params.auth_uid = state.qq;
  }
  // 构造完整 URL
  const url = new URL(API + path, location.origin);
  for (const [k, v] of Object.entries(params)) {
    if (v !== "" && v !== null && v !== undefined) url.searchParams.set(k, v);
  }
  // GET 请求做 in-flight 去重
  const dedupKey = method === "GET" ? url.toString() : null;
  if (dedupKey && _apiInflight.has(dedupKey)) {
    return _apiInflight.get(dedupKey);
  }
  const promise = (async () => {
    const fetchOpts = { method, headers, credentials: "include" };
    if (opts.body) {
      fetchOpts.headers["content-type"] = "application/json";
      fetchOpts.body = JSON.stringify(opts.body);
    }
    const res = await fetch(url.toString(), fetchOpts);
    if (!res.ok) {
      let detail = res.statusText;
      try { const j = await res.json(); detail = j.detail || JSON.stringify(j); } catch {}
      throw new Error(detail);
    }
    return res.status === 204 ? null : await res.json();
  })();
  if (dedupKey) {
    _apiInflight.set(dedupKey, promise);
    promise.finally(() => { _apiInflight.delete(dedupKey); });
  }
  return promise;
}

// ========== 工具函数 ==========

function escapeHtml(s) {
  return String(s == null ? "" : s).replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
}

function escapeAttr(s) {
  return escapeHtml(s).replace(/'/g, "&#39;");
}

function alertFlash(kind, text) {
  state.alert = { kind, text };
  render();
  setTimeout(() => { state.alert = null; render(); }, 4000);
}

function fmtBool(v) {
  return v
    ? '<span class="tag ok">ON</span>'
    : '<span class="tag">OFF</span>';
}

function fmtStatus(v) {
  return v
    ? '<span class="tag ok">启用</span>'
    : '<span class="tag err">禁用</span>';
}

function fmtOnline(v) {
  return v
    ? '<span class="tag ok"><span class="status-dot online"></span>在线</span>'
    : '<span class="tag"><span class="status-dot offline"></span>离线</span>';
}

function fmtJson(obj) {
  return `<pre class="json">${escapeHtml(JSON.stringify(obj, null, 2))}</pre>`;
}

function fmtBytes(n) {
  if (n == null || isNaN(n)) return "-";
  const u = ["B", "KB", "MB", "GB", "TB"];
  let i = 0, v = Number(n);
  while (v >= 1024 && i < u.length - 1) { v /= 1024; i++; }
  return v.toFixed(i === 0 ? 0 : 1) + " " + u[i];
}

function fmtNum(n) {
  if (n == null || isNaN(n)) return "-";
  return Number(n).toLocaleString();
}

function usageBar(percent, opts = {}) {
  const p = Math.max(0, Math.min(100, Number(percent) || 0));
  const cls = p >= 90 ? "danger" : p >= 75 ? "warn" : "";
  const label = opts.label || (p.toFixed(1) + "%");
  return `<div class="usage">
    <div class="usage-head"><span>${escapeHtml(opts.name || "")}</span><span>${escapeHtml(label)}</span></div>
    <div class="usage-bar"><div class="usage-fill ${cls}" style="width:${p}%"></div></div>
  </div>`;
}

function statBars(obj, max) {
  const entries = Object.entries(obj || {});
  if (!entries.length) return '<p class="muted">暂无数据</p>';
  const top = max || entries.reduce((m, [, v]) => Math.max(m, v), 0) || 1;
  return entries.map(([k, v]) => {
    const pct = (v / top) * 100;
    return `<div class="stat-row">
      <span class="stat-label" title="${escapeAttr(k)}">${escapeHtml(k)}</span>
      <span class="stat-track"><span class="stat-fill" style="width:${pct}%"></span></span>
      <span class="stat-num">${fmtNum(v)}</span>
    </div>`;
  }).join("");
}

// ========== 视图加载 ==========

async function loadView() {
  state.loading = true;
  try {
    if (state.view === "dashboard") {
      const [status, system] = await Promise.all([
        api("/status"),
        api("/system").catch(() => null),
      ]);
      state.status = status;
      state.system = system;
    } else if (state.view === "system") {
      state.system = await api("/system");
    } else if (state.view === "bots") {
      state.bots = await api("/bots");
    } else if (state.view === "plugins") {
      if (state.pluginBotId) {
        state.plugins = await api("/plugins/bot/" + encodeURIComponent(state.pluginBotId));
      } else {
        state.plugins = await api("/plugins");
      }
    } else if (state.view === "groups") {
      state.groups = await api("/groups");
    } else if (state.view === "tasks") {
      state.tasks = await api("/tasks");
    } else if (state.view === "logs") {
      state.logs = await api("/logs");
      if (state.logFile) {
        state.logContent = await api("/logs/" + encodeURIComponent(state.logFile), {
          params: { lines: state.logLines },
        });
      }
    } else if (state.view === "stats") {
      state.stats = await api("/stats", { params: { limit: state.statsLimit } });
    }
  } finally { state.loading = false; }
}

// ========== 渲染框架 ==========

function render() {
  const root = document.getElementById("app");
  // 未填写超级用户 QQ 时显示登录页
  if (!state.qq) { root.innerHTML = renderLogin(); return; }
  // 全量重绘时保留输入框焦点与光标位置
  const active = document.activeElement;
  let focusSnap = null;
  if (active && active.id && (active.tagName === "INPUT" || active.tagName === "TEXTAREA")) {
    focusSnap = {
      id: active.id,
      start: active.selectionStart,
      end: active.selectionEnd,
      scrollTop: active.scrollTop,
    };
  }
  root.innerHTML = renderLayout();
  attachLayout();
  if (focusSnap) {
    const next = document.getElementById(focusSnap.id);
    if (next && (next.tagName === "INPUT" || next.tagName === "TEXTAREA")) {
      next.focus();
      try {
        if (focusSnap.start !== null && focusSnap.end !== null) {
          next.setSelectionRange(focusSnap.start, focusSnap.end);
        }
        next.scrollTop = focusSnap.scrollTop || 0;
      } catch (_) { /* number inputs 不支持 setSelectionRange */ }
    }
  }
  // 日志查看器自动滚到底部
  if (state.view === "logs" && state.logContent) {
    const lv = document.getElementById("log-viewer");
    if (lv) lv.scrollTop = lv.scrollHeight;
  }
}

function renderLayout() {
  const navItem = (v, label) => `<a href="#${v}" class="${state.view===v?'active':''}" onclick="switchView('${v}');return false;">${label}</a>`;
  const themeIcon = state.theme === "dark" ? "夜" : "日";
  return `${state.loading ? '<div class="progress-bar" role="progressbar" aria-label="加载中"></div>' : ''}
    <div class="layout">
    ${state.mobileNavOpen ? '<div class="scrim" onclick="toggleMobileNav()"></div>' : ''}
    <aside class="${state.mobileNavOpen?'open':''}" aria-label="主导航">
      <h1>流萤本体 控制台</h1>
      <nav>
        ${navItem('dashboard','概览')}
        ${navItem('bots','机器人账号')}
        ${navItem('plugins','插件管理')}
        ${navItem('groups','群组管理')}
        ${navItem('tasks','定时任务')}
        ${navItem('system','系统信息')}
        ${navItem('logs','日志查看')}
        ${navItem('stats','调用统计')}
      </nav>
    </aside>
    <main>
      <div class="topbar between">
        <div style="display:flex;align-items:center;min-width:0;flex:1">
          <button class="mobile-nav-toggle" onclick="toggleMobileNav()" aria-label="菜单" aria-expanded="${state.mobileNavOpen}">≡</button>
          <div style="min-width:0">
            <div class="breadcrumb">控制台 <span class="sep">›</span> ${escapeHtml(viewTitle())}</div>
            <strong style="font-size:17px">${escapeHtml(viewTitle())}</strong>
          </div>
        </div>
        <div class="row">
          <button class="btn small" onclick="toggleTheme()" title="切换主题" aria-label="切换深色/浅色主题">${themeIcon}</button>
          <span class="muted" title="当前超级用户QQ">QQ ${escapeHtml(state.qq)}</span>
          <button class="btn small" onclick="switchAccount()">切换QQ</button>
        </div>
      </div>
      ${state.alert ? `<div class="alert ${state.alert.kind}" role="alert">${escapeHtml(state.alert.text)}</div>` : ''}
      ${renderView()}
    </main>
  </div>`;
}

function attachLayout() {
  // 导航点击通过 switchView 全局函数处理，此处无需额外绑定
}

function switchView(v) {
  if (!VIEWS[v]) return;
  state.view = v;
  if (state.mobileNavOpen) state.mobileNavOpen = false;
  loadView().then(render).catch(e => { state.loading = false; alertFlash("err", e.message); });
}

function viewTitle() {
  return ({
    dashboard:"概览", bots:"机器人账号", plugins:"插件管理",
    groups:"群组管理", tasks:"定时任务", system:"系统信息",
    logs:"日志查看", stats:"调用统计",
  })[state.view] || state.view;
}

function renderView() {
  const fn = VIEWS[state.view];
  if (!fn) return `<div class="card"><h2>${escapeHtml(viewTitle())}</h2><p class="muted">该视图暂未实现。</p></div>`;
  try { return fn(); }
  catch (e) { return `<div class="alert err">渲染失败：${escapeHtml(e.message)}</div>`; }
}

// ========== 主题与导航 ==========

function toggleTheme() {
  state.theme = state.theme === "dark" ? "light" : "dark";
  document.documentElement.setAttribute("data-theme", state.theme);
  localStorage.setItem("bot_webui_theme", state.theme);
  render();
}

function toggleMobileNav() {
  state.mobileNavOpen = !state.mobileNavOpen;
  render();
}

function switchAccount() {
  state.qq = "";
  localStorage.removeItem("bot_webui_uid");
  render();
}

// 视图渲染函数注册表（由各模块填充）
const VIEWS = {};

// ========== 初始化 ==========

async function bootstrap() {
  const savedTheme = localStorage.getItem("bot_webui_theme") || "dark";
  state.theme = savedTheme;
  document.documentElement.setAttribute("data-theme", savedTheme);
  const savedUid = localStorage.getItem("bot_webui_uid") || "";
  state.qq = savedUid;
  if (state.qq) {
    try { await loadView(); }
    catch (e) { /* 加载失败不阻塞界面 */ }
  }
  render();
}

document.addEventListener("DOMContentLoaded", bootstrap);
