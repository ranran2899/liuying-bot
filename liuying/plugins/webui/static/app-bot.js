// 流萤本体 WebUI 管理模块
// 概览 + 机器人账号 + 插件管理 + 群组管理

// ========== 概览 ==========

function renderDashboard() {
  const s = state.status;
  const sys = state.system;
  if (!s) return `<div class="card muted">加载中…</div>`;
  const onlineList = (s.online_bots || []).map(b => `<span class="tag info">${escapeHtml(b)}</span>`).join("");
  const metrics = [
    ["在线账号", s.online_count, s.bot_account_count ? `/ ${s.bot_account_count}` : ""],
    ["已加载插件", s.plugin_count, "个"],
    ["群组数", s.group_count, "个"],
    ["定时任务", s.task_count, "个"],
  ].map(([k, v, sub]) => `<div class="metric-card">
      <div class="metric-k">${k}</div>
      <div class="metric-v">${escapeHtml(String(v))}</div>
      <div class="metric-sub">${escapeHtml(sub || "")}</div>
    </div>`).join("");

  let sysBlock = "";
  if (sys) {
    sysBlock = `<div class="card">
      <h2>系统资源</h2>
      <div class="kv-grid" style="margin-bottom:12px">
        <div class="kv-item"><div class="k">机器人</div><div class="v">${escapeHtml(sys.bot_name)} ${escapeHtml(sys.bot_version)}</div></div>
        <div class="kv-item"><div class="k">运行环境</div><div class="v">${escapeHtml(sys.platform)} ${escapeHtml(sys.os_release)}</div></div>
        <div class="kv-item"><div class="k">Python</div><div class="v">${escapeHtml(sys.python_version)}</div></div>
        <div class="kv-item"><div class="k">运行时长</div><div class="v">${escapeHtml(sys.uptime_text)}</div></div>
        <div class="kv-item"><div class="k">CPU</div><div class="v">${escapeHtml(String(sys.cpu_percent))}% / ${escapeHtml(String(sys.cpu_count))}核</div></div>
        <div class="kv-item"><div class="k">进程</div><div class="v">PID ${escapeHtml(String(sys.process_pid))} / ${escapeHtml(String(sys.process_threads))}线程</div></div>
      </div>
      ${usageBar(sys.memory_percent, {name:"内存占用", label: `${fmtBytes(sys.memory_used)} / ${fmtBytes(sys.memory_total)}`})}
      ${usageBar(sys.disk_percent, {name:"磁盘占用", label: `${fmtBytes(sys.disk_used)} / ${fmtBytes(sys.disk_total)}`})}
    </div>`;
  } else {
    sysBlock = `<div class="card"><p class="muted">系统信息加载失败，可在"系统信息"页重试。</p></div>`;
  }

  return `<div class="card">
    <h2>运行总览</h2>
    <p class="muted" style="font-size:12px;margin-top:0">
      ${escapeHtml(s.bot_name)} <code>${escapeHtml(s.bot_version)}</code> · 调度器 ${s.scheduler_started ? '<span class="tag ok">运行中</span>' : '<span class="tag">未启动</span>'}
    </p>
    <div class="metric-grid">${metrics}</div>
  </div>
  <div class="card">
    <h2>在线机器人（${s.online_count}）</h2>
    ${onlineList || '<p class="muted">当前无在线账号</p>'}
  </div>
  ${sysBlock}`;
}

// ========== 机器人账号 ==========

function renderBots() {
  const data = state.bots;
  if (!data) return `<div class="card muted">加载中…</div>`;
  const bots = data.bots || [];
  if (!bots.length) return `<div class="card"><h2>机器人账号</h2><p class="muted">暂无机器人账号记录。</p></div>`;
  const rows = bots.map(b => `<tr>
    <td><code>${escapeHtml(b.bot_id)}</code></td>
    <td>${fmtOnline(b.online)}</td>
    <td>${fmtStatus(b.status)}</td>
    <td>${escapeHtml(b.platform || '-')}</td>
    <td class="muted" style="font-size:12px">${escapeHtml(b.create_time || '-')}</td>
    <td><span class="tag ok">${b.available_plugins}</span> / <span class="tag">${b.block_plugins}</span></td>
    <td><span class="tag ok">${b.available_tasks}</span> / <span class="tag">${b.block_tasks}</span></td>
    <td>
      <div class="toggle">
        <button class="${b.status?'on':''}" onclick="setBotStatus('${escapeAttr(b.bot_id)}', true)">开</button>
        <button class="${!b.status?'on':''}" onclick="setBotStatus('${escapeAttr(b.bot_id)}', false)">关</button>
      </div>
    </td>
  </tr>`).join("");
  return `<div class="card">
    <h2>机器人账号（${data.count}，在线 ${data.online_count}）</h2>
    <p class="muted" style="font-size:12px;margin-top:0">
      管理 BotConsole 账号状态。插件/被动列分别表示 可用/禁用 数量。切换状态需登录鉴权。
    </p>
    <table><thead><tr><th>账号ID</th><th>连接</th><th>状态</th><th>平台</th><th>创建时间</th><th>插件(用/禁)</th><th>被动(用/禁)</th><th>切换</th></tr></thead>
    <tbody>${rows}</tbody></table>
  </div>`;
}

