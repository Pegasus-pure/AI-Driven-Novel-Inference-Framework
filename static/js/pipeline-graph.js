const NODE_W = 140;
const NODE_H = 90;
const WIRE_COLOR = '#6e7681';
const WIRE_ACTIVE = '#58a6ff';
const WIRE_WIDTH = 2;
const SNAP_GRID = 20;

// ════════════════════════════════════════════
// 节点数据（从后端动态获取 label/desc/icon）
// ════════════════════════════════════════════
export let PIPELINE_NODES = [
  { id:'context',     x:2500, y:2200, tier:'python',  agent:'ContextBuilder',    label:'', desc:'', icon:'⚡' },
  { id:'director',    x:2500, y:2330, tier:'strong',  agent:'SceneDirector',      label:'', desc:'', icon:'🎬' },
  { id:'continuity',  x:2500, y:2480, tier:'medium',  agent:'ContinuityChecker',  label:'', desc:'', icon:'🔗' },
  { id:'motivation',  x:2750, y:2480, tier:'medium',  agent:'MotivationEngine',   label:'', desc:'', icon:'💡' },
  { id:'dialogue',    x:2750, y:2630, tier:'light',   agent:'DialogueWeaver',     label:'', desc:'', icon:'💬' },
  { id:'reflection',  x:2750, y:2780, tier:'light',   agent:'RoleReflector',     label:'', desc:'', icon:'🤔' },
  { id:'composer',    x:2500, y:2780, tier:'strong',  agent:'SceneComposer',     label:'', desc:'', icon:'🎨' },
  { id:'auditor',     x:2500, y:2930, tier:'medium',  agent:'ConsistencyAuditor', label:'', desc:'', icon:'🔍' },
  { id:'state',       x:2500, y:3080, tier:'light',   agent:'StateExtractor',    label:'', desc:'', icon:'📊' },
  { id:'micro_oracle',x:2750, y:3080, tier:'light',   agent:'MicroOracle',       label:'', desc:'', icon:'🔮' },
  { id:'character_mgr',    x:3000, y:3080, tier:'light',   agent:'CharacterManager',  label:'', desc:'', icon:'👥' },
  { id:'location_mgr',     x:3250, y:3080, tier:'light',   agent:'LocationManager',   label:'', desc:'', icon:'🗺️' },
  { id:'thread_mgr',  x:2750, y:3230, tier:'medium',  agent:'ThreadManager',     label:'', desc:'', icon:'🧵' },
  { id:'apply_state', x:2750, y:3380, tier:'python',  agent:'Python',            label:'', desc:'', icon:'🐍' },
  { id:'oracle',      x:2750, y:3530, tier:'strong',  agent:'ReflectionOracle',  label:'', desc:'', icon:'🔯' },
];

// 连接关系
const PIPELINE_EDGES = [
  { from:'context',     to:'director' },
  { from:'director',    to:'continuity' },
  { from:'director',    to:'motivation' },
  { from:'continuity',  to:'motivation' },
  { from:'motivation',  to:'dialogue' },
  { from:'dialogue',    to:'reflection' },
  { from:'reflection',  to:'composer' },
  { from:'composer',    to:'auditor' },
  { from:'auditor',     to:'state' },
  { from:'auditor',     to:'micro_oracle' },
  { from:'auditor',     to:'character_mgr' },
  { from:'auditor',     to:'location_mgr' },
  { from:'state',       to:'thread_mgr' },
  { from:'micro_oracle',to:'thread_mgr' },
  { from:'character_mgr',    to:'thread_mgr' },
  { from:'location_mgr',     to:'thread_mgr' },
  { from:'thread_mgr',   to:'apply_state' },
  { from:'apply_state',  to:'oracle' },
];

// 节点 ↔ 功能开关映射（oracle 无开关，由拍数触发）
const NODE_FEATURE_MAP = {
  continuity:   'continuity_check',
  reflection:   'role_reflection',
  micro_oracle: 'micro_oracle',
  character_mgr:     'emergence_system',
  location_mgr:      'emergence_system',
};

