/**
 * 流萤 WebUI - 漂流瓶管理页（bottle 插件扩展页面）
 * 提供漂流瓶与评论的审核功能，复用 web_ui 的 JWT 认证
 * 注意：引用内置模块必须使用绝对路径，且不要追加版本参数（避免产生双实例）
 */
import { api, unwrap } from '/assets/js/core/api.js';
import { toast, table, pagination, confirm, modal, loading, empty } from '/assets/js/components/ui.js';
import { icon } from '/assets/js/components/icons.js';
import { h, escapeHtml, formatTime } from '/assets/js/core/utils.js';
import { bus } from '/assets/js/core/eventbus.js';
import { setPageBg } from '/assets/js/core/pagebg.js';

let stats = null;
let currentBottle = null;
let currentComment = null;
let imageZoomEl = null;

// 瓶子列表状态
let listState = {
  page: 1,
  size: 20,
  status: '', // '' | 0 | 100 | 200
  total: 0,
  items: [],
  selected: new Set(),
};

const STATUS_LABELS = {
  0: { text: '待审核', class: 'badge--warning' },
  100: { text: '已拒绝', class: 'badge--danger' },
  200: { text: '已通过', class: 'badge--success' },
};

/** 渲染漂流瓶管理页 */
export default async function renderBottle() {
  // 设置本页全屏壁纸（路由切走时由本体自动淡出）
  setPageBg('/bottle_ext/img/流萤壁纸.png');

  const content = document.getElementById('app-content');
  content.innerHTML = '';
  const page = h('div', { class: 'page page--bottle' });
  content.appendChild(page);

  // 顶部统计
  const statGrid = h('div', { class: 'grid grid--4', id: 'stat-grid' });
  page.appendChild(statGrid);

  // Tab 切换
  const tabs = h('div', { class: 'tabs' });
  tabs.innerHTML = `
    <div class="tab tab--active" data-tab="bottle">${icon('bottle', 14)} 瓶子审核</div>
    <div class="tab" data-tab="comment">${icon('chat', 14)} 评论审核</div>
    <div class="tab" data-tab="list">${icon('table', 14)} 瓶子列表</div>
  `;
  page.appendChild(tabs);

  const tabContent = h('div', { id: 'bottle-tab-content' });
  page.appendChild(tabContent);

  tabs.querySelectorAll('.tab').forEach((t) => {
    t.addEventListener('click', () => {
      tabs.querySelectorAll('.tab').forEach((x) => x.classList.toggle('tab--active', x === t));
      switchTab(t.dataset.tab);
    });
  });

  await loadStats();
  renderStats();
  await switchTab('bottle');

  bus.on('route:change', onRouteChange);
  window.addEventListener('beforeunload', cleanup);
}

/** 清理资源 */
function cleanup() {
  stats = null;
  currentBottle = null;
  currentComment = null;
  closeImageZoom();
  listState = { page: 1, size: 20, status: '', total: 0, items: [], selected: new Set() };
  bus.off('route:change', onRouteChange);
  window.removeEventListener('beforeunload', cleanup);
}

/** 路由变化时检查是否需要清理 */
function onRouteChange() {
  if (!location.hash.startsWith('#/bottle')) {
    cleanup();
  }
}

/** 切换 Tab */
async function switchTab(tab) {
  const wrap = document.getElementById('bottle-tab-content');
  if (!wrap) return;
  if (tab === 'bottle') await renderBottleTab(wrap);
  else if (tab === 'comment') await renderCommentTab(wrap);
  else if (tab === 'list') await renderListTab(wrap);
}

/** 加载统计信息 */
async function loadStats() {
  const data = await unwrap(api.get('/bottle/get_stats'));
  stats = data || null;
}

