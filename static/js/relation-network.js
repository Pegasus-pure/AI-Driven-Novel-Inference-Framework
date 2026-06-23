/**
 * relation-network.js — 角色关系网（力导向节点图）
 *
 * 生命周期:
 *   1. 初始化: 惰性加载，由 CharactersRenderer._ensureNetworkInitialized() 触发
 *   2. 数据就绪: 监听 relation_network_init 事件，接收 characters + locations
 *   3. 渲染: Canvas 力导向布局，节点 = 角色，连线 = npc_relationships
 *   4. 销毁: 切换小说时重置
 *
 * 前后端接口（字段名统一）:
 *   - 输入: characters[].npc_relationships[{target, type, bond_strength}]
 *   - 输出: 关系网可视化（无后端写入）
 */

import { App } from './app.js';

// ═══════════════════════════════════════════════════════
// 力导向布局引擎
// ═══════════════════════════════════════════════════════

class ForceDirectedLayout {
  /**
   * @param {Array} nodes  - [{id, x, y, vx, vy}]
   * @param {Array} edges  - [{source, target, bond_strength}]
   * @param {Object} opts  - {width, height, ...}
   */
  constructor(nodes, edges, opts = {}) {
    this.nodes = nodes;
    this.edges = edges;

    // 物理参数
    this.repelK = opts.repelK || 12000;
    this.springK = opts.springK || 0.008;
    this.centerK = opts.centerK || 0.008;
    this.damping = opts.damping || 0.85;
    this.restLengthBase = opts.restLengthBase || 200;
    this.alpha = 1.0;
    this.alphaTarget = 0.001;
    this.alphaDecay = opts.alphaDecay || 0.025;
    this.velocityDecay = opts.velocityDecay || 0.3;
    this.width = opts.width || 600;
    this.height = opts.height || 400;
    this.cx = this.width / 2;
    this.cy = this.height / 2;

    // 初始化节点速度
    this.nodes.forEach(n => {
      n.vx = 0;
      n.vy = 0;
    });
  }

  /**
   * 执行一步模拟
   * @returns {boolean} 是否仍在收敛
   */
  tick() {
    if (this.alpha < this.alphaTarget) return false;

    const n = this.nodes.length;
    if (n < 2) {
      this.alpha = 0;
      return false;
    }

    // ── 库仑斥力（每对节点） ──
    for (let i = 0; i < n - 1; i++) {
      for (let j = i + 1; j < n; j++) {
        const a = this.nodes[i];
        const b = this.nodes[j];
        let dx = b.x - a.x;
        let dy = b.y - a.y;
        let dist = Math.sqrt(dx * dx + dy * dy);
        if (dist < 5) dist = 5;  // 防止除以零

        const force = (this.repelK * this.alpha) / (dist * dist);
        const fx = (dx / dist) * force;
        const fy = (dy / dist) * force;
        a.vx -= fx;
        a.vy -= fy;
        b.vx += fx;
        b.vy += fy;
      }
    }

    // ── 胡克弹力（有连线的节点对） ──
    for (const edge of this.edges) {
      const src = this.nodes.find(n => n.id === edge.source);
      const dst = this.nodes.find(n => n.id === edge.target);
      if (!src || !dst) continue;

      const dx = dst.x - src.x;
      const dy = dst.y - src.y;
      const dist = Math.sqrt(dx * dx + dy * dy) || 1;

      // 关系越好 restLength 越短
      const strength = edge.bond_strength != null ? edge.bond_strength : 0.5;
      const restLength = this.restLengthBase - strength * this.restLengthBase * 0.6;
      const displacement = dist - restLength;

      const force = this.springK * displacement * this.alpha;
      const fx = (dx / dist) * force;
      const fy = (dy / dist) * force;

      // 减少孤立节点对的影响力
      if (edge.bond_strength > 0) {
        src.vx += fx * strength;
        src.vy += fy * strength;
        dst.vx -= fx * strength;
        dst.vy -= fy * strength;
      }
    }

    // ── 中心引力 ──
    for (const node of this.nodes) {
      const dx = this.cx - node.x;
      const dy = this.cy - node.y;
      node.vx += dx * this.centerK * this.alpha;
      node.vy += dy * this.centerK * this.alpha;
    }

    // ── 应用速度 + 阻尼 ──
    for (const node of this.nodes) {
      node.vx *= this.damping;
      node.vy *= this.damping;

      // 限速
      const speed = Math.sqrt(node.vx * node.vx + node.vy * node.vy);
      if (speed > 10) {
        node.vx = (node.vx / speed) * 10;
        node.vy = (node.vy / speed) * 10;
      }

      node.x += node.vx;
      node.y += node.vy;

      // 宽松边界 — 防止极端漂移到完全不可见区域
      const boundW = Math.max(this.width * 3, 3000);
      const boundH = Math.max(this.height * 3, 2000);
      node.x = Math.max(-boundW, Math.min(boundW, node.x));
      node.y = Math.max(-boundH, Math.min(boundH, node.y));
    }

    this.alpha -= this.alphaDecay;
    return this.alpha >= this.alphaTarget;
  }