// 布局配置（竖排/横排）
const LAYOUTS = {
  vertical: [
    { id:'context',     x:2500, y:2200 },
    { id:'director',    x:2500, y:2330 },
    { id:'continuity',  x:2500, y:2480 },
    { id:'motivation',  x:2750, y:2480 },
    { id:'dialogue',    x:2750, y:2630 },
    { id:'reflection',  x:2750, y:2780 },
    { id:'composer',    x:2500, y:2780 },
    { id:'auditor',     x:2500, y:2930 },
    { id:'state',       x:2500, y:3080 },
    { id:'micro_oracle',x:2750, y:3080 },
    { id:'character_mgr',    x:3000, y:3080 },
    { id:'location_mgr',     x:3250, y:3080 },
    { id:'thread_mgr',  x:2750, y:3230 },
    { id:'apply_state', x:2750, y:3380 },
    { id:'oracle',      x:2750, y:3530 },
  ],
  horizontal: [
    { id:'context',     x:2200, y:2500 },
    { id:'director',    x:2370, y:2500 },
    { id:'continuity',  x:2540, y:2350 },
    { id:'motivation',  x:2540, y:2650 },
    { id:'dialogue',    x:2710, y:2650 },
    { id:'reflection',  x:2880, y:2650 },
    { id:'composer',    x:2710, y:2500 },
    { id:'auditor',     x:2880, y:2500 },
    { id:'state',       x:3050, y:2500 },
    { id:'micro_oracle',x:3050, y:2350 },
    { id:'character_mgr',    x:3220, y:2350 },
    { id:'location_mgr',     x:3390, y:2350 },
    { id:'thread_mgr',  x:3220, y:2500 },
    { id:'apply_state', x:3390, y:2500 },
    { id:'oracle',      x:3560, y:2500 },
  ]
};

// ════════════════════════════════════════════
// PipelineGraph 类
// ════════════════════════════════════════════

export class PipelineGraph {
  constructor() {
    this._zoomLevel  = 1;
    this._isHorizontal = false;
    this._snap = true;
    this._drag = null;    // 节点拖拽状态
    this._pan = null;     // 画布平移状态（左键拖拽空白区域）
    this._disabled  = new Set();
    this._features  = {}; // 功能开关状态缓存

    this._init();
  }

  // ── 初始化 ─────────────────────────────────────
  async _init() {
    this._loadDirection();
    await Promise.all([this._loadMeta(), this._loadFeatures()]);
    this._loadLayout();
    this._applyZoom();   // 初始化缩放变换
    this._renderNodes();
    this._drawWires();
    this._bindPan();      // 左键拖拽平移
    this._bindZoom();     // Ctrl+滚轮缩放
    this._bindNodes();
    this._bindToolbar();
    this._updateLayoutButton();  // 初始化按钮文字
    this._centerView();
  }

  show() {
    // 页面显示时重新居中
    requestAnimationFrame(() => this._centerView());
  }

  // ── 加载元数据 ─────────────────────────────────
  async _loadMeta() {
    try {
      const resp = await fetch('/api/pipeline/nodes-meta');
      const data = await resp.json();
      if (data.success) {
        PIPELINE_NODES.forEach(node => {
          const meta = data.meta[node.id];
          if (meta) {
            node.label = meta.label || node.id;
            node.desc  = meta.desc  || '';
            node.icon  = meta.icon  || node.icon;
          }
        });
      }
    } catch (err) {
      console.error('[PipelineGraph] 加载元数据失败:', err);
    }
  }

  // ── 加载功能开关状态 ─────────────────────────
  async _loadFeatures() {
    try {
      const resp = await fetch('/api/config/features');
      const data = await resp.json();
      if (data.success) {
        this._features = data.features || {};
      }
    } catch (err) {
      console.error('[PipelineGraph] 加载功能开关失败:', err);
      this._features = {};
    }
  }

  // ── 加载布局（按排版方向分别存储）───────────
  _loadLayout() {
    const key = this._isHorizontal ? 'rain_pg_layout_horizontal' : 'rain_pg_layout_vertical';
    try {
      const saved = localStorage.getItem(key);
      if (saved) {
        const layout = JSON.parse(saved);
        PIPELINE_NODES.forEach(node => {
          if (layout[node.id]) {
            node.x = layout[node.id].x;
            node.y = layout[node.id].y;
          }
        });
        return;
      }
    } catch (e) {
      console.warn('[PipelineGraph] 读取布局失败:', e);
    }

    // 无保存数据 → 使用该方向的预设布局
    const preset = LAYOUTS[this._isHorizontal ? 'horizontal' : 'vertical'];
    preset.forEach(pos => {
      const node = PIPELINE_NODES.find(n => n.id === pos.id);
      if (node) { node.x = pos.x; node.y = pos.y; }
    });
  }