/** 渲染顶部统计卡片 */
function renderStats() {
  const grid = document.getElementById('stat-grid');
  if (!grid) return;
  grid.innerHTML = '';
  if (!stats) {
    grid.appendChild(empty('无统计数据'));
    return;
  }
  const cards = [
    { label: '待审核瓶子', value: stats.pending_bottles, icon: 'bottle', color: 'var(--status-warning)' },
    { label: '待审核评论', value: stats.pending_comments, icon: 'chat', color: 'var(--status-danger)' },
    { label: '瓶子总数', value: stats.total_bottles, icon: 'database', color: 'var(--accent-firefly)' },
    { label: '评论总数', value: stats.total_comments, icon: 'comment', color: 'var(--accent-firefly-dim)' },
  ];
  cards.forEach((c) => {
    const card = h('div', { class: 'card stat-card' }, [
      h('div', { class: 'flex items-center justify-between' }, [
        h('div', { class: 'stat-card__label text-sm text-secondary', text: c.label }),
        h('span', { html: icon(c.icon, 18, 'stat-card__icon'), style: `color:${c.color};` }),
      ]),
      h('div', { class: 'stat-card__value', text: String(c.value ?? 0) }),
    ]);
    grid.appendChild(card);
  });
}

/** 渲染瓶子审核 Tab */
async function renderBottleTab(wrap) {
  wrap.innerHTML = '';
  const card = h('div', { class: 'card' }, [
    h('div', { class: 'flex justify-between items-center mb-md' }, [
      h('div', { class: 'card__title', style: 'margin:0;', html: icon('bottle', 16, 'card__title-icon') + ' 待审核瓶子' }),
      h('div', { class: 'flex gap-sm' }, [
        h('button', { class: 'btn btn--sm', id: 'btn-skip-bottle', html: icon('refresh', 14) + ' 换一个' }),
      ]),
    ]),
    h('div', { id: 'bottle-detail' }),
  ]);
  wrap.appendChild(card);
  document.getElementById('btn-skip-bottle').addEventListener('click', () => loadRandomBottle());
  await loadRandomBottle();
}

/** 加载随机待审核瓶子 */
async function loadRandomBottle() {
  const detail = document.getElementById('bottle-detail');
  if (!detail) return;
  detail.innerHTML = '';
  const l = loading(detail, '加载中');
  const data = await unwrap(api.get('/bottle/bottles/random'));
  l.close();
  if (!data) {
    detail.appendChild(empty('没有待审核的瓶子', 'success'));
    currentBottle = null;
    await refreshStats();
    return;
  }
  currentBottle = data;
  renderBottleDetail(detail, data);
}

/** 渲染瓶子详情 */
function renderBottleDetail(container, bottle) {
  container.innerHTML = '';
  const info = h('div', { class: 'bottle-detail' }, [
    h('div', { class: 'flex items-center gap-sm mb-md' }, [
      h('span', { class: 'badge badge--warning', text: `ID: ${bottle.id}` }),
      h('span', { class: 'badge', text: `平台: ${escapeHtml(bottle.platform || 'unknown')}` }),
      h('span', { class: 'badge badge--info', text: `点赞: ${bottle.like_count ?? 0}` }),
    ]),
    h('div', { class: 'info-row' }, [
      h('span', { class: 'info-row__label text-secondary text-sm', text: '发送者UID' }),
      h('span', { class: 'info-row__value text-mono', text: bottle.uid || '无' }),
    ]),
    h('div', { class: 'info-row' }, [
      h('span', { class: 'info-row__label text-secondary text-sm', text: '用户ID' }),
      h('span', { class: 'info-row__value text-mono text-sm', text: bottle.user_id || '-' }),
    ]),
    h('div', { class: 'info-row' }, [
      h('span', { class: 'info-row__label text-secondary text-sm', text: '发送时间' }),
      h('span', { class: 'info-row__value text-sm', text: formatTime(bottle.create_time) }),
    ]),
    h('div', { class: 'info-row info-row--column' }, [
      h('span', { class: 'info-row__label text-secondary text-sm', text: '内容' }),
      h('div', { class: 'info-row__content', html: escapeHtml(bottle.content || '(空)') }),
    ]),
  ]);
  container.appendChild(info);

  // 图片展示
  if (Array.isArray(bottle.images) && bottle.images.length > 0) {
    const imgWrap = h('div', { class: 'bottle-images' });
    bottle.images.forEach((b64) => {
      const img = h('img', {
        class: 'bottle-image',
        src: `data:image/png;base64,${b64}`,
        alt: '漂流瓶图片',
        onClick: (e) => openImageZoom(e.currentTarget),
      });
      imgWrap.appendChild(img);
    });
    container.appendChild(imgWrap);
  }

  // 操作按钮
  const actions = h('div', { class: 'flex gap-sm mt-md' }, [
    h('button', {
      class: 'btn btn--success',
      html: icon('check', 14) + ' 通过',
      onClick: () => approveBottle(bottle.id),
    }),
    h('button', {
      class: 'btn btn--danger',
      html: icon('close', 14) + ' 拒绝',
      onClick: () => refuseBottle(bottle.id),
    }),
  ]);
  container.appendChild(actions);
}

