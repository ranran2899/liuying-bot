// 流萤AI WebUI 内容模块
// 记忆查看（/memory/summary, /memory/clear）+ 情绪状态（/emotion/{user_id}）

// ========== 记忆查看 ==========

function renderMemory() {
  const mem = state.memory;
  if (!mem) return `<div class="card muted">加载中…</div>`;
  const items = mem.memories || [];
  const rows = items.map(it => `<tr>
    <td><span class="tag">${escapeHtml(it.tier || '-')}</span></td>
    <td><code style="font-size:11px">${escapeHtml(it.user_id || '')}${it.group_id ? '/'+escapeHtml(it.group_id) : ''}</code></td>
    <td>${escapeHtml(it.summary || it.content || '')}</td>
    <td class="muted" style="font-size:12px">${escapeHtml(it.create_time || it.created_at || '')}</td>
  </tr>`).join("");
  return `<div class="toolbar">
      <input type="text" placeholder="按 user_id 过滤" value="${escapeAttr(state.memoryUserId)}"
             oninput="state.memoryUserId=this.value" style="width:160px">
      <input type="text" placeholder="按 group_id 过滤" value="${escapeAttr(state.memoryGroupId)}"
             oninput="state.memoryGroupId=this.value" style="width:160px">
      <select onchange="state.memoryLimit=Number(this.value); loadView().then(render)">
        ${[20, 50, 100, 200].map(n => `<option value="${n}" ${Number(state.memoryLimit)===n?'selected':''}>显示 ${n} 条</option>`).join('')}
      </select>
      <button class="btn primary" onclick="reloadMemory()">应用</button>
      ${(state.memoryUserId || state.memoryGroupId) ? '<button class="btn small" onclick="clearMemoryFilters()">清除过滤</button>' : ''}
    </div>
    <div class="card">
      <div class="between">
        <h2 style="margin:0">记忆摘要（${mem.count || items.length}）</h2>
        <button class="btn small danger" onclick="clearUserMemory()">清空该用户记忆</button>
      </div>
      <p class="muted" style="font-size:12px;margin:8px 0">
        显示 AI 插件记忆系统蒸馏后的记忆条目。清空操作需超级用户权限，且仅清空当前 user_id 的记忆。
      </p>
      <table><thead><tr><th>层级</th><th>作用域</th><th>摘要</th><th>时间</th></tr></thead>
      <tbody>${rows || '<tr><td colspan="4" class="muted">暂无记忆条目</td></tr>'}</tbody></table>
    </div>`;
}

async function reloadMemory() {
  try { await loadView(); render(); }
  catch (e) { alertFlash("err", e.message); }
}

async function clearMemoryFilters() {
  state.memoryUserId = "";
  state.memoryGroupId = "";
  try { await loadView(); render(); }
  catch (e) { alertFlash("err", e.message); }
}

async function clearUserMemory() {
  const uid = state.memoryUserId || "global";
  if (!confirm(`确认清空用户 ${uid} 的所有记忆？此操作不可撤销。`)) return;
  try {
    await api("/memory/clear", {
      method: "POST",
      params: { user_id: uid, group_id: state.memoryGroupId },
    });
    alertFlash("ok", `已清空用户 ${uid} 的记忆`);
    await loadView();
    render();
  } catch (e) {
    alertFlash("err", "清空失败：" + e.message);
  }
}

// ========== 情绪状态 ==========

function renderEmotion() {
  const emo = state.emotion;
  return `<div class="toolbar">
      <input type="text" placeholder="输入用户 QQ" value="${escapeAttr(state.emotionUserId)}"
             oninput="state.emotionUserId=this.value"
             onkeydown="if(event.key==='Enter')loadEmotion()" style="width:200px">
      <button class="btn primary" onclick="loadEmotion()">查询</button>
    </div>
    <div class="card">
      ${emo ? renderEmotionDetail(emo) : '<p class="muted">请输入用户 QQ 后查询情绪状态。</p>'}
    </div>`;
}

function renderEmotionDetail(emo) {
  const warm = emo.relation_warmth;
  const thoughts = emo.pending_thoughts || [];
  const thoughtList = thoughts.length
    ? `<h3>待处理想法（${thoughts.length}）</h3><ul>${thoughts.map(t => `<li>${escapeHtml(t)}</li>`).join("")}</ul>`
    : '';
  return `<h2>用户 ${escapeHtml(emo.user_id)} 的情绪状态</h2>
    <div class="kv-grid">
      <div class="kv-item"><div class="k">心情 mood</div><div class="v">${Number(emo.mood ?? 0).toFixed(2)}</div></div>
      <div class="kv-item"><div class="k">能量 energy</div><div class="v">${Number(emo.energy ?? 0).toFixed(2)}</div></div>
      <div class="kv-item"><div class="k">关系亲密度</div><div class="v">${Number(warm ?? 0).toFixed(2)}</div></div>
    </div>
    ${thoughtList}`;
}

async function loadEmotion() {
  if (!state.emotionUserId) { alertFlash("err", "请输入用户 QQ"); return; }
  try {
    state.emotion = await api("/emotion/" + encodeURIComponent(state.emotionUserId));
    render();
  } catch (e) {
    alertFlash("err", "查询失败：" + e.message);
  }
}

// 注册视图
VIEWS.memory = renderMemory;
VIEWS.emotion = renderEmotion;
