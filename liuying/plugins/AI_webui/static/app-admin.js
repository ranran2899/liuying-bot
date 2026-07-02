// 流萤AI WebUI 管理模块
// 概览 + 运行状态 + 功能开关 + 权限检查 + 功能体检 + 人格管理 + 群上下文

// ========== 概览 ==========

function renderDashboard() {
  const s = state.status;
  const h = state.health;
  if (!s) return `<div class="card muted">加载中…</div>`;
  const items = [
    ["AI对话", fmtBool(s.enabled)],
    ["当前人格", escapeHtml(s.persona)],
    ["Agent工具", fmtBool(s.agent_enabled)],
    ["记忆系统", fmtBool(s.memory_enabled)],
    ["TTS语音", fmtBool(s.tts_enabled)],
    ["安全过滤", fmtBool(s.safety_filter_enabled)],
    ["视觉理解", fmtBool(s.vision_enabled)],
    ["碎片化风格", escapeHtml(s.fragment_style)],
    ["服务器时间", escapeHtml(s.timestamp || '-')],
  ];
  const kvGrid = `<div class="kv-grid">${items.map(([k, v]) =>
    `<div class="kv-item"><div class="k">${k}</div><div class="v">${v}</div></div>`).join("")}</div>`;
  const healthBlock = h ? `<h3>功能体检摘要</h3>${fmtJson(h)}` :
    `<p class="muted" style="font-size:12px">功能体检需超级用户权限，未填写或无权限时不展示。</p>`;
  return `<div class="card">
    <h2>运行状态概览</h2>
    <p class="muted" style="font-size:12px;margin-top:0">AI 插件各功能模块开关与当前人格汇总。</p>
    ${kvGrid}
  </div>
  <div class="card">${healthBlock}</div>`;
}

// ========== 运行状态 ==========

function renderStatus() {
  const s = state.status;
  if (!s) return `<div class="card muted">加载中…</div>`;
  const rows = [
    ["AI对话总开关", fmtBool(s.enabled)],
    ["默认人格", escapeHtml(s.persona)],
    ["Agent工具调用", fmtBool(s.agent_enabled)],
    ["记忆系统", fmtBool(s.memory_enabled)],
    ["TTS语音", fmtBool(s.tts_enabled)],
    ["安全过滤", fmtBool(s.safety_filter_enabled)],
    ["视觉理解", fmtBool(s.vision_enabled)],
    ["碎片化风格", escapeHtml(s.fragment_style)],
    ["服务器时间", escapeHtml(s.timestamp || '-')],
  ];
  return `<div class="card">
    <h2>运行状态</h2>
    <table><tbody>${rows.map(([k, v]) =>
      `<tr><td class="muted">${k}</td><td>${v}</td></tr>`).join("")}</tbody></table>
  </div>`;
}

// ========== 功能开关 ==========

function renderRuntime() {
  const r = state.runtime;
  if (!r) return `<div class="card muted">加载中…</div>`;
  const features = r.features || [];
  const rows = features.map(f => {
    const sourceTag = `<span class="tag source-${escapeAttr(f.source)}">${escapeHtml(f.source)}</span>`;
    const toggle = `<div class="toggle">
      <button class="${f.enabled?'on':''}" onclick="setGlobalSwitch('${escapeAttr(f.name)}', true)">开</button>
      <button class="${!f.enabled?'on':''}" onclick="setGlobalSwitch('${escapeAttr(f.name)}', false)">关</button>
    </div>`;
    return `<tr>
      <td><strong>${escapeHtml(f.name)}</strong> <code style="font-size:11px">${escapeHtml(f.config_key || '')}</code></td>
      <td>${fmtBool(f.enabled)} ${sourceTag}</td>
      <td>${toggle}</td>
    </tr>`;
  }).join("");
  return `<div class="card">
    <h2>全局功能开关</h2>
    <p class="muted" style="font-size:12px;margin-top:0">
      AI 插件子功能运行时开关。修改需超级用户权限，立即生效。
    </p>
    <table><thead><tr><th>功能</th><th>状态</th><th>切换</th></tr></thead>
    <tbody>${rows || '<tr><td colspan="3" class="muted">暂无开关</td></tr>'}</tbody></table>
  </div>
  ${renderGroupSwitchEditor()}
  ${renderUserSwitchEditor()}`;
}

