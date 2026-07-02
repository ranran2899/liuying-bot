// 流萤AI WebUI 核心模块
// 提供 API 调用、全局状态、渲染框架、导航与初始化

const API = "/ai";

let state = {
  // 鉴权：流萤采用超级用户 QQ 作为 query 参数（非 cookie 登录）
  logged: false, qq: "",
  // 视图与加载状态
  view: "dashboard", loading: false, alert: null,
  // 主题与移动端导航
  theme: "dark", mobileNavOpen: false,
  // 各视图数据缓存
  status: null, health: null,
  configEntries: [], configGroups: [], activeConfigGroup: null, configSearch: "", showAdvancedConfig: false,
  runtime: null, runtimeScope: "global", runtimeScopeId: "",
  personas: null, personaDetail: null,
  memory: null, memoryUserId: "", memoryGroupId: "", memoryLimit: 50,
  emotionUserId: "", emotion: null,
  groups: null,
  tokenDays: 7, token: null,
  vision: null, visionProvider: "", visionModel: "",
  knowledge: null,
  aclUserId: "", aclLevel: 5, aclGroupId: "", acl: null,
};

// ========== API 调用 ==========

const _apiInflight = new Map();

async function api(path, opts = {}) {
  const method = (opts.method || "GET").toUpperCase();
  const headers = { ...(opts.headers || {}) };
  // 自动注入超级用户 QQ 作为 auth_uid query 参数（写操作鉴权需要）
  // 使用 auth_uid 而非 user_id，避免与路由自身的 user_id 业务参数冲突
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
    ? '<span class="tag source-group">ON</span>'
    : '<span class="tag">OFF</span>';
}

function fmtJson(obj) {
  return `<pre class="json">${escapeHtml(JSON.stringify(obj, null, 2))}</pre>`;
}

// ========== 视图加载 ==========

async function loadView() {
  state.loading = true;
  try {
    if (state.view === "dashboard") {
      const [status, health] = await Promise.all([
        api("/status"),
        api("/health/full", { params: { user_id: state.qq } }).catch(() => null),
      ]);
      state.status = status;
      state.health = health;
    } else if (state.view === "status") {
      state.status = await api("/status");
    } else if (state.view === "config") {
      const data = await api("/config");
      state.configEntries = data.entries || [];
      state.configGroups = data.groups || [];
      if (!state.activeConfigGroup || !state.configGroups.includes(state.activeConfigGroup)) {
        state.activeConfigGroup = state.configGroups[0] || null;
      }
    } else if (state.view === "runtime") {
      state.runtime = await api("/runtime", { params: { user_id: state.qq } });
    } else if (state.view === "persona") {
      state.personas = await api("/persona");
    } else if (state.view === "memory") {
      state.memory = await api("/memory/summary", {
        params: { user_id: state.memoryUserId, group_id: state.memoryGroupId, limit: state.memoryLimit },
      });
    } else if (state.view === "emotion") {
      // 情绪状态需要先输入 QQ，不预加载
      if (state.emotionUserId) {
        state.emotion = await api("/emotion/" + encodeURIComponent(state.emotionUserId));
      }
    } else if (state.view === "groups") {
      state.groups = await api("/groups");
    } else if (state.view === "token") {
      state.token = await api("/token/summary", { params: { days: state.tokenDays } });
    } else if (state.view === "vision") {
      state.vision = await api("/vision/capability");
    } else if (state.view === "knowledge") {
      state.knowledge = await api("/knowledge/stats");
    } else if (state.view === "acl") {
      // 权限检查需要先输入 QQ，不预加载
    } else if (state.view === "health") {
      state.health = await api("/health/full", { auth: true });
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
}

function renderLayout() {
  const navItem = (v, label) => `<a class="${state.view===v?'active':''}" onclick="switchView('${v}')">${label}</a>`;
  const themeIcon = state.theme === "dark" ? "夜" : "日";
  return `${state.loading ? '<div class="progress-bar"></div>' : ''}
    <div class="layout">
    ${state.mobileNavOpen ? '<div class="scrim" onclick="toggleMobileNav()"></div>' : ''}
    <aside class="${state.mobileNavOpen?'open':''}">
      <h1>流萤AI 控制台</h1>
      <nav>
        ${navItem('dashboard','概览')}
        ${navItem('status','运行状态')}
        ${navItem('config','配置中心')}
        ${navItem('runtime','功能开关')}
        ${navItem('persona','人格管理')}
        ${navItem('memory','记忆查看')}
        ${navItem('emotion','情绪状态')}
        ${navItem('groups','群上下文')}
        ${navItem('token','Token统计')}
        ${navItem('vision','视觉能力')}
        ${navItem('knowledge','知识库')}
        ${navItem('acl','权限检查')}
        ${navItem('health','功能体检')}
      </nav>
    </aside>
    <main>
      <div class="topbar between">
        <div style="display:flex;align-items:center;min-width:0;flex:1">
          <button class="mobile-nav-toggle" onclick="toggleMobileNav()" aria-label="菜单">≡</button>
          <div style="min-width:0">
            <div class="breadcrumb">控制台 <span class="sep">›</span> ${escapeHtml(viewTitle())}</div>
            <strong style="font-size:17px">${escapeHtml(viewTitle())}</strong>
          </div>
        </div>
        <div class="row">
          <button class="btn small" onclick="toggleTheme()" title="切换主题">${themeIcon}</button>
          <span class="muted" title="当前超级用户QQ">QQ ${escapeHtml(state.qq)}</span>
          <button class="btn small" onclick="switchAccount()">切换QQ</button>
        </div>
      </div>
      ${state.alert ? `<div class="alert ${state.alert.kind}">${escapeHtml(state.alert.text)}</div>` : ''}
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
    dashboard:"概览", status:"运行状态", config:"配置中心",
    runtime:"功能开关", persona:"人格管理", memory:"记忆查看",
    emotion:"情绪状态", groups:"群上下文", token:"Token统计",
    vision:"视觉能力", knowledge:"知识库", acl:"权限检查", health:"功能体检",
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
  localStorage.setItem("ai_webui_theme", state.theme);
  render();
}

function toggleMobileNav() {
  state.mobileNavOpen = !state.mobileNavOpen;
  render();
}

function switchAccount() {
  state.qq = "";
  localStorage.removeItem("ai_webui_uid");
  render();
}

// 视图渲染函数注册表（由各模块填充）
const VIEWS = {};

// ========== 初始化 ==========

async function bootstrap() {
  const savedTheme = localStorage.getItem("ai_webui_theme") || "dark";
  state.theme = savedTheme;
  document.documentElement.setAttribute("data-theme", savedTheme);
  const savedUid = localStorage.getItem("ai_webui_uid") || "";
  state.qq = savedUid;
  if (state.qq) {
    try { await loadView(); }
    catch (e) { /* 加载失败不阻塞界面 */ }
  }
  render();
}

document.addEventListener("DOMContentLoaded", bootstrap);
