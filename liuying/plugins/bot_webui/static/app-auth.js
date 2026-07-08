// 流萤本体 WebUI 鉴权模块
// 流萤采用超级用户 QQ 作为 query 参数鉴权（非 cookie 登录）
// 本模块负责 QQ 身份输入、持久化与登录页渲染

function renderLogin() {
  const themeIcon = state.theme === "dark" ? "夜" : "日";
  return `<div class="login-wrap"><div class="card">
    <div class="between">
      <h2 style="margin:0">流萤本体 WebUI 登录</h2>
      <button class="btn small" onclick="toggleTheme()" title="切换主题">${themeIcon}</button>
    </div>
    <p class="muted" style="font-size:12.5px;margin:10px 0 16px">
      输入超级用户 QQ 进行身份标识。所有写操作（机器人开关、插件启停、群组权限、
      任务暂停/移除等）需该 QQ 在 NoneBot 配置的 <code>SUPERUSERS</code> 列表中。
    </p>
    <label for="login-qq">超级用户 QQ</label>
    <input id="login-qq" type="text" inputmode="numeric" autocomplete="username" autofocus
           placeholder="输入超级用户 QQ" value="${escapeAttr(state.qq)}"
           onkeydown="if(event.key==='Enter')doLogin()">
    <div style="margin-top:16px">
      <button class="btn primary" onclick="doLogin()">进入控制台</button>
    </div>
    <div id="login-msg" class="muted" style="margin-top:14px;font-size:12.5px" aria-live="polite" role="status"></div>
    <div class="alert info" style="margin-top:18px;font-size:12px">
      鉴权说明：QQ 仅在本地浏览器持久化（localStorage），每次写操作请求会以
      <code>auth_uid</code> query 参数发送到后端校验。切换 QQ 请点右上角"切换QQ"。
    </div>
  </div></div>`;
}

async function doLogin() {
  const input = document.getElementById("login-qq");
  const msg = document.getElementById("login-msg");
  const qq = (input && input.value || "").trim();
  if (!qq) { msg.textContent = "请输入超级用户 QQ。"; return; }
  msg.textContent = "正在校验…";
  // 通过健康检查接口验证 QQ 是否有权限（health/full 反映本体可用性）
  try {
    await api("/health/full", { auth: true, params: { auth_uid: qq } });
    state.qq = qq;
    state.logged = true;
    localStorage.setItem("bot_webui_uid", qq);
    msg.textContent = "登录成功，正在加载…";
    await loadView();
    render();
  } catch (e) {
    msg.textContent = "校验失败：" + e.message + "（请确认该 QQ 为超级用户）";
  }
}