  /** 重置布局（随机初始位置） */
  reset(width, height) {
    this.width = width || this.width;
    this.height = height || this.height;
    this.cx = this.width / 2;
    this.cy = this.height / 2;
    this.alpha = 1.0;

    // 螺旋分布，避免完全随机导致太多重叠
    this.nodes.forEach((n, i) => {
      const angle = i * 2.4;  // 黄金角 ≈ 137.5°
      const radius = 80 + (i % 12) * 45;
      n.x = this.cx + Math.cos(angle) * radius;
      n.y = this.cy + Math.sin(angle) * radius;
      n.vx = 0;
      n.vy = 0;
    });
  }
}

// ═══════════════════════════════════════════════════════
// 连线样式映射
// ═══════════════════════════════════════════════════════

const RELATIONSHIP_STYLES = {
  // 按类型关键词
  love:       { color: '#e8797b', width: 2.5, dash: [],      label: '爱情' },
  romance:    { color: '#e8797b', width: 2.5, dash: [],      label: '爱情' },
  lover:      { color: '#e8797b', width: 2.5, dash: [],      label: '爱情' },
  spouse:     { color: '#e8797b', width: 2.5, dash: [],      label: '配偶' },
  family:     { color: '#c084fc', width: 2.0, dash: [],      label: '血缘' },
  sibling:    { color: '#c084fc', width: 2.0, dash: [],      label: '手足' },
  enemy:      { color: '#f87171', width: 1.8, dash: [6, 4],  label: '敌对' },
  rival:      { color: '#fb923c', width: 1.8, dash: [6, 4],  label: '竞争' },
  friend:     { color: '#4ade80', width: 2.0, dash: [],      label: '友好' },
  mentor:     { color: '#38bdf8', width: 1.8, dash: [3, 3],  label: '师徒' },
  master:     { color: '#38bdf8', width: 1.8, dash: [3, 3],  label: '师徒' },
  student:    { color: '#38bdf8', width: 1.5, dash: [3, 3],  label: '师徒' },
  colleague:  { color: '#a78bfa', width: 1.5, dash: [],      label: '同僚' },
  ally:       { color: '#34d399', width: 1.8, dash: [],      label: '盟友' },
};

const DEFAULT_EDGE_STYLE = { color: '#8892a4', width: 1.4, dash: [], label: '关系' };

/** 根据关系类型获取连线样式 */
function _getEdgeStyle(type) {
  if (!type) return DEFAULT_EDGE_STYLE;
  const t = type.toLowerCase();
  for (const [key, style] of Object.entries(RELATIONSHIP_STYLES)) {
    if (t.includes(key)) return style;
  }
  return DEFAULT_EDGE_STYLE;
}

// ═══════════════════════════════════════════════════════
// 角色头像配色（与 characters.js 保持一致）
// ═══════════════════════════════════════════════════════

const AVATAR_COLORS = ['#1a3a5c', '#3a1a2c', '#2a1a3c', '#1a3a3a', '#3a2a1a'];

// ═══════════════════════════════════════════════════════
// 关系网主类
// ═══════════════════════════════════════════════════════