/** 审核通过瓶子 */
async function approveBottle(bottleId) {
  const r = await api.post(`/bottle/bottles/approve/${bottleId}`);
  if (!r) return;
  if (r.suc) {
    toast.success(r.info || '审核通过');
    await loadRandomBottle();
    await refreshStats();
  } else {
    toast.danger(r.info || '操作失败');
  }
}

/** 拒绝瓶子 */
async function refuseBottle(bottleId) {
  const r = await api.post(`/bottle/bottles/refuse/${bottleId}`);
  if (!r) return;
  if (r.suc) {
    toast.success(r.info || '已拒绝');
    await loadRandomBottle();
    await refreshStats();
  } else {
    toast.danger(r.info || '操作失败');
  }
}

/** 渲染评论审核 Tab */
async function renderCommentTab(wrap) {
  wrap.innerHTML = '';
  const card = h('div', { class: 'card' }, [
    h('div', { class: 'flex justify-between items-center mb-md' }, [
      h('div', { class: 'card__title', style: 'margin:0;', html: icon('chat', 16, 'card__title-icon') + ' 待审核评论' }),
      h('div', { class: 'flex gap-sm' }, [
        h('button', { class: 'btn btn--sm', id: 'btn-skip-comment', html: icon('refresh', 14) + ' 换一个' }),
      ]),
    ]),
    h('div', { id: 'comment-detail' }),
  ]);
  wrap.appendChild(card);
  document.getElementById('btn-skip-comment').addEventListener('click', () => loadRandomComment());
  await loadRandomComment();
}

/** 加载随机待审核评论 */
async function loadRandomComment() {
  const detail = document.getElementById('comment-detail');
  if (!detail) return;
  detail.innerHTML = '';
  const l = loading(detail, '加载中');
  const data = await unwrap(api.get('/bottle/comments/random'));
  l.close();
  if (!data) {
    detail.appendChild(empty('没有待审核的评论', 'success'));
    currentComment = null;
    await refreshStats();
    return;
  }
  currentComment = data;
  renderCommentDetail(detail, data);
}

/** 渲染评论详情 */
function renderCommentDetail(container, comment) {
  container.innerHTML = '';
  const info = h('div', { class: 'bottle-detail' }, [
    h('div', { class: 'flex items-center gap-sm mb-md' }, [
      h('span', { class: 'badge badge--warning', text: `评论ID: ${comment.id}` }),
      h('span', { class: 'badge badge--info', text: `瓶子ID: ${comment.bottle_id}` }),
    ]),
    h('div', { class: 'info-row' }, [
      h('span', { class: 'info-row__label text-secondary text-sm', text: '评论者UID' }),
      h('span', { class: 'info-row__value text-mono', text: comment.uid || '无' }),
    ]),
    h('div', { class: 'info-row' }, [
      h('span', { class: 'info-row__label text-secondary text-sm', text: '用户ID' }),
      h('span', { class: 'info-row__value text-mono text-sm', text: comment.user_id || '-' }),
    ]),
    h('div', { class: 'info-row' }, [
      h('span', { class: 'info-row__label text-secondary text-sm', text: '评论时间' }),
      h('span', { class: 'info-row__value text-sm', text: formatTime(comment.create_time) }),
    ]),
    h('div', { class: 'info-row info-row--column' }, [
      h('span', { class: 'info-row__label text-secondary text-sm', text: '评论内容' }),
      h('div', { class: 'info-row__content', html: escapeHtml(comment.content || '(空)') }),
    ]),
  ]);
  container.appendChild(info);

  const actions = h('div', { class: 'flex gap-sm mt-md' }, [
    h('button', {
      class: 'btn btn--success',
      html: icon('check', 14) + ' 通过',
      onClick: () => approveComment(comment.id),
    }),
    h('button', {
      class: 'btn btn--danger',
      html: icon('close', 14) + ' 拒绝',
      onClick: () => refuseComment(comment.id),
    }),
  ]);
  container.appendChild(actions);
}