  _saveLayout() {
    const layout = {};
    PIPELINE_NODES.forEach(n => { layout[n.id] = { x: n.x, y: n.y }; });
    const key = this._isHorizontal ? 'rain_pg_layout_horizontal' : 'rain_pg_layout_vertical';
    localStorage.setItem(key, JSON.stringify(layout));
  }

  // ── 排版方向持久化 ───────────────────────────
  _loadDirection() {
    try {
      const saved = localStorage.getItem('rain_pg_direction');
      if (saved) {
        this._isHorizontal = saved === 'horizontal';
        return;
      }
    } catch (e) { /* ignore */ }

    // 迁移：从旧的 rain_pg_layout 推断排版方向
    // context 节点 x=2500（竖排）vs x=2200（横排）
    try {
      const oldLayout = localStorage.getItem('rain_pg_layout');
      if (oldLayout) {
        const layout = JSON.parse(oldLayout);
        if (layout.context) {
          this._isHorizontal = layout.context.x < 2300;
          // 迁移到新的分方向存储
          const key = this._isHorizontal ? 'rain_pg_layout_horizontal' : 'rain_pg_layout_vertical';
          localStorage.setItem(key, oldLayout);
          localStorage.removeItem('rain_pg_layout');
          this._saveDirection();
          return;
        }
      }
    } catch (e) { /* ignore */ }

    this._isHorizontal = false;
  }

  _saveDirection() {
    localStorage.setItem('rain_pg_direction', this._isHorizontal ? 'horizontal' : 'vertical');
  }

  _updateLayoutButton() {
    const btn = document.getElementById('pgBtnLayout');
    if (btn) {
      btn.textContent = this._isHorizontal ? '⇅ 竖排' : '⇄ 横排';
    }
  }

  // ── 应用缩放变换到 .pg-zoom-wrapper ────────
  _applyZoom() {
    const wrapper = document.getElementById('pipelineGraphZoom');
    if (!wrapper) return;
    wrapper.style.transform = `scale(${this._zoomLevel})`;
    // 同步 CSS 变量（供 CSS 使用）
    wrapper.style.setProperty('--pg-zoom', this._zoomLevel);

    const zoomDisplay = document.getElementById('pgZoomLevel');
    if (zoomDisplay) {
      zoomDisplay.textContent = `${Math.round(this._zoomLevel * 100)}%`;
    }
  }

  // ── 渲染节点 ───────────────────────────────────
  _renderNodes() {
    const container = document.getElementById('pipelineGraphNodes');
    if (!container) return;
    container.innerHTML = '';

    PIPELINE_NODES.forEach(node => {
      const el = document.createElement('div');
      el.className = `pg-node tier-${node.tier} ${this._disabled.has(node.id) ? 'pg-node--disabled' : ''}`;
      el.id = `pg-node-${node.id}`;
      el.style.left = `${node.x - NODE_W / 2}px`;
      el.style.top  = `${node.y - NODE_H / 2}px`;
      el.dataset.nodeId = node.id;

      // 动态徽章：根据功能开关状态显示 已激活 / 未激活 / 条件触发
      let badgeHtml = '';
      const featureKey = NODE_FEATURE_MAP[node.id];
      if (featureKey) {
        const isActive = this._features[featureKey] === true;
        const cssClass = isActive ? 'pg-opt-badge--active' : 'pg-opt-badge--inactive';
        badgeHtml = `<span class="pg-opt-badge ${cssClass}">${isActive ? '已激活' : '未激活'}</span>`;
      } else if (node.id === 'oracle') {
        badgeHtml = '<span class="pg-opt-badge pg-opt-badge--conditional">条件触发</span>';
      }

      el.innerHTML = `
        <div class="pg-node__icon">${node.icon}</div>
        <div class="pg-node__body">
          <div class="pg-node__label">${node.label}</div>
          <div class="pg-node__desc">${node.desc}</div>
        </div>
        ${badgeHtml}
      `;

      container.appendChild(el);
    });
  }

