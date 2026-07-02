// 流萤AI WebUI 配置中心模块
// 对接 /config (GET) 与 /config/value (POST)
// 支持分组切换、搜索过滤、按类型编辑（bool/int/float/str/secret）

function renderConfig() {
  const entries = state.configEntries || [];
  const groups = state.configGroups || [];
  const search = (state.configSearch || "").trim().toLowerCase();
  const searchTokens = search ? search.split(/\s+/).filter(Boolean) : [];

  // 搜索过滤
  let items = entries;
  let activeGroup = state.activeConfigGroup;
  if (searchTokens.length) {
    items = items.filter(e => {
      const hay = [e.key, e.help_text, e.group, e.value_type].join(" ").toLowerCase();
      return searchTokens.every(t => hay.includes(t));
    });
    activeGroup = null;
  } else if (activeGroup) {
    items = items.filter(e => e.group === activeGroup);
  }

  // 分组切换条
  const groupBar = !search ? groups.map(g => {
    const count = entries.filter(e => e.group === g).length;
    return `<button class="${g===activeGroup?'active':''}" onclick="pickConfigGroup('${escapeAttr(g)}')">${escapeHtml(g)} <span class="muted" style="font-size:11px">${count}</span></button>`;
  }).join("") : "";

  const heading = search ? `搜索结果（${items.length}）` : (activeGroup || "配置");
  return `<div class="toolbar">
      <input id="config-search-input" type="search" placeholder="搜索配置键名 / 说明 / 分组…"
             value="${escapeAttr(state.configSearch)}"
             oninput="state.configSearch=this.value;render()" style="flex:1;max-width:340px">
      <span class="muted">共 ${entries.length} 项</span>
    </div>
    <div class="alert info" style="margin-bottom:10px;font-size:12.5px">
      配置由 <code>plugins2config.yaml</code> 持久化；敏感字段（如 API Key）显示为 <code>***</code>。
      修改需超级用户权限。
    </div>
    ${groupBar ? `<div class="group-bar">${groupBar}</div>` : ''}
    <div class="card">
      <h2>${escapeHtml(heading)}</h2>
      ${items.length ? items.map(renderConfigField).join("") : '<p class="muted">无匹配配置项</p>'}
    </div>`;
}

function pickConfigGroup(g) {
  state.activeConfigGroup = g;
  render();
}

function renderConfigField(e) {
  const tags = [];
  if (e.secret) tags.push(`<span class="tag secret">敏感</span>`);
  tags.push(`<span class="tag source-${escapeAttr(e.group)}">${escapeHtml(e.group)}</span>`);
  const inputHtml = renderConfigInput(e);
  return `<div class="field" data-field="${escapeAttr(e.key)}">
    <div class="field-head"><strong>${escapeHtml(e.key)}</strong>${tags.join("")}</div>
    <div class="field-desc">${escapeHtml(e.help_text || '')}</div>
    <div class="field-input">${inputHtml}</div>
  </div>`;
}

function renderConfigInput(e) {
  const cur = e.value;
  const fieldType = e.value_type;
  const field = escapeAttr(e.key);
  if (fieldType === "bool") {
    const on = cur === true || cur === "true" || cur === 1;
    return `<div class="toggle">
      <button class="${on?'on':''}" onclick="saveConfigValue('${field}', true)">开</button>
      <button class="${!on?'on':''}" onclick="saveConfigValue('${field}', false)">关</button>
    </div>`;
  }
  if (fieldType === "int") {
    return `<input type="number" step="1" value="${escapeAttr(cur==null?'':cur)}" oninput="this.dataset.dirty='1'">
      <button class="btn small primary" onclick="commitConfigText('${field}', this, 'int')">保存</button>`;
  }
  if (fieldType === "float") {
    return `<input type="number" step="0.01" value="${escapeAttr(cur==null?'':cur)}" oninput="this.dataset.dirty='1'">
      <button class="btn small primary" onclick="commitConfigText('${field}', this, 'float')">保存</button>`;
  }
  if (e.secret) {
    return `<input type="password" placeholder="${cur ? '已设置（输入新值覆盖）' : '未设置'}" oninput="this.dataset.dirty='1'">
      <button class="btn small primary" onclick="commitConfigText('${field}', this, 'secret')">保存</button>`;
  }
  return `<input type="text" value="${escapeAttr(cur==null?'':cur)}" oninput="this.dataset.dirty='1'">
    <button class="btn small primary" onclick="commitConfigText('${field}', this, 'text')">保存</button>`;
}

async function commitConfigText(field, btn, kind) {
  const wrap = btn.parentElement;
  const input = wrap.querySelector("input");
  if (!input) return;
  let value = input.value;
  if (kind === "int") value = parseInt(value, 10);
  else if (kind === "float") value = parseFloat(value);
  await saveConfigValue(field, value);
}

async function saveConfigValue(field, value) {
  try {
    const result = await api("/config/value", {
      method: "POST",
      body: { key: field, value },
    });
    if (result.ok) {
      alertFlash("ok", `已保存 ${field}，重启后仍生效`);
      await loadView();
      render();
    } else {
      alertFlash("err", `保存失败`);
    }
  } catch (e) {
    alertFlash("err", "保存失败：" + e.message);
  }
}

// 注册视图
VIEWS.config = renderConfig;