export class RelationNetwork {
  constructor() {
    /** @type {HTMLElement} Canvas 容器 */
    this._container = null;
    /** @type {HTMLCanvasElement} Canvas 元素 */
    this._canvas = null;
    /** @type {CanvasRenderingContext2D} Canvas 上下文 */
    this._ctx = null;

    /** @type {Array} 节点列表 */
    this._nodes = [];
    /** @type {Array} 连线列表 */
    this._edges = [];

    /** @type {ForceDirectedLayout|null} 力导向布局引擎 */
    this._layout = null;

    /** @type {boolean} 是否已填充数据 */
    this._dataReady = false;
    /** @type {boolean} 是否渲染了 Canvas */
    this._canvasReady = false;
    /** @type {number|null} 动画帧 ID */
    this._animFrameId = null;

    // ── 交互状态 ──
    /** @type {Object|null} 当前拖拽的节点 */
    this._dragNode = null;
    /** @type {number} 拖拽偏移 */
    this._dragOffsetX = 0;
    this._dragOffsetY = 0;
    /** @type {boolean} 是否在拖拽中 */
    this._isDragging = false;
    /** @type {string|null} 选中的节点 ID */
    this._selectedNodeId = null;
    /** @type {string|null} 悬停的节点 ID */
    this._hoveredNodeId = null;
    /** @type {Object|null} 悬停的连线 */
    this._hoveredEdge = null;

    // ── 视图变换 ──
    /** @type {number} 缩放比例 */
    this._zoom = 1.0;
    /** @type {number} 视图偏移 */
    this._viewX = 0;
    this._viewY = 0;
    /** @type {boolean} 画布拖拽中 */
    this._panning = false;
    /** @type {number} 画布拖拽起点 */
    this._panStartX = 0;
    this._panStartY = 0;
    this._panViewStartX = 0;
    this._panViewStartY = 0;

    // ── 工具提示 ──
    /** @type {HTMLElement|null} 信息卡元素 */
    this._tooltip = null;

    // ── 过滤器 ──
    /** @type {string} 当前过滤器 */
    this._filter = 'all';

    // ── 角色名称映射 ──
    this._nameMap = {};
  }

  // ═══════════════════════════════════════════════════
  // 初始化
  // ═══════════════════════════════════════════════════

  init() {
    App.on('relation_network_init', (payload) => {
      if (payload && payload.characters) {
        this._buildGraph(payload.characters);
        this._renderCanvas();
      }
    });

    // 切换小说时重置
    App.on('novel_selected', () => {
      this._teardown();
    });

    console.log('[RelationNetwork] 初始化完成（惰性加载，等待数据）');
  }

  /** 销毁当前状态 */
  _teardown() {
    if (this._animFrameId) {
      cancelAnimationFrame(this._animFrameId);
      this._animFrameId = null;
    }
    this._nodes = [];
    this._edges = [];
    this._layout = null;
    this._dataReady = false;
    this._canvasReady = false;
    this._selectedNodeId = null;
    this._hoveredNodeId = null;
    this._hoveredEdge = null;
    this._dragNode = null;
    this._isDragging = false;
    this._zoom = 1.0;
    this._viewX = 0;
    this._viewY = 0;
    this._filter = 'all';
    this._container = null;
    this._canvas = null;
    this._ctx = null;
  }

  // ═══════════════════════════════════════════════════
  // 数据构建
  // ═══════════════════════════════════════════════════

  /**
   * 从角色数据构建图结构
   */
  _buildGraph(characters) {
    this._nodes = [];
    this._edges = [];
    this._nameMap = {};

    if (!characters || characters.length === 0) {
      return;
    }

    // 构建节点
    const nodeMap = {};
    characters.forEach((c, i) => {
      const node = {
        id: c.id || '',
        name: c.name || '??',
        role: c.role || '',
        x: 0,   // 由 reset 设置
        y: 0,
        vx: 0,
        vy: 0,
        colorIdx: i % AVATAR_COLORS.length,
        relationships: c.key_relationships || c.npc_relationships || [],
        // 运行时数据（可选）
        attitude: c.attitude || '',
      };
      this._nodes.push(node);
      nodeMap[node.id] = node;
      this._nameMap[node.id] = node.name;
    });

    // 构建连线
    this._nodes.forEach(source => {
      (source.relationships || []).forEach(rel => {
        if (nodeMap[rel.target]) {
          this._edges.push({
            source: source.id,
            target: rel.target,
            type: rel.type || '未知关系',
            bond_strength: rel.bond_strength != null ? rel.bond_strength 
                         : (rel.intensity != null ? rel.intensity : 0.5),
          });
        }
      });
    });

    this._deduplicateEdges();
    this._dataReady = true;

    console.log(`[RelationNetwork] 图构建完成: ${this._nodes.length} 节点, ${this._edges.length} 连线`);
  }

  /** 去重双向连线 */
  _deduplicateEdges() {
    const seen = new Set();
    this._edges = this._edges.filter(e => {
      const key1 = `${e.source}->${e.target}`;
      const key2 = `${e.target}->${e.source}`;
      if (seen.has(key1) || seen.has(key2)) return false;
      seen.add(key1);
      return true;
    });
  }

  // ═══════════════════════════════════════════════════
  // Canvas 渲染
  // ═══════════════════════════════════════════════════