  // ── 绘制连线 ───────────────────────────────────
  _drawWires() {
    const g = document.getElementById('pg-wires-group');
    if (!g) return;

    let paths = '';

    PIPELINE_EDGES.forEach(edge => {
      const fromNode = PIPELINE_NODES.find(n => n.id === edge.from);
      const toNode   = PIPELINE_NODES.find(n => n.id === edge.to);
      if (!fromNode || !toNode) return;

      // 用节点中心坐标连接（无端口设计）
      const x1 = fromNode.x;
      const y1 = fromNode.y;
      const x2 = toNode.x;
      const y2 = toNode.y;

      // 贝塞尔曲线
      const mx = (x1 + x2) / 2;
      const my = (y1 + y2) / 2;

      const dx = Math.abs(x2 - x1);
      const dy = Math.abs(y2 - y1);

      let d;
      if (dx > dy) {
        d = `M ${x1} ${y1} C ${mx} ${y1}, ${mx} ${y2}, ${x2} ${y2}`;
      } else {
        d = `M ${x1} ${y1} C ${x1} ${my}, ${x2} ${my}, ${x2} ${y2}`;
      }

      const isDisabled = this._disabled.has(fromNode.id) || this._disabled.has(toNode.id);
      const color = isDisabled ? WIRE_COLOR : WIRE_ACTIVE;
      const width = isDisabled ? WIRE_WIDTH : WIRE_WIDTH + 1;

      const tierToArrow = { strong: 'pg-arrow-strong', medium: 'pg-arrow-medium', light: 'pg-arrow-light', python: 'pg-arrow-python' };
      const marker = tierToArrow[fromNode.tier] || 'pg-arrow-python';

      paths += `<path d="${d}" stroke="${color}" stroke-width="${width}" fill="none"
                   stroke-linecap="round"
                   marker-end="url(#${marker})"
                   class="${isDisabled ? '' : 'pg-wire--active'}" />`;
    });

    g.innerHTML = paths;
  }

  // ── 绑定节点拖拽 ───────────────────────────────
  _bindNodes() {
    const container = document.getElementById('pipelineGraphNodes');
    if (!container) return;

    container.addEventListener('mousedown', (e) => {
      const nodeEl = e.target.closest('.pg-node');
      if (!nodeEl) return;

      e.stopPropagation();
      const nodeId = nodeEl.dataset.nodeId;
      const node = PIPELINE_NODES.find(n => n.id === nodeId);
      if (!node) return;

      this._drag = {
        nodeId,
        startX: e.clientX,
        startY: e.clientY,
        origX: node.x,
        origY: node.y,
      };
    });

    document.addEventListener('mousemove', (e) => {
      if (!this._drag) return;

      const dx = e.clientX - this._drag.startX;
      const dy = e.clientY - this._drag.startY;

      const node = PIPELINE_NODES.find(n => n.id === this._drag.nodeId);
      if (!node) return;

      let newX = this._drag.origX + dx / this._zoomLevel;
      let newY = this._drag.origY + dy / this._zoomLevel;

      if (this._snap) {
        newX = Math.round(newX / SNAP_GRID) * SNAP_GRID;
        newY = Math.round(newY / SNAP_GRID) * SNAP_GRID;
      }

      node.x = newX;
      node.y = newY;

      const nodeEl = document.getElementById(`pg-node-${node.id}`);
      if (nodeEl) {
        nodeEl.style.left = `${node.x - NODE_W / 2}px`;
        nodeEl.style.top  = `${node.y - NODE_H / 2}px`;
      }

      this._drawWires();
    });

    document.addEventListener('mouseup', () => {
      if (this._drag) {
        this._saveLayout();
        this._drag = null;
      }
    });
  }

  // ── 绑定画布平移（鼠标左键拖拽空白区域）──
  _bindPan() {
    const scrollEl = document.getElementById('pipelineGraphScroll');
    if (!scrollEl) return;

    scrollEl.addEventListener('mousedown', (e) => {
      // 点击在节点上时不触发平移
      if (e.target.closest('.pg-node')) return;
      // 只响应左键
      if (e.button !== 0) return;

      this._pan = {
        startX: e.clientX,
        startY: e.clientY,
        origScrollX: scrollEl.scrollLeft,
        origScrollY: scrollEl.scrollTop,
      };
      scrollEl.style.cursor = 'grabbing';
    });

    document.addEventListener('mousemove', (e) => {
      if (!this._pan) return;
      const dx = e.clientX - this._pan.startX;
      const dy = e.clientY - this._pan.startY;
      scrollEl.scrollLeft = this._pan.origScrollX - dx;
      scrollEl.scrollTop  = this._pan.origScrollY - dy;
    });

    document.addEventListener('mouseup', () => {
      if (this._pan) {
        scrollEl.style.cursor = 'grab';
        this._pan = null;
      }
    });
  }

