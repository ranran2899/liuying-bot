// 流萤本体 WebUI 系统模块
// 系统信息 + 定时任务 + 日志查看 + 调用统计

// ========== 系统信息 ==========

function renderSystem() {
  const sys = state.system;
  if (!sys) return `<div class="card muted">加载中…</div>`;
  const kv = [
    ["机器人名称", sys.bot_name],
    ["机器人版本", sys.bot_version],
    ["Python 版本", sys.python_version],
    ["操作系统", `${sys.platform} ${sys.os_release}`],
    ["主机名", sys.hostname],
    ["CPU 核心", `${sys.cpu_count} 核`],
    ["进程 PID", sys.process_pid],
    ["线程数", sys.process_threads],
    ["运行时长", sys.uptime_text],
  ];
  return `<div class="card">
    <div class="between">
      <h2 style="margin:0">系统信息</h2>
      <button class="btn small" onclick="refreshSystem()">刷新</button>
    </div>
    <p class="muted" style="font-size:12px;margin:8px 0 0">流萤机器人本体运行环境概览。</p>
    <div class="kv-grid" style="margin-top:14px">
      ${kv.map(([k, v]) => `<div class="kv-item"><div class="k">${k}</div><div class="v">${escapeHtml(String(v))}</div></div>`).join("")}
    </div>
  </div>
  <div class="card">
    <h2>资源占用</h2>
    <div class="kv-grid" style="margin-bottom:14px">
      <div class="kv-item"><div class="k">CPU 使用率</div><div class="v">${escapeHtml(String(sys.cpu_percent))}%</div></div>
      <div class="kv-item"><div class="k">进程内存 RSS</div><div class="v">${fmtBytes(sys.process_memory_rss)}</div></div>
    </div>
    ${usageBar(sys.memory_percent, {name:"系统内存", label: `${fmtBytes(sys.memory_used)} / ${fmtBytes(sys.memory_total)}`})}
    ${usageBar(sys.disk_percent, {name:"磁盘占用", label: `${fmtBytes(sys.disk_used)} / ${fmtBytes(sys.disk_total)}`})}
  </div>`;
}

async function refreshSystem() {
  state.loading = true; render();
  try {
    state.system = await api("/system");
    alertFlash("ok", "系统信息已刷新");
  } catch (e) { alertFlash("err", "刷新失败：" + e.message); }
  state.loading = false; render();
}

// ========== 定时任务 ==========

const TASK_STATUS_CLS = {
  running: "ok", paused: "warn", pending: "",
  completed: "info", failed: "err",
};

