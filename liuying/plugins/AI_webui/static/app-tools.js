// 流萤AI WebUI 视觉能力模块
// 对接 /vision/capability (GET) 与 /vision/preferred (POST)
// 提供视觉 provider 能力概览与首选 provider 设置

function renderVision() {
  const v = state.vision;
  if (!v) return `<div class="card muted">加载中…</div>`;

  // 顶部摘要卡片
  const supported = v.vision_supported;
  const supportedPill = supported
    ? '<span class="tag" style="background:rgba(52,211,153,0.18);color:var(--ok)">已支持</span>'
    : '<span class="tag" style="background:rgba(248,113,113,0.18);color:var(--danger)">未支持</span>';
  const cached = v.cached_probes || 0;
  const preferred = v.preferred_provider
    ? `<code>${escapeHtml(v.preferred_provider)}</code>${v.preferred_model ? ` <span class="muted">/</span> <code>${escapeHtml(v.preferred_model)}</code>` : ''}`
    : '<span class="muted">未设置（自动路由）</span>';
  const ts = v.timestamp
    ? new Date(v.timestamp).toLocaleString()
    : '-';

  // 设置首选 provider 表单
  const formCard = `<div class="card">
    <h2>设置首选视觉 Provider</h2>
    <p class="muted" style="font-size:12.5px;margin-top:0">
      指定视觉请求优先使用的 provider 与模型。留空则由路由层自动选择支持视觉的 provider。
      需要超级用户权限（auth_uid 自动注入）。
    </p>
    <div class="field-input" style="margin-top:10px">
      <input id="vision-provider" type="text" placeholder="provider 名（如 openai / zhipu）"
        value="${escapeAttr(state.visionProvider || v.preferred_provider || '')}"
        style="min-width:220px;flex:1">
      <input id="vision-model" type="text" placeholder="模型名（如 gpt-4o）"
        value="${escapeAttr(state.visionModel || v.preferred_model || '')}"
        style="min-width:220px;flex:1">
      <button class="btn primary" onclick="setVisionPreferred()">保存</button>
      ${v.preferred_provider ? '<button class="btn" onclick="clearVisionPreferred()">清除首选</button>' : ''}
    </div>
  </div>`;

  // 能力概览
  const overviewCard = `<div class="card">
    <h2>能力概览</h2>
    <div class="row" style="gap:30px">
      <div>
        <div class="muted">视觉支持</div>
        <div style="font-size:18px;margin-top:4px">${supportedPill}</div>
      </div>
      <div>
        <div class="muted">已缓存探测</div>
        <div style="font-size:18px;margin-top:4px">${cached}</div>
      </div>
      <div>
        <div class="muted">当前首选</div>
        <div style="font-size:14px;margin-top:6px">${preferred}</div>
      </div>
      <div>
        <div class="muted">检测时间</div>
        <div style="font-size:13px;margin-top:6px">${escapeHtml(ts)}</div>
      </div>
    </div>
  </div>`;

  // 完整 JSON 详情（参考插件的 details 折叠风格）
  const detailCard = `<div class="card">
    <h2>原始响应</h2>
    <details open>
      <summary class="muted">点击折叠/展开完整 JSON</summary>
      <pre style="white-space:pre-wrap;font-size:12px;background:var(--input-bg);padding:10px;border-radius:6px;overflow-x:auto;margin-top:8px">${escapeHtml(JSON.stringify(v, null, 2))}</pre>
    </details>
  </div>`;

  return overviewCard + formCard + detailCard;
}

async function setVisionPreferred() {
  const providerEl = document.getElementById("vision-provider");
  const modelEl = document.getElementById("vision-model");
  const provider = (providerEl?.value || "").trim();
  const model = (modelEl?.value || "").trim();
  if (!provider || !model) {
    alertFlash("err", "provider 与 model 均不能为空");
    return;
  }
  try {
    await api("/vision/preferred", {
      method: "POST",
      params: { provider, model },
    });
    state.visionProvider = provider;
    state.visionModel = model;
    alertFlash("ok", `已设置首选视觉 provider: ${provider}/${model}`);
    state.vision = await api("/vision/capability");
    render();
  } catch (e) {
    alertFlash("err", "设置失败：" + e.message);
  }
}

async function clearVisionPreferred() {
  // 通过传入空字符串清除首选（后端 set_preferred 接受任意字符串）
  // 这里采用设置为空串的方式，由后端处理
  try {
    await api("/vision/preferred", {
      method: "POST",
      params: { provider: "", model: "" },
    });
    state.visionProvider = "";
    state.visionModel = "";
    alertFlash("ok", "已清除首选视觉 provider");
    state.vision = await api("/vision/capability");
    render();
  } catch (e) {
    alertFlash("err", "清除失败：" + e.message);
  }
}

VIEWS.vision = renderVision;