function renderGroupSwitchEditor() {
  return `<div class="card">
    <h2>群组级覆盖</h2>
    <p class="muted" style="font-size:12px;margin:0 0 10px">为指定群单独覆盖某功能开关，优先级高于全局。</p>
    <div class="row">
      <input type="text" id="rt-group-id" placeholder="群号" style="width:160px">
      <input type="text" id="rt-group-feat" placeholder="功能名（如 memory_enabled）" style="width:220px">
      <button class="btn primary" onclick="setGroupSwitch(true)">开启</button>
      <button class="btn danger" onclick="setGroupSwitch(false)">关闭</button>
      <button class="btn small" onclick="clearGroupSwitch()">清除覆盖</button>
    </div>
  </div>`;
}

function renderUserSwitchEditor() {
  return `<div class="card">
    <h2>用户级覆盖</h2>
    <p class="muted" style="font-size:12px;margin:0 0 10px">为指定用户单独覆盖某功能开关，优先级高于全局与群组级。</p>
    <div class="row">
      <input type="text" id="rt-user-id" placeholder="用户 QQ" style="width:160px">
      <input type="text" id="rt-user-feat" placeholder="功能名" style="width:220px">
      <button class="btn primary" onclick="setUserSwitch(true)">开启</button>
      <button class="btn danger" onclick="setUserSwitch(false)">关闭</button>
      <button class="btn small" onclick="clearUserSwitch()">清除覆盖</button>
    </div>
  </div>`;
}

async function setGlobalSwitch(feature, enabled) {
  try {
    await api("/runtime/global", { method: "POST", params: { feature, enabled } });
    alertFlash("ok", `${feature} 已${enabled?'开启':'关闭'}`);
    await loadView(); render();
  } catch (e) { alertFlash("err", "操作失败：" + e.message); }
}

async function setGroupSwitch(enabled) {
  const gid = document.getElementById("rt-group-id")?.value.trim();
  const feat = document.getElementById("rt-group-feat")?.value.trim();
  if (!gid || !feat) { alertFlash("err", "请填写群号与功能名"); return; }
  try {
    await api("/runtime/group", { method: "POST", params: { group_id: gid, feature: feat, enabled } });
    alertFlash("ok", `群 ${gid} 的 ${feat} 已${enabled?'开启':'关闭'}`);
    await loadView(); render();
  } catch (e) { alertFlash("err", "操作失败：" + e.message); }
}

async function clearGroupSwitch() {
  const gid = document.getElementById("rt-group-id")?.value.trim();
  const feat = document.getElementById("rt-group-feat")?.value.trim();
  if (!gid || !feat) { alertFlash("err", "请填写群号与功能名"); return; }
  try {
    await api("/runtime/group", { method: "DELETE", params: { group_id: gid, feature: feat } });
    alertFlash("ok", `已清除群 ${gid} 的 ${feat} 覆盖`);
    await loadView(); render();
  } catch (e) { alertFlash("err", "操作失败：" + e.message); }
}

async function setUserSwitch(enabled) {
  const uid = document.getElementById("rt-user-id")?.value.trim();
  const feat = document.getElementById("rt-user-feat")?.value.trim();
  if (!uid || !feat) { alertFlash("err", "请填写用户 QQ 与功能名"); return; }
  try {
    await api("/runtime/user", { method: "POST", params: { user_id: uid, feature: feat, enabled } });
    alertFlash("ok", `用户 ${uid} 的 ${feat} 已${enabled?'开启':'关闭'}`);
    await loadView(); render();
  } catch (e) { alertFlash("err", "操作失败：" + e.message); }
}

async function clearUserSwitch() {
  const uid = document.getElementById("rt-user-id")?.value.trim();
  const feat = document.getElementById("rt-user-feat")?.value.trim();
  if (!uid || !feat) { alertFlash("err", "请填写用户 QQ 与功能名"); return; }
  try {
    await api("/runtime/user", { method: "DELETE", params: { user_id: uid, feature: feat } });
    alertFlash("ok", `已清除用户 ${uid} 的 ${feat} 覆盖`);
    await loadView(); render();
  } catch (e) { alertFlash("err", "操作失败：" + e.message); }
}

// ========== 权限检查 ==========