  _renderCanvas() {
    // 停止旧动画
    if (this._animFrameId) {
      cancelAnimationFrame(this._animFrameId);
      this._animFrameId = null;
    }
    // 移除旧的事件监听
    if (this._resizeHandler) {
      window.removeEventListener('resize', this._resizeHandler);
    }

    const container = document.getElementById('relationNetworkContainer');
    if (!container) return;

    // 清空容器
    container.innerHTML = '';

    // 空状态检查
    if (this._nodes.length === 0) {
      container.innerHTML = `
        <div class="relation-network__placeholder">
          <p>暂无关系数据</p>
          <p class="relation-network__hint">角色缺少 npc_relationships 字段</p>
        </div>`;
      return;
    }

    if (this._nodes.length < 2) {
      container.innerHTML = `
        <div class="relation-network__placeholder">
          <p>至少需要 2 个角色才能形成关系网</p>
          <p class="relation-network__hint">当前角色数量: ${this._nodes.length}</p>
        </div>`;
      return;
    }

    // ── 工具栏 ──
    const toolbar = this._createToolbar();
    container.appendChild(toolbar);

    // ── 图例 ──
    const legend = this._createLegend();
    container.appendChild(legend);

    // ── Canvas ──
    const canvas = document.createElement('canvas');
    canvas.className = 'relation-network__canvas';
    container.appendChild(canvas);

    // ── 工具提示容器 ──
    const tooltip = document.createElement('div');
    tooltip.className = 'relation-tooltip';
    container.appendChild(tooltip);
    this._tooltip = tooltip;

    this._container = container;
    this._canvas = canvas;
    this._ctx = canvas.getContext('2d');

    // ── 窗口尺寸变化 ──
    this._resizeHandler = () => this._resizeCanvas();
    window.addEventListener('resize', this._resizeHandler);

    // ── 延迟初始化，确保 DOM 布局完成后读取正确尺寸 ──
    requestAnimationFrame(() => {
      this._resizeCanvas();
      this._canvasReady = true;
      this._initLayout();
      this._bindCanvasEvents();
      this._startAnimation();
    });

    console.log('[RelationNetwork] Canvas 已渲染');
  }

  /** 自适应 Canvas 尺寸（含 DPI 缩放） */
  _resizeCanvas() {
    if (!this._canvas || !this._ctx) return;

    const dpr = window.devicePixelRatio || 1;
    // 读 Canvas 自身已渲染的实际尺寸（CSS flex:1 会自动分配剩余高度）
    const rect = this._canvas.getBoundingClientRect();
    const w = Math.floor(rect.width);
    const h = Math.max(200, Math.floor(rect.height));

    this._canvas.width = w * dpr;
    this._canvas.height = h * dpr;
    this._canvas.style.width = w + 'px';
    this._canvas.style.height = h + 'px';
    this._ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

    this._canvasWidth = w;
    this._canvasHeight = h;

    // 更新布局尺寸
    if (this._layout) {
      this._layout.width = w;
      this._layout.height = h;
      this._layout.cx = w / 2;
      this._layout.cy = h / 2;
    }
  }

  /** 初始化力导向布局 */
  _initLayout() {
    if (!this._canvas) return;
    const w = this._canvasWidth || 600;
    const h = this._canvasHeight || 400;

    this._layout = new ForceDirectedLayout(this._nodes, this._edges, {
      width: w,
      height: h,
      repelK: 25000,
      springK: 0.006,
      centerK: 0.005,
      damping: 0.88,
      alphaDecay: 0.018,
      restLengthBase: 240,
    });

    this._layout.reset(w, h);
  }

  // ═══════════════════════════════════════════════════
  // 动画循环
  // ═══════════════════════════════════════════════════

  _startAnimation() {
    if (this._animFrameId) return;
    this._loop();
  }

  _loop = () => {
    // 运行布局
    if (this._layout) {
      this._layout.tick();
    }

    // 绘制
    this._draw();

    this._animFrameId = requestAnimationFrame(this._loop);
  };

  // ═══════════════════════════════════════════════════
  // Canvas 绘制
  // ═══════════════════════════════════════════════════

  _draw() {
    const ctx = this._ctx;
    if (!ctx || !this._canvas) return;

    const w = this._canvasWidth || 600;
    const h = this._canvasHeight || 400;

    // 清空
    ctx.clearRect(0, 0, w, h);

    // 应用视图变换
    ctx.save();
    ctx.translate(this._viewX, this._viewY);
    ctx.scale(this._zoom, this._zoom);

    // 绘制连线
    this._drawEdges(ctx);

    // 绘制节点
    this._drawNodes(ctx);

    ctx.restore();

    // 绘制节点标签（在变换外，保持文字清晰）
    // 标签在节点上方已绘制，不移出
  }

