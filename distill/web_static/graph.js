const TYPE_COLORS = {
  source: '#F97316',
  project: '#38BDF8',
  concept: '#A78BFA',
  entity: '#34D399',
  decision: '#FB7185',
  constraint: '#FBBF24',
  output: '#6EE7B7',
};

const state = {
  graphData: { nodes: [], edges: [] },
  sigma: null,
  graph: null,
  selectedNodeId: null,
};

const els = {
  container: document.getElementById('graph-container'),
  statusPill: document.getElementById('status-pill'),
  nodeDetails: document.getElementById('node-details'),
  vaultStatus: document.getElementById('vault-status'),
  searchInput: document.getElementById('search-input'),
  searchButton: document.getElementById('search-button'),
  refreshButton: document.getElementById('refresh-button'),
  searchResults: document.getElementById('search-results'),
  communityList: document.getElementById('community-list'),
};

async function fetchJSON(url, options = {}) {
  const response = await fetch(url, options);
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`);
  }
  return response.json();
}

function setStatus(text) {
  els.statusPill.textContent = text;
}

function colorForType(type) {
  return TYPE_COLORS[type] || '#94A3B8';
}

function buildGraph(data) {
  const GraphClass = graphology.Graph;
  const graph = new GraphClass();

  data.nodes.forEach((node, index) => {
    graph.addNode(node.id, {
      label: node.label,
      x: Number.isFinite(node.x) ? node.x : Math.cos(index) * 10,
      y: Number.isFinite(node.y) ? node.y : Math.sin(index) * 10,
      size: node.size || 8,
      color: colorForType(node.type),
      type: node.type,
      path: node.path,
      status: node.status,
      word_count: node.word_count || 0,
    });
  });

  data.edges.forEach((edge) => {
    if (!graph.hasNode(edge.source) || !graph.hasNode(edge.target)) return;
    const edgeId = edge.id || `${edge.source}->${edge.target}:${edge.type || 'link'}`;
    if (!graph.hasEdge(edgeId)) {
      graph.addEdgeWithKey(edgeId, edge.source, edge.target, {
        size: 1,
        color: 'rgba(148, 163, 184, 0.28)',
        label: edge.type || 'link',
      });
    }
  });

  return graph;
}

function renderGraph(data) {
  state.graphData = data;
  if (state.sigma) {
    state.sigma.kill();
  }

  const graph = buildGraph(data);
  state.graph = graph;
  state.sigma = new sigma.Sigma(graph, els.container, {
    renderEdgeLabels: false,
    labelRenderedSizeThreshold: 10,
    minCameraRatio: 0.08,
    maxCameraRatio: 10,
  });

  state.sigma.on('clickNode', ({ node }) => {
    selectNode(node);
  });

  state.sigma.on('clickStage', () => {
    clearSelection();
  });

  setStatus(`图谱: ${data.nodes.length} 节点 / ${data.edges.length} 边`);
}

function renderStatus(status) {
  const stats = status.stats || {};
  const graph = status.graph || {};
  const stale = status.staleness || {};
  els.vaultStatus.innerHTML = `
    <div class="meta-item"><div class="meta-label">Vault</div><div>${escapeHtml(status.vault || '-')}</div></div>
    <div class="meta-item"><div class="meta-label">对象总数</div><div>${stats.total_objects ?? 0}</div></div>
    <div class="meta-item"><div class="meta-label">图节点/边</div><div>${graph.nodes ?? 0} / ${graph.edges ?? 0}</div></div>
    <div class="meta-item"><div class="meta-label">Broken Links</div><div>${stats.broken_links ?? 0}</div></div>
    <div class="meta-item"><div class="meta-label">Orphans</div><div>${stats.orphan_objects ?? 0}</div></div>
    <div class="meta-item"><div class="meta-label">Staleness</div><div>${stale.stale ? 'STALE' : 'FRESH'} (${stale.total_changes ?? 0})</div></div>
  `;
}

function renderCommunities(payload) {
  const communities = payload.communities || [];
  if (!communities.length) {
    els.communityList.innerHTML = '<div class="muted">暂无社区数据</div>';
    return;
  }
  els.communityList.innerHTML = communities.slice(0, 8).map((community) => `
    <div class="card">
      <div class="card-title">${escapeHtml(community.label || community.id)}</div>
      <div class="card-subtle">成员: ${community.size} · 密度: ${community.density}</div>
      <div class="card-subtle">关键词: ${escapeHtml((community.keywords || []).join(', '))}</div>
    </div>
  `).join('');
}

function renderSearchResults(payload) {
  const results = payload.results || [];
  if (!results.length) {
    els.searchResults.innerHTML = '<div class="muted">没有搜索结果</div>';
    return;
  }
  els.searchResults.innerHTML = results.map((item) => `
    <div class="card" data-path="${encodeURIComponent(item.path)}">
      <div class="card-title">${escapeHtml(item.title || item.path)}</div>
      <div class="card-subtle">${escapeHtml(item.type || 'unknown')} · ${escapeHtml(item.path)}</div>
      <div class="card-subtle">${escapeHtml(item.excerpt || '')}</div>
    </div>
  `).join('');

  els.searchResults.querySelectorAll('[data-path]').forEach((el) => {
    el.addEventListener('click', () => {
      const path = decodeURIComponent(el.dataset.path);
      focusNodeByPath(path);
      loadObjectDetails(path);
    });
  });
}

function clearSelection() {
  state.selectedNodeId = null;
  els.nodeDetails.innerHTML = `
    <div class="meta-item">
      <div class="meta-label">状态</div>
      <div>点击左侧节点查看详情</div>
    </div>
  `;
}

function escapeHtml(value) {
  return String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

async function selectNode(nodeId) {
  state.selectedNodeId = nodeId;
  const attrs = state.graph?.getNodeAttributes(nodeId) || {};
  await loadObjectDetails(attrs.path || nodeId, attrs);
}

async function loadObjectDetails(path, attrs = null) {
  try {
    const [objectData, impactData] = await Promise.all([
      fetchJSON(`/api/object?path=${encodeURIComponent(path)}`),
      fetchJSON(`/api/impact?path=${encodeURIComponent(path)}&direction=upstream`),
    ]);

    const meta = attrs || state.graph?.getNodeAttributes(path) || {};
    const backlinks = (objectData.backlinks || []).slice(0, 8).join(', ') || '无';
    const outlinks = (objectData.outlinks || []).slice(0, 8).join(', ') || '无';
    const impacted = impactData.total_affected ?? 0;

    els.nodeDetails.innerHTML = `
      <div class="meta-item"><div class="meta-label">标题</div><div>${escapeHtml(objectData.title || meta.label || path)}</div></div>
      <div class="meta-item"><div class="meta-label">路径</div><div>${escapeHtml(objectData.path || path)}</div></div>
      <div class="meta-item"><div class="meta-label">类型</div><div>${escapeHtml(objectData.type || meta.type || 'unknown')}</div></div>
      <div class="meta-item"><div class="meta-label">状态</div><div>${escapeHtml(objectData.status || meta.status || 'unknown')}</div></div>
      <div class="meta-item"><div class="meta-label">字数 / 影响</div><div>${meta.word_count || 0} / ${impacted}</div></div>
      <div class="meta-item"><div class="meta-label">Backlinks</div><div>${escapeHtml(backlinks)}</div></div>
      <div class="meta-item"><div class="meta-label">Outlinks</div><div>${escapeHtml(outlinks)}</div></div>
      <div class="meta-item"><div class="meta-label">Frontmatter</div><div class="code-block">${escapeHtml(JSON.stringify(objectData.frontmatter || {}, null, 2))}</div></div>
    `;
  } catch (error) {
    els.nodeDetails.innerHTML = `
      <div class="meta-item">
        <div class="meta-label">错误</div>
        <div>${escapeHtml(error.message)}</div>
      </div>
    `;
  }
}

function focusNodeByPath(path) {
  const nodeId = state.graph?.hasNode(path) ? path : null;
  if (!nodeId || !state.sigma) return;
  const attrs = state.graph.getNodeAttributes(nodeId);
  state.sigma.getCamera().animate({ x: attrs.x, y: attrs.y, ratio: 0.5 }, { duration: 600 });
  selectNode(nodeId);
}

async function runSearch() {
  const query = els.searchInput.value.trim();
  if (!query) {
    els.searchResults.innerHTML = '<div class="muted">请输入搜索词</div>';
    return;
  }
  setStatus(`搜索中: ${query}`);
  try {
    const results = await fetchJSON(`/api/search?q=${encodeURIComponent(query)}`);
    renderSearchResults(results);
    setStatus(`搜索完成: ${results.results?.length || 0} 条`);
  } catch (error) {
    els.searchResults.innerHTML = `<div class="muted">搜索失败: ${escapeHtml(error.message)}</div>`;
    setStatus('搜索失败');
  }
}

async function loadAll() {
  setStatus('加载图谱与状态...');
  try {
    const [graph, status, communities] = await Promise.all([
      fetchJSON('/api/graph'),
      fetchJSON('/api/status'),
      fetchJSON('/api/communities'),
    ]);
    renderGraph(graph);
    renderStatus(status);
    renderCommunities(communities);
  } catch (error) {
    setStatus(`加载失败: ${error.message}`);
    els.communityList.innerHTML = `<div class="muted">${escapeHtml(error.message)}</div>`;
  }
}

els.searchButton.addEventListener('click', runSearch);
els.refreshButton.addEventListener('click', loadAll);
els.searchInput.addEventListener('keydown', (event) => {
  if (event.key === 'Enter') {
    runSearch();
  }
});

loadAll();