/** 审核通过评论 */
async function approveComment(commentId) {
  const r = await api.post(`/bottle/comments/approve/${commentId}`);
  if (!r) return;
  if (r.suc) {
    toast.success(r.info || '审核通过');
    await loadRandomComment();
    await refreshStats();
  } else {
    toast.danger(r.info || '操作失败');
  }
}

/** 拒绝评论 */
async function refuseComment(commentId) {
  const r = await api.post(`/bottle/comments/refuse/${commentId}`);
  if (!r) return;
  if (r.suc) {
    toast.success(r.info || '已拒绝');
    await loadRandomComment();
    await refreshStats();
  } else {
    toast.danger(r.info || '操作失败');
  }
}

/** 刷新统计 */
async function refreshStats() {
  await loadStats();
  renderStats();
}

/** 打开图片放大遮罩 */
function openImageZoom(imgEl) {
  closeImageZoom();
  const mask = h('div', {
    class: 'image-zoom-mask',
    onClick: closeImageZoom,
  });
  const clone = h('img', {
    class: 'image-zoom__img',
    src: imgEl.src,
    alt: '放大图片',
  });
  mask.appendChild(clone);
  document.body.appendChild(mask);
  imageZoomEl = mask;
  // ESC 关闭放大遮罩
  const escHandler = (e) => {
    if (e.key === 'Escape') closeImageZoom();
  };
  document.addEventListener('keydown', escHandler);
  imageZoomEl._escHandler = escHandler;
}

/** 关闭图片放大遮罩 */
function closeImageZoom() {
  if (imageZoomEl) {
    if (imageZoomEl._escHandler) {
      document.removeEventListener('keydown', imageZoomEl._escHandler);
    }
    imageZoomEl.remove();
    imageZoomEl = null;
  }
}

/* ========== 瓶子列表 Tab ========== */

/** 渲染瓶子列表 Tab */
async function renderListTab(wrap) {
  wrap.innerHTML = '';
  // 工具栏
  const toolbar = h('div', { class: 'toolbar mb-md' });
  toolbar.innerHTML = `
    <label class="flex items-center gap-xs text-sm" style="white-space:nowrap;">
      <input type="checkbox" id="list-select-all" style="width:auto;"> 全选
    </label>
    <select id="list-status-filter" class="btn" style="width:auto;">
      <option value="">全部状态</option>
      <option value="0">待审核</option>
      <option value="100">已拒绝</option>
      <option value="200">已通过</option>
    </select>
    <button class="btn btn--sm" id="list-refresh">${icon('refresh', 14)} 刷新</button>
    <button class="btn btn--danger btn--sm" id="list-batch-delete" disabled>${icon('delete', 14)} 批量删除</button>
    <span class="text-sm text-tertiary" id="list-selected-info"></span>
  `;
  wrap.appendChild(toolbar);

  // 表格容器
  const tableWrap = h('div', { id: 'list-table-wrap' });
  wrap.appendChild(tableWrap);

  // 分页容器
  const pagWrap = h('div', { id: 'list-pagination', class: 'mt-md' });
  wrap.appendChild(pagWrap);

  // 绑定事件
  document.getElementById('list-status-filter').addEventListener('change', (e) => {
    listState.status = e.target.value;
    listState.page = 1;
    listState.selected.clear();
    loadBottleList();
  });
  document.getElementById('list-refresh').addEventListener('click', () => loadBottleList());
  document.getElementById('list-batch-delete').addEventListener('click', batchDeleteBottles);
  document.getElementById('list-select-all').addEventListener('change', (e) => {
    if (e.target.checked) {
      listState.items.forEach((it) => listState.selected.add(it.id));
    } else {
      listState.selected.clear();
    }
    renderListTable();
    updateSelectedInfo();
  });

  await loadBottleList();
}