function renderTasks() {
  const data = state.tasks;
  if (!data) return `<div class="card muted">加载中…</div>`;
  const tasks = data.tasks || [];
  const groups = data.groups || {};
  const groupBar = Object.keys(groups).length ? `<div class="group-bar">
    <button class="${!state.taskGroupFilter?'active':''}" onclick="state.taskGroupFilter=''; render()">全部分组 (${data.count})</button>
    ${Object.entries(groups).map(([g, n]) => `<button class="${state.taskGroupFilter===g?'active':''}" onclick="state.taskGroupFilter='${escapeAttr(g)}'; render()">${escapeHtml(g)} (${n})</button>`).join("")}
  </div>` : "";
  const rows = tasks.map(t => {
    const statusCls = TASK_STATUS_CLS[t.status] || "";
    return `<tr>
      <td><strong>${escapeHtml(t.name)}</strong><br><code style="font-size:11px">${escapeHtml(t.id)}</code></td>
      <td><span class="tag ${statusCls}">${escapeHtml(t.status)}</span></td>
      <td><span class="tag info">${escapeHtml(t.trigger_type)}</span></td>
      <td>${escapeHtml(t.group || '-')}</td>
      <td>${escapeHtml(String(t.run_count))}</td>
      <td class="muted" style="font-size:12px">${escapeHtml(t.last_run_time || '-')}</td>
      <td class="muted" style="font-size:12px">${escapeHtml(t.description || '-')}</td>
      <td>
        <div class="row" style="gap:4px">
          ${t.status === 'paused'
            ? `<button class="btn small primary" onclick="resumeTask('${escapeAttr(t.id)}')">恢复</button>`
            : `<button class="btn small" onclick="pauseTask('${escapeAttr(t.id)}')">暂停</button>`}
          <button class="btn small" onclick="runTaskNow('${escapeAttr(t.id)}')">立即执行</button>
          <button class="btn small danger" onclick="removeTask('${escapeAttr(t.id)}')">移除</button>
        </div>
      </td>
    </tr>`;
  }).join("");
  return `${groupBar}
    <div class="card">
      <h2>定时任务（${tasks.length}/${data.count}）</h2>
      <p class="muted" style="font-size:12px;margin-top:0">
        流萤内置调度器任务列表。暂停/恢复/执行/移除操作需登录鉴权。
        调度器状态：${data.started ? '<span class="tag ok">运行中</span>' : '<span class="tag">未启动</span>'}
      </p>
      <table><thead><tr><th>任务</th><th>状态</th><th>触发器</th><th>分组</th><th>运行次数</th><th>上次运行</th><th>描述</th><th>操作</th></tr></thead>
      <tbody>${rows || '<tr><td colspan="8" class="muted">暂无任务</td></tr>'}</tbody></table>
    </div>`;
}

async function pauseTask(taskId) {
  try {
    const r = await api("/tasks/pause", { method: "POST", body: { task_id: taskId } });
    alertFlash(r.ok ? "ok" : "err", r.ok ? `${taskId} 已暂停` : "暂停失败");
    await loadView(); render();
  } catch (e) { alertFlash("err", "操作失败：" + e.message); }
}

async function resumeTask(taskId) {
  try {
    const r = await api("/tasks/resume", { method: "POST", body: { task_id: taskId } });
    alertFlash(r.ok ? "ok" : "err", r.ok ? `${taskId} 已恢复` : "恢复失败");
    await loadView(); render();
  } catch (e) { alertFlash("err", "操作失败：" + e.message); }
}

async function runTaskNow(taskId) {
  if (!confirm(`确认立即执行任务 ${taskId}？`)) return;
  try {
    const r = await api("/tasks/run", { method: "POST", body: { task_id: taskId } });
    alertFlash(r.ok ? "ok" : "err", r.ok ? `${taskId} 已触发执行` : "触发失败");
  } catch (e) { alertFlash("err", "操作失败：" + e.message); }
}

async function removeTask(taskId) {
  if (!confirm(`确认移除任务 ${taskId}？此操作不可撤销。`)) return;
  try {
    const r = await api("/tasks", { method: "DELETE", params: { task_id: taskId } });
    alertFlash(r.ok ? "ok" : "err", r.ok ? `${taskId} 已移除` : "移除失败");
    await loadView(); render();
  } catch (e) { alertFlash("err", "操作失败：" + e.message); }
}

// ========== 日志查看 ==========