  /** 绘制连线 */
  _drawEdges(ctx) {
    const selectedId = this._selectedNodeId;

    for (const edge of this._edges) {
      const source = this._nodes.find(n => n.id === edge.source);
      const target = this._nodes.find(n => n.id === edge.target);
      if (!source || !target) continue;

      // 筛选
      if (this._filter !== 'all') {
        const style = _getEdgeStyle(edge.type);
        if (style.label !== this._filter) continue;
      }

      const style = _getEdgeStyle(edge.type);
      const isRelated = selectedId && (edge.source === selectedId || edge.target === selectedId);
      const isHovered = this._hoveredEdge === edge;

      ctx.beginPath();
      ctx.moveTo(source.x, source.y);
      ctx.lineTo(target.x, target.y);

      // 高亮关联连线
      if (isRelated) {
        ctx.strokeStyle = style.color;
        ctx.globalAlpha = 0.9;
        ctx.lineWidth = style.width + 1;
      } else if (selectedId) {
        ctx.strokeStyle = '#2d3748';
        ctx.globalAlpha = 0.15;
        ctx.lineWidth = style.width * 0.5;
      } else if (isHovered) {
        ctx.strokeStyle = '#60a5fa';
        ctx.globalAlpha = 0.85;
        ctx.lineWidth = style.width + 1;
      } else {
        ctx.strokeStyle = style.color;
        ctx.globalAlpha = 0.6;
        ctx.lineWidth = style.width;
      }

      if (style.dash.length > 0) {
        ctx.setLineDash(style.dash);
      } else {
        ctx.setLineDash([]);
      }

      ctx.stroke();
      ctx.globalAlpha = 1.0;
      ctx.setLineDash([]);
    }
  }

  /** 绘制节点 */
  _drawNodes(ctx) {
    const w = this._canvasWidth || 600;
    const h = this._canvasHeight || 400;
    const selectedId = this._selectedNodeId;
    const hoveredId = this._hoveredNodeId;

    for (const node of this._nodes) {
      const isSelected = node.id === selectedId;
      const isHovered = node.id === hoveredId;
      const isRelated = selectedId && this._isRelated(selectedId, node.id);

      // 非关联节点透明度
      if (selectedId && !isSelected && !isRelated) {
        ctx.globalAlpha = 0.2;
      }

      const cx = node.x;
      const cy = node.y;
      const radius = isSelected ? 26 : (isHovered ? 24 : 22);

      // ── 外发光（选中态） ──
      if (isSelected) {
        ctx.beginPath();
        ctx.arc(cx, cy, radius + 6, 0, Math.PI * 2);
        ctx.fillStyle = 'rgba(96, 165, 250, 0.25)';
        ctx.fill();
      }

      // ── 圆形头像 ──
      ctx.beginPath();
      ctx.arc(cx, cy, radius, 0, Math.PI * 2);
      ctx.fillStyle = AVATAR_COLORS[node.colorIdx];
      ctx.fill();

      // 边框
      ctx.strokeStyle = isSelected ? '#60a5fa' : (isHovered ? '#94a3b8' : '#334155');
      ctx.lineWidth = isSelected ? 2.5 : 1.5;
      ctx.stroke();

      // ── 角色名首字母 ──
      const initial = (node.name || '?').charAt(0);
      ctx.fillStyle = '#e2e8f0';
      ctx.font = `bold ${radius * 0.8}px "Segoe UI", "PingFang SC", sans-serif`;
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillText(initial, cx, cy + 1);

      // ── 角色名称标签 ──
      ctx.globalAlpha = 1.0;
      ctx.fillStyle = selectedId && !isSelected && !isRelated ? '#4a5568' : '#cbd5e1';
      ctx.font = '12px "Segoe UI", "PingFang SC", sans-serif';
      ctx.textAlign = 'center';
      ctx.textBaseline = 'top';
      ctx.fillText(node.name, cx, cy + radius + 6);
    }

    ctx.globalAlpha = 1.0;
  }

  /** 判断两节点是否有直接连线 */
  _isRelated(id1, id2) {
    return this._edges.some(e =>
      (e.source === id1 && e.target === id2) ||
      (e.source === id2 && e.target === id1)
    );
  }

  // ═══════════════════════════════════════════════════
  // 工具栏
  // ═══════════════════════════════════════════════════