/** 加载瓶子列表 */
async function loadBottleList() {
  const tableWrap = document.getElementById('list-table-wrap');
  const pagWrap = document.getElementById('list-pagination');
  if (!tableWrap) return;
  tableWrap.innerHTML = '';
  const l = loading(tableWrap, '加载中');
  const query = { index: listState.page, size: listState.size };
  if (listState.status !== '') query.status = listState.status;
  const data = await unwrap(api.get('/bottle/bottles/list', query));
  l.close();
  if (!data) return;
  listState.total = data.total || 0;
  listState.items = Array.isArray(data.data) ? data.data : [];
  renderListTable();
  renderListPagination(pagWrap);
  updateSelectedInfo();
}

/** 渲染列表表格 */
function renderListTable() {
  const tableWrap = document.getElementById('list-table-wrap');
  if (!tableWrap) return;
  tableWrap.innerHTML = '';
  if (listState.items.length === 0) {
    tableWrap.appendChild(empty('无漂流瓶数据', 'bottle'));
    return;
  }
  const columns = [
    {
      key: '__select',
      title: '',
      width: '40px',
      render: (_, row) => {
        const checked = listState.selected.has(row.id);
        return `<input type="checkbox" class="list-row-select" data-id="${row.id}" ${checked ? 'checked' : ''} style="width:auto;">`;
      },
    },
    {
      key: 'id',
      title: 'ID',
      width: '70px',
      render: (v) => `<span class="text-mono">${v}</span>`,
    },
    {
      key: 'content',
      title: '内容',
      render: (v) => {
        const text = v || '(空)';
        const truncated = text.length > 50 ? text.slice(0, 50) + '...' : text;
        return `<span title="${escapeHtml(text)}">${escapeHtml(truncated)}</span>`;
      },
    },
    {
      key: 'status',
      title: '状态',
      width: '90px',
      render: (v) => {
        const s = STATUS_LABELS[v] || { text: String(v), class: '' };
        return `<span class="badge ${s.class}">${s.text}</span>`;
      },
    },
    {
      key: 'image_count',
      title: '图片',
      width: '80px',
      render: (v, row) => v > 0
        ? `<button class="badge badge--info list-row-images" data-id="${row.id}" title="点击查看图片" style="cursor:pointer;border:none;font:inherit;">${icon('image', 12)} ${v}</button>`
        : '<span class="text-tertiary">-</span>',
    },
    {
      key: 'like_count',
      title: '点赞',
      width: '60px',
      render: (v) => `<span class="text-mono">${v || 0}</span>`,
    },
    {
      key: 'platform',
      title: '平台',
      width: '100px',
      render: (v) => `<span class="text-mono text-sm">${escapeHtml(v || 'unknown')}</span>`,
    },
    {
      key: 'user_id',
      title: '发送者',
      width: '140px',
      render: (v) => `<span class="text-mono text-sm" title="${escapeHtml(v || '')}">${escapeHtml(v || '-')}</span>`,
    },
    {
      key: 'create_time',
      title: '创建时间',
      width: '160px',
      render: (v) => `<span class="text-sm text-secondary">${formatTime(v)}</span>`,
    },
    {
      key: '__actions',
      title: '操作',
      width: '90px',
      render: (_, row) => `<button class="btn btn--danger btn--sm list-row-delete" data-id="${row.id}">${icon('delete', 12)} 删除</button>`,
    },
  ];
  tableWrap.appendChild(table(columns, listState.items));

  // 绑定行内复选框
  tableWrap.querySelectorAll('.list-row-select').forEach((cb) => {
    cb.addEventListener('change', (e) => {
      const id = Number(e.target.dataset.id);
      if (e.target.checked) listState.selected.add(id);
      else listState.selected.delete(id);
      updateSelectedInfo();
    });
  });
  // 绑定行内删除按钮
  tableWrap.querySelectorAll('.list-row-delete').forEach((btn) => {
    btn.addEventListener('click', (e) => {
      const id = Number(e.currentTarget.dataset.id);
      deleteBottle(id);
    });
  });
  // 绑定图片查看按钮
  tableWrap.querySelectorAll('.list-row-images').forEach((btn) => {
    btn.addEventListener('click', (e) => {
      const id = Number(e.currentTarget.dataset.id);
      showBottleImages(id);
    });
  });
}