function renderAcl() {
  const a = state.acl;
  return `<div class="toolbar">
      <input type="text" placeholder="用户 QQ" value="${escapeAttr(state.aclUserId)}"
             oninput="state.aclUserId=this.value" style="width:160px">
      <label class="muted">所需等级</label>
      <input type="number" value="${state.aclLevel}" min="1" max="10"
             oninput="state.aclLevel=Number(this.value)" style="width:80px">
      <input type="text" placeholder="群号（可选）" value="${escapeAttr(state.aclGroupId)}"
             oninput="state.aclGroupId=this.value" style="width:160px">
      <button class="btn primary" onclick="checkAcl()">检查</button>
    </div>
    <div class="card">
      ${a ? renderAclResult(a) : '<p class="muted">输入用户 QQ 后点击检查，查看该用户是否满足指定权限等级。</p>'}
    </div>`;
}

function renderAclResult(a) {
  const items = [
    ["是否允许", a.allowed ? '<span class="tag source-group">是</span>' : '<span class="tag required">否</span>'],
    ["用户等级", escapeHtml(String(a.user_level ?? '-'))],
    ["超级用户", a.is_superuser ? "是" : "否"],
    ["黑名单", a.is_blacklisted ? '<span class="tag required">是</span>' : "否"],
    ["所需等级", escapeHtml(String(a.required_level ?? '-'))],
  ];
  return `<h2>用户 ${escapeHtml(a.user_id)} 的权限检查结果</h2>
    <div class="kv-grid">${items.map(([k, v]) =>
      `<div class="kv-item"><div class="k">${k}</div><div class="v">${v}</div></div>`).join("")}</div>
    ${a.reason ? `<p class="muted" style="margin-top:10px">原因：${escapeHtml(a.reason)}</p>` : ''}`;
}

async function checkAcl() {
  if (!state.aclUserId) { alertFlash("err", "请输入用户 QQ"); return; }
  try {
    state.acl = await api("/acl/check", {
      params: { user_id: state.aclUserId, level: state.aclLevel, group_id: state.aclGroupId },
    });
    render();
  } catch (e) { alertFlash("err", "检查失败：" + e.message); }
}

// ========== 功能体检 ==========

const HEALTH_STATUS = {
  ok: {label:"正常", cls:"hs-ok"}, warn: {label:"注意", cls:"hs-warn"},
  error: {label:"异常", cls:"hs-error"}, disabled: {label:"未启用", cls:"hs-disabled"},
  info: {label:"信息", cls:"hs-info"},
};

function renderHealth() {
  const h = state.health;
  if (!h) return `<div class="card muted">加载中…（功能体检需超级用户权限）</div>`;
  return `<div class="card">
    <div class="between">
      <h2 style="margin:0">功能体检</h2>
      <button class="btn small" onclick="refreshHealth()">重新检测</button>
    </div>
    <p class="muted" style="font-size:12px;margin:8px 0 0">
      展示 AI 插件各功能模块开关状态与计数。数据来自 <code>runtime_switch.health_check()</code>。
    </p>
    ${fmtJson(h)}
  </div>`;
}

async function refreshHealth() {
  state.loading = true; render();
  try {
    state.health = await api("/health/full", { auth: true });
  } catch (e) { alertFlash("err", "检测失败：" + e.message); }
  state.loading = false; render();
}

// ========== 人格管理 ==========

function renderPersona() {
  const data = state.personas;
  if (!data) return `<div class="card muted">加载中…</div>`;
  const personas = data.personas || [];
  const active = data.active || "";
  // 人格列表
  const rows = personas.map(p => {
    const activeTag = p.name === active ? '<span class="tag source-group">当前</span>' : '';
    return `<tr>
      <td><strong>${escapeHtml(p.name)}</strong> ${activeTag}</td>
      <td>${escapeHtml(p.display_name || '')}</td>
      <td class="muted">${escapeHtml(p.description || '')}</td>
      <td><button class="btn small" onclick="queryUserPersona('${escapeAttr(p.name)}')">查询用户</button></td>
    </tr>`;
  }).join("");
  // 全局切换
  const globalSel = `<select id="persona-global-sel">
    ${personas.map(p => `<option value="${escapeAttr(p.name)}" ${p.name===active?'selected':''}>${escapeHtml(p.name)} - ${escapeHtml(p.display_name||'')}</option>`).join("")}
  </select>`;
  return `<div class="card">
    <h2>切换全局默认人格</h2>
    <p class="muted" style="font-size:12px;margin-top:0">当前全局默认：<code>${escapeHtml(active)}</code>。切换需超级用户权限。</p>
    <div class="row">${globalSel}
      <button class="btn primary" onclick="switchGlobalPersona()">切换全局</button>
    </div>
  </div>
  <div class="card">
    <h2>切换用户级人格</h2>
    <p class="muted" style="font-size:12px;margin-top:0">为指定用户设置独立人格，覆盖全局默认。切换需超级用户权限。</p>
    <div class="row">
      <input type="text" id="persona-user-uid" placeholder="用户 QQ" style="width:160px">
      <select id="persona-user-sel">
        ${personas.map(p => `<option value="${escapeAttr(p.name)}">${escapeHtml(p.name)} - ${escapeHtml(p.display_name||'')}</option>`).join("")}
      </select>
      <button class="btn primary" onclick="switchUserPersona()">切换</button>
      <button class="btn small" onclick="queryUserPersona()">查询用户人格</button>
    </div>
    <div id="persona-user-detail"></div>
  </div>
  <div class="card">
    <h2>可用人格列表（${personas.length}）</h2>
    <table><thead><tr><th>名称</th><th>显示名</th><th>描述</th><th></th></tr></thead>
    <tbody>${rows || '<tr><td colspan="4" class="muted">暂无人格</td></tr>'}</tbody></table>
  </div>`;
}