  _createToolbar() {
    const bar = document.createElement('div');
    bar.className = 'relation-toolbar';

    // ── 搜索框 ──
    const search = document.createElement('input');
    search.className = 'relation-toolbar__search';
    search.type = 'text';
    search.placeholder = '🔍 搜索角色...';
    search.addEventListener('input', (e) => this._onSearch(e.target.value));
    bar.appendChild(search);

    // ── 筛选下拉 ──
    const filter = document.createElement('select');
    filter.className = 'relation-toolbar__filter';
    const filterOptions = [
      { value: 'all', label: '全部关系' },
      { value: '友好', label: '友好' },
      { value: '中立', label: '中立' },
      { value: '敌对', label: '敌对' },
      { value: '爱情', label: '爱情' },
      { value: '血缘', label: '血缘' },
      { value: '师徒', label: '师徒' },
      { value: '同僚', label: '同僚' },
    ];
    filterOptions.forEach(opt => {
      const option = document.createElement('option');
      option.value = opt.value;
      option.textContent = opt.label;
      filter.appendChild(option);
    });
    filter.addEventListener('change', (e) => {
      this._filter = e.target.value;
    });
    bar.appendChild(filter);

    // ── 重置布局 ──
    const resetBtn = document.createElement('button');
    resetBtn.className = 'relation-toolbar__btn';
    resetBtn.textContent = '↺ 重置布局';
    resetBtn.addEventListener('click', () => this._resetLayout());
    bar.appendChild(resetBtn);

    // ── 适应屏幕 ──
    const fitBtn = document.createElement('button');
    fitBtn.className = 'relation-toolbar__btn';
    fitBtn.textContent = '🔲 适应屏幕';
    fitBtn.addEventListener('click', () => this._fitToScreen());
    bar.appendChild(fitBtn);

    // ── 数据统计 ──
    const stats = document.createElement('span');
    stats.className = 'relation-toolbar__stats';
    stats.textContent = `${this._nodes.length} 节点 · ${this._edges.length} 连线`;
    stats.style.cssText = 'margin-left:auto;font-size:11px;color:var(--text-muted);';
    bar.appendChild(stats);

    return bar;
  }

  /** 创建关系图例 */
  _createLegend() {
    const legendItems = [
      { color: '#e8797b', width: '24px', type: 'solid', label: '爱情' },
      { color: '#c084fc', width: '20px', type: 'solid', label: '血缘' },
      { color: '#34d399', width: '20px', type: 'solid', label: '友好/盟友' },
      { color: '#f87171', width: '18px', type: 'dashed', label: '敌对' },
      { color: '#38bdf8', width: '18px', type: 'dashed', label: '师徒' },
      { color: '#fb923c', width: '18px', type: 'dashed', label: '竞争' },
      { color: '#a78bfa', width: '16px', type: 'solid', label: '同僚' },
      { color: '#8892a4', width: '14px', type: 'solid', label: '其他' },
    ];

    const legend = document.createElement('div');
    legend.className = 'relation-legend';

    legendItems.forEach(item => {
      const li = document.createElement('div');
      li.className = 'relation-legend__item';

      const line = document.createElement('div');
      line.className = 'relation-legend__line';
      line.style.cssText = `
        width:${item.width}; background:${item.color};
        ${item.type === 'dashed' ? 'border:1px dashed ' + item.color + '; background:transparent;' : ''}
      `;

      const label = document.createElement('span');
      label.textContent = item.label;

      li.appendChild(line);
      li.appendChild(label);
      legend.appendChild(li);
    });

    return legend;
  }

  /** 搜索角色 */
  _onSearch(query) {
    if (!query.trim()) {
      this._selectedNodeId = null;
      return;
    }

    const q = query.trim().toLowerCase();
    const found = this._nodes.find(n => n.name.toLowerCase().includes(q));
    if (found) {
      this._selectedNodeId = found.id;
      // 居中到选中节点
      if (this._canvas && this._canvasWidth) {
        this._viewX = this._canvasWidth / 2 / this._zoom - found.x;
        this._viewY = (this._canvasHeight || 400) / 2 / this._zoom - found.y;
      }
    }
  }

  /** 重置布局 */
  _resetLayout() {
    if (this._layout) {
      this._layout.reset(this._canvasWidth || 600, this._canvasHeight || 400);
    }
    this._zoom = 1.0;
    this._viewX = 0;
    this._viewY = 0;
    this._selectedNodeId = null;
  }

  /** 适应屏幕 */
  _fitToScreen() {
    if (this._nodes.length === 0) return;

    let minX = Infinity, minY = Infinity;
    let maxX = -Infinity, maxY = -Infinity;

    this._nodes.forEach(n => {
      if (n.x < minX) minX = n.x;
      if (n.y < minY) minY = n.y;
      if (n.x > maxX) maxX = n.x;
      if (n.y > maxY) maxY = n.y;
    });

    const padding = 60;
    const nodeW = maxX - minX + padding * 2;
    const nodeH = maxY - minY + padding * 2;
    const cw = this._canvasWidth || 600;
    const ch = this._canvasHeight || 400;

    const scaleX = cw / nodeW;
    const scaleY = ch / nodeH;
    this._zoom = Math.min(scaleX, scaleY, 2.0);
    this._viewX = (cw - (minX + maxX) / 2 * this._zoom * 2) / 2;
    this._viewY = (ch - (minY + maxY) / 2 * this._zoom * 2) / 2;
  }