/** 渲染分页 */
function renderListPagination(pagWrap) {
  pagWrap.innerHTML = '';
  pagWrap.appendChild(pagination({
    current: listState.page,
    total: listState.total,
    pageSize: listState.size,
    onChange: (p) => {
      listState.page = p;
      loadBottleList();
    },
  }));
}

/** 更新选中信息与按钮状态 */
function updateSelectedInfo() {
  const info = document.getElementById('list-selected-info');
  const btn = document.getElementById('list-batch-delete');
  const selectAll = document.getElementById('list-select-all');
  const count = listState.selected.size;
  if (info) info.textContent = count > 0 ? `已选 ${count} 项` : '';
  if (btn) btn.disabled = count === 0;
  // 全选 checkbox 状态联动
  if (selectAll) {
    const allOnPage = listState.items.map((it) => it.id);
    const allSelected = allOnPage.length > 0 && allOnPage.every((id) => listState.selected.has(id));
    selectAll.checked = allSelected;
  }
}

/** 删除单个漂流瓶 */
function deleteBottle(bottleId) {
  confirm({
    title: '确认删除',
    content: `确定要删除漂流瓶 #${bottleId} 吗？关联的图片、评论和点赞记录将一并清理，此操作不可恢复。`,
    okText: '删除',
    cancelText: '取消',
    danger: true,
    onOk: async () => {
      const r = await api.delete(`/bottle/bottles/${bottleId}`);
      if (!r) return;
      if (r.suc) {
        toast.success(r.info || '删除成功');
        listState.selected.delete(bottleId);
        await loadBottleList();
        await refreshStats();
      } else {
        toast.danger(r.info || '删除失败');
      }
    },
  });
}

/** 批量删除漂流瓶 */
function batchDeleteBottles() {
  const ids = Array.from(listState.selected);
  if (ids.length === 0) {
    toast.warning('请先选择要删除的瓶子');
    return;
  }
  confirm({
    title: '批量删除确认',
    content: `确定要删除选中的 ${ids.length} 个漂流瓶吗？此操作不可恢复。`,
    okText: '批量删除',
    cancelText: '取消',
    danger: true,
    onOk: async () => {
      const r = await api.post('/bottle/bottles/batch_delete', { ids });
      if (!r) return;
      if (r.suc) {
        const result = r.data || { success: [], failed: [] };
        toast.success(`成功删除 ${result.success.length} 条，失败 ${result.failed.length} 条`);
        listState.selected.clear();
        await loadBottleList();
        await refreshStats();
      } else {
        toast.danger(r.info || '批量删除失败');
      }
    },
  });
}

/** 查看漂流瓶图片 */
async function showBottleImages(bottleId) {
  const m = modal({
    title: `漂流瓶 #${bottleId} 的图片`,
    size: 'lg',
    body: h('div'),
  });
  const l = loading(m.body, '加载图片中');
  const data = await unwrap(api.get(`/bottle/bottles/${bottleId}/images`));
  l.close();
  m.body.innerHTML = '';
  if (!data) {
    m.body.appendChild(empty('加载失败'));
    return;
  }
  const images = data.images || [];
  if (images.length === 0) {
    m.body.appendChild(empty('该瓶子没有图片'));
    return;
  }
  const grid = h('div', { class: 'bottle-images' });
  images.forEach((b64) => {
    const img = h('img', {
      class: 'bottle-image',
      src: `data:image/png;base64,${b64}`,
      alt: '漂流瓶图片',
      title: '点击放大查看',
      onClick: (e) => openImageZoom(e.currentTarget),
    });
    grid.appendChild(img);
  });
  m.body.appendChild(grid);
}
