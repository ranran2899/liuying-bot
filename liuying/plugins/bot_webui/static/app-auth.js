// 流萤本体 WebUI 鉴权模块
// 使用账号 + 令牌登录鉴权（非 cookie 登录）
// 本模块负责账号/令牌输入、持久化与登录页渲染

function renderLogin() {
  const themeIcon = state.theme === "dark" ? "夜" : "日";
  return `<div class="login-wrap"><div class="card">
    <div class="between">
      <h2 style="margin:0">流萤本体 WebUI 登录</h2>
      <button class="btn small" onclick="toggleTheme()" title="切换主题">${themeIcon}</button>
    </div>
    <p class="muted" style="font-size:12.5px;margin:10px 0 16px">
      输入账号和令牌进行身份验证。所有写操作（机器人开关、插件启停、群组权限、
      任务暂停/移除等）需提供正确的账号与令牌。
    </p>
    <label for="login-account">账号</label>
    <input id="login-account" type="text" autocomplete="username" autofocus
           placeholder="输入账号" value="${escapeAttr(state.account)}"
           onkeydown="if(event.key==='Enter')document.getElementById('login-token').focus()">
    <label for="login-token" style="margin-top:12px">令牌</label>
    <input id="login-token" type="password" autocomplete="current-password"
           placeholder="输入令牌" value="${escapeAttr(state.token)}"
           onkeydown="if(event.key==='Enter')doLogin()">
    <div style="margin-top:16px">
      <button class="btn primary" onclick="doLogin()">进入控制台</button>
    </div>
    <div id="login-msg" class="muted" style="margin-top:14px;font-size:12.5px" aria-live="polite" role="status"></div>
    <div class="alert info" style="margin-top:18px;font-size:12px">
      鉴权说明：账号和令牌仅在本地浏览器持久化（localStorage），每次写操作请求会以
      <code>account</code> 和 <code>token</code> query 参数发送到后端校验。切换账号请点右上角"退出登录"。
    </div>
  </div></div>`;
}

async function doLogin() {
  const accountInput = document.getElementById("login-account");
  const tokenInput = document.getElementById("login-token");
  const msg = document.getElementById("login-msg");
  const account = (accountInput && accountInput.value || "").trim();
  const token = (tokenInput && tokenInput.value || "").trim();
  if (!account || !token) { msg.textContent = "请输入账号和令牌。"; return; }
  msg.textContent = "正在校验…";
  try {
    await api("/health/full", { auth: true, params: { account, token } });
    state.account = account;
    state.token = token;
    state.logged = true;
    localStorage.setItem("bot_webui_account", account);
    localStorage.setItem("bot_webui_token", token);
    msg.textContent = "登录成功，正在加载…";
    await loadView();
    render();
  } catch (e) {
    msg.textContent = "校验失败：" + e.message + "（请确认账号和令牌正确）";
  }
}