  // ═══════════════════════════════════════════════════
  // Canvas 事件绑定
  // ═══════════════════════════════════════════════════

  _bindCanvasEvents() {
    if (!this._canvas) return;

    const canvas = this._canvas;

    // ── 鼠标按下 ──
    canvas.addEventListener('mousedown', (e) => {
      const pos = this._getCanvasPos(e);
      const node = this._hitTestNode(pos.x, pos.y);

      if (node) {
        // 拖拽节点
        this._dragNode = node;
        this._dragOffsetX = pos.x - node.x;
        this._dragOffsetY = pos.y - node.y;
        this._isDragging = false;
        this._selectedNodeId = node.id;
        if (this._layout) this._layout.alpha = Math.max(this._layout.alpha, 0.3);
      } else {
        // 画布平移
        this._panning = true;
        this._panStartX = e.clientX;
        this._panStartY = e.clientY;
        this._panViewStartX = this._viewX;
        this._panViewStartY = this._viewY;
        this._selectedNodeId = null;
        this._hideTooltip();
      }
    });

    // ── 鼠标移动 ──
    canvas.addEventListener('mousemove', (e) => {
      const pos = this._getCanvasPos(e);

      if (this._dragNode) {
        // 拖拽中
        this._isDragging = true;
        this._dragNode.x = pos.x - this._dragOffsetX;
        this._dragNode.y = pos.y - this._dragOffsetY;
        if (this._layout) this._layout.alpha = Math.max(this._layout.alpha, 0.3);
        return;
      }

      if (this._panning) {
        // 画布平移
        const dx = e.clientX - this._panStartX;
        const dy = e.clientY - this._panStartY;
        this._viewX = this._panViewStartX + dx;
        this._viewY = this._panViewStartY + dy;
        return;
      }

      // ── 悬停检测 ──
      const node = this._hitTestNode(pos.x, pos.y);
      const edge = node ? null : this._hitTestEdge(pos.x, pos.y);

      if (node) {
        this._hoveredNodeId = node.id;
        this._hoveredEdge = null;
        canvas.style.cursor = 'pointer';
        this._showTooltip(node, null, pos);
      } else if (edge) {
        this._hoveredEdge = edge;
        this._hoveredNodeId = null;
        canvas.style.cursor = 'pointer';
        this._showTooltip(null, edge, pos);
      } else {
        this._hoveredNodeId = null;
        this._hoveredEdge = null;
        canvas.style.cursor = 'grab';
        this._hideTooltip();
      }
    });

    // ── 鼠标释放 ──
    canvas.addEventListener('mouseup', () => {
      if (this._dragNode && !this._isDragging) {
        // 点击（非拖拽）
        this._selectedNodeId = this._dragNode.id;
      }
      this._dragNode = null;
      this._isDragging = false;
      this._panning = false;
    });

    // ── 鼠标离开 ──
    canvas.addEventListener('mouseleave', () => {
      this._dragNode = null;
      this._isDragging = false;
      this._panning = false;
      this._hoveredNodeId = null;
      this._hoveredEdge = null;
      this._hideTooltip();
    });

    // ── 双击 ──
    canvas.addEventListener('dblclick', (e) => {
      const pos = this._getCanvasPos(e);
      const node = this._hitTestNode(pos.x, pos.y);
      if (node) {
        // 打开角色编辑模态框
        this._openCharacterModal(node.id);
      }
    });

    // ── 滚轮缩放 ──
    canvas.addEventListener('wheel', (e) => {
      e.preventDefault();
      const delta = e.deltaY > 0 ? 0.9 : 1.1;
      const newZoom = Math.max(0.3, Math.min(3.0, this._zoom * delta));

      // 以鼠标位置为中心缩放
      const rect = canvas.getBoundingClientRect();
      const mx = e.clientX - rect.left;
      const my = e.clientY - rect.top;

      const worldX = (mx - this._viewX) / this._zoom;
      const worldY = (my - this._viewY) / this._zoom;

      this._zoom = newZoom;
      this._viewX = mx - worldX * this._zoom;
      this._viewY = my - worldY * this._zoom;
    }, { passive: false });
  }

  /** 将鼠标事件坐标转换为世界坐标（考虑视图变换） */
  _getCanvasPos(e) {
    const rect = this._canvas.getBoundingClientRect();
    const mx = e.clientX - rect.left;
    const my = e.clientY - rect.top;
    return {
      x: (mx - this._viewX) / this._zoom,
      y: (my - this._viewY) / this._zoom,
    };
  }

