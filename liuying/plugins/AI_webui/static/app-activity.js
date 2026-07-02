// 流萤AI WebUI 活动统计模块
// Token 统计（/token/summary）+ 知识库统计（/knowledge/stats）

// ========== Token 统计 ==========

function renderToken() {
  const data = state.token;
  if (!data) return `<div class="card muted">加载中…</div>`;
  const stats = data.stats || {};
  const tabs = [1, 7, 30, 90].map(d =>
    `<button class="${Number(state.tokenDays)===d?'active':''}" onclick="switchTokenDays(${d})">${d} 天</button>`
  ).join("");
  return `<div class="group-bar">${tabs}</div>
    <div class="card">
      <h2>Token 使用统计（最近 ${data.days} 天）</h2>
      <p class="muted" style="font-size:12px;margin-top:0">
        统计 AI 插件通过 LLM 模块发起的所有调用，按 prompt/completion 分别计量。
      </p>
      ${renderTokenSummary(stats)}
      <h3>完整统计详情</h3>
      ${fmtJson(stats)}
    </div>`;
}

function renderTokenSummary(stats) {
  const total = stats.total_input || stats.prompt_tokens || 0;
  const totalOut = stats.total_output || stats.completion_tokens || 0;
  const calls = stats.total_calls || stats.call_count || 0;
  const byProvider = stats.by_provider || stats.by_model || {};
  const providerRows = Object.keys(byProvider).length
    ? Object.entries(byProvider).map(([k, v]) => `<tr>
        <td>${escapeHtml(k)}</td>
        <td>${escapeHtml(String(v.total_input ?? v.prompt_tokens ?? '-'))}</td>
        <td>${escapeHtml(String(v.total_output ?? v.completion_tokens ?? '-'))}</td>
        <td>${escapeHtml(String(v.total_calls ?? v.call_count ?? '-'))}</td>
      </tr>`).join("")
    : '';
  return `<div class="kv-grid" style="margin-bottom:14px">
      <div class="kv-item"><div class="k">输入 token</div><div class="v">${Number(total).toLocaleString()}</div></div>
      <div class="kv-item"><div class="k">输出 token</div><div class="v">${Number(totalOut).toLocaleString()}</div></div>
      <div class="kv-item"><div class="k">调用次数</div><div class="v">${Number(calls).toLocaleString()}</div></div>
    </div>
    ${providerRows ? `<h3>按 provider 统计</h3><table>
      <thead><tr><th>Provider</th><th>输入</th><th>输出</th><th>调用</th></tr></thead>
      <tbody>${providerRows}</tbody></table>` : ''}`;
}

async function switchTokenDays(days) {
  state.tokenDays = days;
  try { await loadView(); render(); }
  catch (e) { alertFlash("err", e.message); }
}

// ========== 知识库统计 ==========

function renderKnowledge() {
  const data = state.knowledge;
  if (!data) return `<div class="card muted">加载中…</div>`;
  const stats = data.stats || {};
  return `<div class="card">
    <h2>插件知识库统计</h2>
    <p class="muted" style="font-size:12px;margin-top:0">
      AI 插件知识库存储已注册插件的功能描述与命令接口，供 Agent 工具调用参考。
    </p>
    ${fmtJson(stats)}
  </div>`;
}

// 注册视图
VIEWS.token = renderToken;
VIEWS.knowledge = renderKnowledge;