function renderLogs() {
  const data = state.logs;
  if (!data) return `<div class="card muted">加载中…</div>`;
  const files = data.files || [];
  if (!files.length) return `<div class="card"><h2>日志查看</h2><p class="muted">暂无日志文件。</p></div>`;
  // 默认选最新文件
  if (!state.logFile) state.logFile = files[0].name;
  const fileBar = files.map(f => `<button class="${state.logFile===f.name?'active':''}" onclick="selectLog('${escapeAttr(f.name)}')">${escapeHtml(f.name)} <span class="muted" style="font-size:11px">(${fmtBytes(f.size)})</span></button>`).join("");
  let logBlock = "";
  if (state.logContent) {
    const c = state.logContent;
    const lines = (c.lines || []).map(l => `<span class="log-line">${escapeHtml(l)}</span>`).join("");
    logBlock = `<div class="between" style="margin-bottom:8px">
      <span class="muted" style="font-size:12px">${escapeHtml(c.name)} · 共 ${c.total_lines} 行 · 显示尾部 ${c.returned} 行 ${c.truncated?'（已截断）':''}</span>
      <select aria-label="日志显示行数" onchange="state.logLines=Number(this.value); loadView().then(render)">
        ${[200, 400, 800, 2000].map(n => `<option value="${n}" ${Number(state.logLines)===n?'selected':''}>尾部 ${n} 行</option>`).join("")}
      </select>
    </div>
    <div class="log-viewer" id="log-viewer">${lines || '<span class="muted">（空日志）</span>'}</div>`;
  } else {
    logBlock = '<p class="muted">选择日志文件查看内容…</p>';
  }
  return `<div class="card">
    <h2>日志查看</h2>
    <p class="muted" style="font-size:12px;margin-top:0">日志文件位于 <code>log/</code> 目录，按修改时间倒序排列。仅展示尾部内容，避免大文件阻塞。</p>
    <div class="log-files">${fileBar}</div>
    ${logBlock}
  </div>`;
}

function selectLog(name) {
  state.logFile = name;
  state.logContent = null;
  loadView().then(render).catch(e => alertFlash("err", e.message));
}

// ========== 调用统计 ==========

function renderStats() {
  const data = state.stats;
  if (!data) return `<div class="card muted">加载中…</div>`;
  const recent = data.recent || [];
  const rows = recent.map(r => `<tr>
    <td><code style="font-size:11px">${escapeHtml(r.plugin_name || '-')}</code></td>
    <td>${escapeHtml(r.user_id || '-')}</td>
    <td>${escapeHtml(r.group_id || '-')}</td>
    <td>${escapeHtml(r.bot_id || '-')}</td>
    <td class="muted" style="font-size:12px">${escapeHtml(r.create_time || '-')}</td>
  </tr>`).join("");
  const metrics = [
    ["总调用次数", data.total],
    ["插件种类", Object.keys(data.by_plugin || {}).length],
    ["涉及群组", Object.keys(data.by_group || {}).length],
    ["涉及用户", Object.keys(data.by_user || {}).length],
  ].map(([k, v]) => `<div class="metric-card">
    <div class="metric-k">${k}</div>
    <div class="metric-v">${escapeHtml(String(v))}</div>
  </div>`).join("");
  return `<div class="card">
    <div class="between">
      <h2 style="margin:0">调用统计</h2>
      <select aria-label="统计记录数量" onchange="state.statsLimit=Number(this.value); loadView().then(render)">
        ${[50, 100, 200, 500].map(n => `<option value="${n}" ${Number(state.statsLimit)===n?'selected':''}>最近 ${n} 条</option>`).join("")}
      </select>
    </div>
    <div class="metric-grid" style="margin-top:14px">${metrics}</div>
  </div>
  <div class="card">
    <h3>按插件调用次数</h3>
    ${statBars(data.by_plugin)}
  </div>
  <div class="row" style="gap:16px;align-items:flex-start">
    <div class="card" style="flex:1;min-width:280px">
      <h3>按群组调用次数</h3>
      ${statBars(data.by_group)}
    </div>
    <div class="card" style="flex:1;min-width:280px">
      <h3>按用户调用次数</h3>
      ${statBars(data.by_user)}
    </div>
  </div>
  <div class="card">
    <h2>最近调用记录（${recent.length}）</h2>
    <table><thead><tr><th>插件</th><th>用户</th><th>群组</th><th>Bot</th><th>时间</th></tr></thead>
    <tbody>${rows || '<tr><td colspan="5" class="muted">暂无记录</td></tr>'}</tbody></table>
  </div>`;
}

// 注册视图
VIEWS.system = renderSystem;
VIEWS.tasks = renderTasks;
VIEWS.logs = renderLogs;
VIEWS.stats = renderStats;