  /** 命中检测（节点） */
  _hitTestNode(wx, wy) {
    const radius = 28; // 点击判定半径（略大于绘制半径）
    let closest = null;
    let closestDist = Infinity;

    for (const node of this._nodes) {
      const dx = wx - node.x;
      const dy = wy - node.y;
      const dist = Math.sqrt(dx * dx + dy * dy);
      if (dist < radius && dist < closestDist) {
        closest = node;
        closestDist = dist;
      }
    }

    return closest;
  }

  /** 命中检测（连线） */
  _hitTestEdge(wx, wy) {
    let closest = null;
    let closestDist = 8; // 阈值

    for (const edge of this._edges) {
      const source = this._nodes.find(n => n.id === edge.source);
      const target = this._nodes.find(n => n.id === edge.target);
      if (!source || !target) continue;

      const dist = this._pointToLineDist(wx, wy, source.x, source.y, target.x, target.y);
      if (dist < closestDist) {
        closest = edge;
        closestDist = dist;
      }
    }

    return closest;
  }

  /** 点到线段距离 */
  _pointToLineDist(px, py, x1, y1, x2, y2) {
    const A = px - x1;
    const B = py - y1;
    const C = x2 - x1;
    const D = y2 - y1;
    const dot = A * C + B * D;
    const lenSq = C * C + D * D;
    let t = lenSq !== 0 ? dot / lenSq : -1;
    t = Math.max(0, Math.min(1, t));
    const projX = x1 + t * C;
    const projY = y1 + t * D;
    const dx = px - projX;
    const dy = py - projY;
    return Math.sqrt(dx * dx + dy * dy);
  }

  // ═══════════════════════════════════════════════════
  // 工具提示
  // ═══════════════════════════════════════════════════

  _showTooltip(node, edge, pos) {
    if (!this._tooltip) return;

    if (node) {
      // 鼠标位置的世界坐标 → 屏幕坐标
      const sx = node.x * this._zoom + this._viewX;
      const sy = node.y * this._zoom + this._viewY;

      const role = node.role ? `身份: ${node.role}` : '';
      const relationCount = this._edges.filter(
        e => e.source === node.id || e.target === node.id
      ).length;

      this._tooltip.innerHTML = `
        <div class="relation-tooltip__name">${this._esc(node.name)}</div>
        ${role ? `<div class="relation-tooltip__detail">${this._esc(role)}</div>` : ''}
        <div class="relation-tooltip__detail">关联: ${relationCount} 条关系</div>
      `;
      this._tooltip.className = 'relation-tooltip relation-tooltip--visible';

      // 定位（避免溢出屏幕）
      const rect = this._canvas.getBoundingClientRect();
      let tx = sx + 20;
      let ty = sy - 30;
      if (tx + 160 > rect.width) tx = sx - 170;
      if (ty < 10) ty = sy + 20;
      this._tooltip.style.left = tx + 'px';
      this._tooltip.style.top = ty + 'px';
      return;
    }

    if (edge) {
      const source = this._nodes.find(n => n.id === edge.source);
      const target = this._nodes.find(n => n.id === edge.target);
      if (!source || !target) return;

      const style = _getEdgeStyle(edge.type);
      const sx = pos.x * this._zoom + this._viewX;
      const sy = pos.y * this._zoom + this._viewY;

      this._tooltip.innerHTML = `
        <div class="relation-tooltip__name">${this._esc(source.name)} ↔ ${this._esc(target.name)}</div>
        <div class="relation-tooltip__detail">关系: ${this._esc(edge.type || '未知')}</div>
        <div class="relation-tooltip__detail">紧密程度: ${Math.round((edge.bond_strength || 0) * 100)}%</div>
      `;
      this._tooltip.className = 'relation-tooltip relation-tooltip--visible';

      let tx = sx + 15;
      let ty = sy - 20;
      const rect = this._canvas.getBoundingClientRect();
      if (tx + 160 > rect.width) tx = sx - 175;
      if (ty < 10) ty = sy + 15;
      this._tooltip.style.left = tx + 'px';
      this._tooltip.style.top = ty + 'px';
    }
  }

  _hideTooltip() {
    if (this._tooltip) {
      this._tooltip.className = 'relation-tooltip';
    }
  }

  /** 打开角色编辑模态框 */
  _openCharacterModal(charId) {
    // 触发 characters.js 的编辑模态框
    App.emit('relation_network_open_char', { charId });
  }

  _esc(str) {
    if (!str) return '';
    const div = document.createElement('div');
    div.textContent = String(str);
    return div.innerHTML;
  }
}