async function setBotStatus(botId, status) {
  if (!confirm(`确认${status?'启用':'禁用'}机器人 ${botId}？`)) return;
  try {
    await api("/bots/status", { method: "POST", params: { bot_id: botId, status } });
    alertFlash("ok", `${botId} 已${status?'启用':'禁用'}`);
    await loadView(); render();
  } catch (e) { alertFlash("err", "操作失败：" + e.message); }
}

// ========== 插件管理 ==========

function renderPlugins() {
  const data = state.plugins;
  return `<div class="toolbar">
      <label class="muted">查看模式</label>
      <div class="toggle">
        <button class="${!state.pluginBotId?'on':''}" onclick="setPluginMode('')">全部插件</button>
        <button class="${state.pluginBotId?'on':''}" onclick="setPluginMode('per-bot')">按机器人</button>
      </div>
      ${state.pluginBotId ? '<input type="text" id="plugin-bot-id" placeholder="机器人ID" value="'+escapeAttr(state.pluginBotId)+'" oninput="state.pluginBotId=this.value" style="width:160px"><button class="btn primary" onclick="reloadPlugins()">查询</button>' : ''}
      ${!state.pluginBotId ? '<input type="text" placeholder="按名称/模块搜索" value="'+escapeAttr(state.pluginSearch)+'" oninput="state.pluginSearch=this.value; render()" style="width:220px">' : ''}
    </div>
    <div class="card">
      ${renderPluginTable()}
    </div>`;
}

function setPluginMode(mode) {
  if (mode === "per-bot") {
    // 进入按机器人模式，保留已填写的 botId
    if (!state.pluginBotId) state.pluginBotId = "";
  } else {
    state.pluginBotId = "";
  }
  state.plugins = null;
  loadView().then(render).catch(e => alertFlash("err", e.message));
}

async function reloadPlugins() {
  const input = document.getElementById("plugin-bot-id");
  if (input) state.pluginBotId = input.value.trim();
  state.plugins = null;
  loadView().then(render).catch(e => alertFlash("err", e.message));
}