async function switchGlobalPersona() {
  const name = document.getElementById("persona-global-sel")?.value;
  if (!name) return;
  if (!confirm(`确认将全局默认人格切换为 ${name}？`)) return;
  try {
    await api("/persona/global", { method: "POST", body: { persona_name: name } });
    alertFlash("ok", `全局人格已切换为 ${name}`);
    await loadView(); render();
  } catch (e) { alertFlash("err", "切换失败：" + e.message); }
}

async function switchUserPersona() {
  const uid = document.getElementById("persona-user-uid")?.value.trim();
  const name = document.getElementById("persona-user-sel")?.value;
  if (!uid || !name) { alertFlash("err", "请填写用户 QQ 并选择人格"); return; }
  try {
    await api("/persona/switch", { method: "POST", body: { user_id: uid, persona_name: name } });
    alertFlash("ok", `用户 ${uid} 的人格已切换为 ${name}`);
  } catch (e) { alertFlash("err", "切换失败：" + e.message); }
}

async function queryUserPersona() {
  const uid = document.getElementById("persona-user-uid")?.value.trim();
  if (!uid) { alertFlash("err", "请填写用户 QQ"); return; }
  const box = document.getElementById("persona-user-detail");
  if (!box) return;
  box.innerHTML = '<p class="muted">查询中…</p>';
  try {
    const data = await api("/persona/" + encodeURIComponent(uid));
    box.innerHTML = `<div class="alert info" style="margin-top:12px">
      用户 <code>${escapeHtml(data.user_id)}</code> 当前人格：<strong>${escapeHtml(data.persona_name)}</strong>
      （${escapeHtml(data.display_name || '')}）<br>
      <span class="muted" style="font-size:12px">${escapeHtml(data.description || '')}</span>
    </div>`;
  } catch (e) { box.innerHTML = `<div class="alert err" style="margin-top:12px">查询失败：${escapeHtml(e.message)}</div>`; }
}

// ========== 群上下文 ==========

function renderGroups() {
  const data = state.groups;
  if (!data) return `<div class="card muted">加载中…</div>`;
  if (!data.length) return `<div class="card"><h2>群上下文</h2><p class="muted">暂无活跃群上下文记录。</p></div>`;
  const rows = data.map(g => `<tr>
    <td><code>${escapeHtml(g.group_id)}</code></td>
    <td>${escapeHtml(g.style || '-')}</td>
    <td class="muted">${escapeHtml(g.summary || '-')}</td>
    <td class="muted" style="font-size:12px">${escapeHtml(g.last_activity || '-')}</td>
  </tr>`).join("");
  return `<div class="card">
    <h2>群上下文（${data.length}）</h2>
    <p class="muted" style="font-size:12px;margin-top:0">AI 插件记录的活跃群上下文，含群风格与摘要。</p>
    <table><thead><tr><th>群号</th><th>风格</th><th>摘要</th><th>最后活动</th></tr></thead>
    <tbody>${rows}</tbody></table>
  </div>`;
}

// 注册视图
VIEWS.dashboard = renderDashboard;
VIEWS.status = renderStatus;
VIEWS.runtime = renderRuntime;
VIEWS.acl = renderAcl;
VIEWS.health = renderHealth;
VIEWS.persona = renderPersona;
VIEWS.groups = renderGroups;