  // ── 绑定缩放（Ctrl+滚轮）────────────────────
  _bindZoom() {
    const scrollEl = document.getElementById('pipelineGraphScroll');
    if (!scrollEl) return;

    scrollEl.addEventListener('wheel', (e) => {
      // 只有 Ctrl 键按下时才缩放，否则让滚轮正常滚动
      if (!e.ctrlKey) return;

      e.preventDefault();

      const delta = e.deltaY > 0 ? -0.1 : 0.1;
      const newZoom = Math.min(2.5, Math.max(0.5, this._zoomLevel + delta));

      // 以鼠标位置为缩放中心
      const rect = scrollEl.getBoundingClientRect();
      const mouseX = e.clientX - rect.left;
      const mouseY = e.clientY - rect.top;

      const canvasX = (scrollEl.scrollLeft + mouseX) / this._zoomLevel;
      const canvasY = (scrollEl.scrollTop  + mouseY) / this._zoomLevel;

      this._zoomLevel = newZoom;
      this._applyZoom();

      // 调整滚动位置，使鼠标指向的画面位置保持不变
      scrollEl.scrollLeft = Math.max(0, canvasX * newZoom - mouseX);
      scrollEl.scrollTop  = Math.max(0, canvasY * newZoom - mouseY);

      this._drawWires();
    }, { passive: false });
  }

  // ── 居中视图（滚动到第一个节点）──────────
  _centerView() {
    const scrollEl = document.getElementById('pipelineGraphScroll');
    if (!scrollEl) return;

    const firstNodeData = PIPELINE_NODES[0];
    if (!firstNodeData) return;

    requestAnimationFrame(() => {
      const scale = this._zoomLevel || 1;

      // 第一个节点的像素位置（考虑缩放）
      const nodePixelX = firstNodeData.x * scale;
      const nodePixelY = firstNodeData.y * scale;

      // 让节点出现在视口左侧约 35%、上方约 30% 的位置
      const padX = Math.min(scrollEl.clientWidth * 0.35, 220);
      const padY = Math.min(scrollEl.clientHeight * 0.3, 160);

      scrollEl.scrollLeft = Math.max(0, nodePixelX - padX);
      scrollEl.scrollTop  = Math.max(0, nodePixelY - padY);
    });
  }

  // ── 绑定工具栏 ─────────────────────────────────
  _bindToolbar() {
    const btnLayout = document.getElementById('pgBtnLayout');
    if (btnLayout) {
      btnLayout.addEventListener('click', () => {
        // 1. 保存当前方向的布局
        this._saveLayout();

        // 2. 切换方向
        this._isHorizontal = !this._isHorizontal;
        btnLayout.textContent = this._isHorizontal ? '⇅ 竖排' : '⇄ 横排';
        this._saveDirection();

        // 3. 加载新方向的布局（已保存的或默认）
        this._loadLayout();

        this._renderNodes();
        this._drawWires();
        this._centerView();
      });
    }

    const btnReset = document.getElementById('pgBtnReset');
    if (btnReset) {
      btnReset.addEventListener('click', () => {
        localStorage.removeItem('rain_pg_layout_vertical');
        localStorage.removeItem('rain_pg_layout_horizontal');
        localStorage.removeItem('rain_pg_direction');
        const layout = LAYOUTS[this._isHorizontal ? 'horizontal' : 'vertical'];
        layout.forEach(pos => {
          const node = PIPELINE_NODES.find(n => n.id === pos.id);
          if (node) {
            node.x = pos.x;
            node.y = pos.y;
          }
        });
        this._renderNodes();
        this._drawWires();
        this._centerView();
      });
    }

    const btnSnap = document.getElementById('pgBtnSnap');
    if (btnSnap) {
      btnSnap.addEventListener('click', () => {
        this._snap = !this._snap;
        btnSnap.classList.toggle('pipeline-graph__toolbar-btn--active', this._snap);
      });
    }
  }

  // ── 公开方法 ─────────────────────────────────────

  /** 更新单个功能开关状态并刷新对应节点徽章 */
  updateFeatureState(featureKey, value) {
    this._features[featureKey] = value;
    this._renderNodes();
  }

  /** 从后端重新拉取所有功能开关状态并刷新徽章 */
  async refreshFeatureStates() {
    await this._loadFeatures();
    this._renderNodes();
  }
}