function renderPluginTable() {
  const data = state.plugins;
  if (!data) return '<p class="muted">加载中…</p>';
  if (state.pluginBotId) {
    // 按机器人模式
    const plugins = data.plugins || [];
    const rows = plugins.map(p => `<tr>
      <td><strong>${escapeHtml(p.name)}</strong><br><code style="font-size:11px">${escapeHtml(p.module)}</code></td>
      <td>${escapeHtml(p.menu_type || '-')}</td>
      <td>${escapeHtml(p.author || '-')} ${p.version?'<code style="font-size:11px">'+escapeHtml(p.version)+'</code>':''}</td>
      <td>${p.load_status?'<span class="tag ok">成功</span>':'<span class="tag err">失败</span>'}</td>
      <td>${fmtStatus(p.enabled_for_bot)}</td>
      <td>
        <div class="toggle">
          <button class="${p.enabled_for_bot?'on':''}" onclick="togglePlugin('${escapeAttr(state.pluginBotId)}','${escapeAttr(p.module)}', true)">启用</button>
          <button class="${!p.enabled_for_bot?'on':''}" onclick="togglePlugin('${escapeAttr(state.pluginBotId)}','${escapeAttr(p.module)}', false)">禁用</button>
        </div>
      </td>
    </tr>`).join("");
    return `<h2>机器人 ${escapeHtml(state.pluginBotId)} 的插件（${plugins.length}）</h2>
      <p class="muted" style="font-size:12px;margin-top:0">为该机器人单独启用/禁用插件。操作需登录鉴权。</p>
      <div class="row" style="margin-bottom:10px">
        <button class="btn small primary" onclick="toggleAllPlugins(true)">全部启用</button>
        <button class="btn small danger" onclick="toggleAllPlugins(false)">全部禁用</button>
      </div>
      <table><thead><tr><th>插件</th><th>分类</th><th>作者/版本</th><th>加载</th><th>状态</th><th>切换</th></tr></thead>
      <tbody>${rows || '<tr><td colspan="6" class="muted">暂无插件</td></tr>'}</tbody></table>`;
  }
  // 全部插件模式
  const plugins = data.plugins || [];
  const filtered = plugins.filter(p => {
    if (state.pluginMenuFilter && p.menu_type !== state.pluginMenuFilter) return false;
    if (state.pluginSearch) {
      const q = state.pluginSearch.toLowerCase();
      if (!String(p.name).toLowerCase().includes(q) && !String(p.module).toLowerCase().includes(q)) return false;
    }
    return true;
  });
  const menuTypes = data.menu_types || [];
  const filterBar = menuTypes.length ? `<div class="group-bar">
    <button class="${!state.pluginMenuFilter?'active':''}" onclick="state.pluginMenuFilter=''; render()">全部</button>
    ${menuTypes.map(t => `<button class="${state.pluginMenuFilter===t?'active':''}" onclick="state.pluginMenuFilter='${escapeAttr(t)}'; render()">${escapeHtml(t)}</button>`).join("")}
  </div>` : "";
  const rows = filtered.map(p => `<tr>
    <td><strong>${escapeHtml(p.name)}</strong><br><code style="font-size:11px">${escapeHtml(p.module)}</code></td>
    <td>${escapeHtml(p.menu_type || '-')}</td>
    <td>${escapeHtml(p.author || '-')} ${p.version?'<code style="font-size:11px">'+escapeHtml(p.version)+'</code>':''}</td>
    <td>${p.load_status?'<span class="tag ok">成功</span>':'<span class="tag err">失败</span>'}</td>
    <td>${p.status?fmtBool(p.status):'<span class="tag">-</span>'}</td>
    <td><span class="tag">${escapeHtml(p.plugin_type || '-')}</span></td>
    <td><span class="tag info">${escapeHtml(String(p.cost_gold))}</span></td>
  </tr>`).join("");
  return `${filterBar}
    <h2>插件列表（${filtered.length}/${plugins.length}）</h2>
    <p class="muted" style="font-size:12px;margin-top:0">查看全部已加载插件。如需对单个机器人启停插件，请切换"按机器人"模式。</p>
    <table><thead><tr><th>插件</th><th>分类</th><th>作者/版本</th><th>加载</th><th>全局开关</th><th>类型</th><th>金币</th></tr></thead>
    <tbody>${rows || '<tr><td colspan="7" class="muted">暂无插件</td></tr>'}</tbody></table>`;
}

async function togglePlugin(botId, module, enabled) {
  try {
    await api("/plugins/toggle", { method: "POST", body: { bot_id: botId, module, enabled } });
    alertFlash("ok", `${module} 已${enabled?'启用':'禁用'}（${botId}）`);
    await loadView(); render();
  } catch (e) { alertFlash("err", "操作失败：" + e.message); }
}

async function toggleAllPlugins(enabled) {
  if (!confirm(`确认${enabled?'启用':'禁用'}机器人 ${state.pluginBotId} 的全部插件？`)) return;
  try {
    await api("/plugins/toggle_all", { method: "POST", body: { bot_id: state.pluginBotId, enabled } });
    alertFlash("ok", `已${enabled?'启用':'禁用'}全部插件（${state.pluginBotId}）`);
    await loadView(); render();
  } catch (e) { alertFlash("err", "操作失败：" + e.message); }
}

// ========== 群组管理 ==========

function renderGroups() {
  const data = state.groups;
  if (!data) return `<div class="card muted">加载中…</div>`;
  const groups = data.groups || [];
  const filtered = groups.filter(g => {
    if (state.groupStatusFilter === "on" && !g.status) return false;
    if (state.groupStatusFilter === "off" && g.status) return false;
    if (state.groupSearch) {
      const q = state.groupSearch.toLowerCase();
      if (!String(g.group_id).toLowerCase().includes(q) && !String(g.group_name).toLowerCase().includes(q)) return false;
    }
    return true;
  });
  const rows = filtered.map(g => `<tr>
    <td><code>${escapeHtml(g.group_id)}</code></td>
    <td>${escapeHtml(g.group_name || '-')}</td>
    <td>${escapeHtml(g.platform || '-')}</td>
    <td>${escapeHtml(String(g.member_count))} / ${escapeHtml(String(g.max_member_count))}</td>
    <td>
      <input type="number" min="0" max="10" value="${escapeAttr(String(g.level))}" style="width:64px"
             aria-label="群 ${escapeAttr(g.group_id)} 权限等级"
             onchange="setGroupLevel('${escapeAttr(g.group_id)}', this.value)">
    </td>
    <td>${fmtStatus(g.status)}</td>
    <td>${g.is_super?'<span class="tag warn">超级群</span>':'<span class="tag">普通</span>'}</td>
    <td>${g.proactive_allowed?fmtBool(g.proactive_allowed):'<span class="tag">-</span>'}</td>
    <td>
      <div class="row" style="gap:4px">
        <button class="btn small" onclick="toggleGroupStatus('${escapeAttr(g.group_id)}', ${!g.status})">${g.status?'禁用':'启用'}</button>
        <button class="btn small" onclick="toggleSuperGroup('${escapeAttr(g.group_id)}')">${g.is_super?'取消超级':'设为超级'}</button>
        <button class="btn small" onclick="toggleProactive('${escapeAttr(g.group_id)}', ${!g.proactive_allowed})">${g.proactive_allowed?'禁止主动':'允许主动'}</button>
      </div>
    </td>
  </tr>`).join("");
  return `<div class="toolbar">
      <div class="toggle">
        <button class="${!state.groupStatusFilter?'on':''}" onclick="state.groupStatusFilter=''; render()">全部</button>
        <button class="${state.groupStatusFilter==='on'?'on':''}" onclick="state.groupStatusFilter='on'; render()">启用</button>
        <button class="${state.groupStatusFilter==='off'?'on':''}" onclick="state.groupStatusFilter='off'; render()">禁用</button>
      </div>
      <input type="text" placeholder="按群号/群名搜索" value="${escapeAttr(state.groupSearch)}" oninput="state.groupSearch=this.value; render()" style="width:200px">
    </div>
    <div class="card">
      <h2>群组列表（${filtered.length}/${groups.length}）</h2>
      <p class="muted" style="font-size:12px;margin-top:0">
        管理群组权限等级与状态。等级直接修改生效，其余操作需登录鉴权。
      </p>
      <table><thead><tr><th>群号</th><th>群名</th><th>平台</th><th>人数</th><th>等级</th><th>状态</th><th>类型</th><th>主动消息</th><th>操作</th></tr></thead>
      <tbody>${rows || '<tr><td colspan="9" class="muted">暂无群组</td></tr>'}</tbody></table>
    </div>`;
}

async function setGroupLevel(groupId, level) {
  const lv = Number(level);
  if (isNaN(lv) || lv < 0 || lv > 10) { alertFlash("err", "等级需为 0-10"); return; }
  try {
    await api("/groups/level", { method: "POST", body: { group_id: groupId, level: lv } });
    alertFlash("ok", `群 ${groupId} 等级已设为 ${lv}`);
    await loadView(); render();
  } catch (e) { alertFlash("err", "操作失败：" + e.message); }
}

async function toggleGroupStatus(groupId, status) {
  try {
    await api("/groups/status", { method: "POST", body: { group_id: groupId, status } });
    alertFlash("ok", `群 ${groupId} 已${status?'启用':'禁用'}`);
    await loadView(); render();
  } catch (e) { alertFlash("err", "操作失败：" + e.message); }
}

async function toggleSuperGroup(groupId) {
  try {
    const r = await api("/groups/super", { method: "POST", body: { group_id: groupId } });
    alertFlash("ok", `群 ${groupId} ${r.is_super?'已设为超级群':'已取消超级群'}`);
    await loadView(); render();
  } catch (e) { alertFlash("err", "操作失败：" + e.message); }
}

async function toggleProactive(groupId, allowed) {
  try {
    await api("/groups/proactive", { method: "POST", body: { group_id: groupId, allowed } });
    alertFlash("ok", `群 ${groupId} ${allowed?'已允许':'已禁止'}主动消息`);
    await loadView(); render();
  } catch (e) { alertFlash("err", "操作失败：" + e.message); }
}

// 注册视图
VIEWS.dashboard = renderDashboard;
VIEWS.bots = renderBots;
VIEWS.plugins = renderPlugins;
VIEWS.groups = renderGroups;
