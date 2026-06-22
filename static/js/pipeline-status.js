/**
 * pipeline-status.js — Agent 流水线状态条 + 选项区状态显示
 *
 * 三重视觉反馈:
 *   (A) 顶部 #pipelineBar — 全流程 dot 进度 + 标签（始终显示）
 *   (B) 选项区上方 #pipelineBubbles — 胶囊气泡堆叠，最多 3 个
 *       新气泡从底部推入，满 3 时顶部最旧气泡向上滑出
 *   (C) 选项区上方 #pipelineStatusLabel — 单行文字 (fallback 模式)
 *
 * 显示模式通过 App.state.statusDisplayMode 切换:
 *   'bubbles' → (B) 气泡模式
 *   'label'   → (C) 单行模式
 * 默认为气泡模式，可在 F7 设置面板中切换。
 *
 * agent name 列表与 pipeline.py 中 progress_cb 的 key 保持一致。
 * 阶段标签从后端 API (/api/pipeline/nodes-meta) 动态获取。
 */

import { App } from './app.js';

export class PipelineStatusBar {
  constructor() {
    /** @type {HTMLElement} */
    this._bar = null;
    /** @type {HTMLElement} */
    this._nodes = null;
    /** @type {HTMLElement} */
    this._label = null;
    /** @type {HTMLElement} */
    this._progress = null;

    // ── 气泡区 ──
    /** @type {HTMLElement} */
    this._bubbleContainer = null;
    /** @type {Array<{agent:string, label:string, el:HTMLElement}>} */
    this._bubbles = [];

    // ── 单行标签 ──
    /** @type {HTMLElement} */
    this._statusLabel = null;
    /** @type {HTMLElement} */
    this._statusText = null;

    /** @type {number} 气泡最大同时可见数 */
    this._MAX_BUBBLES = 3;

    // ── 流水线层级定义（从后端 API 加载） ──
    /** @type {Array<{agent:string, label:string, emoji:string}>} */
    this._stages = [];

    /** @type {number} 当前活跃层级索引 (-1 = 无) */
    this._activeIndex = -1;
    /** @type {boolean} */
    this._visible = false;
    /** @type {number|null} 隐藏超时 */
    this._hideTimeout = null;
  }

  async init() {
    // ── 顶部流水线条 ──
    this._bar = document.getElementById('pipelineBar');
    this._nodes = document.getElementById('pipelineNodes');
    this._label = document.getElementById('pipelineLabel');
    this._progress = document.getElementById('pipelineProgress');

    // ── 气泡容器 ──
    this._bubbleContainer = document.getElementById('pipelineBubbles');

    // ── 单行状态标签 ──
    this._statusLabel = document.getElementById('pipelineStatusLabel');
    if (this._statusLabel) {
      this._statusText = this._statusLabel.querySelector('.pipeline-status__text');
      // 兼容旧类名（CSS 中可能用了 pipeline-status-label__text）
      if (!this._statusText) {
        this._statusText = this._statusLabel.querySelector('.pipeline-status-label__text');
      }
    }

    // ── 从后端加载阶段定义 ──
    await this._loadStages();

    // ── 渲染流水线节点 ──
    this._renderStages();

    // ── 初始化显示模式切换 ──
    this._initDisplayToggle();

    // ── 恢复上次的显示模式 ──
    const savedMode = (localStorage.getItem('rain_statusDisplayMode') || 'bubbles').replace(/['"]/g, '');
    App.state.statusDisplayMode = savedMode;
    this._applyDisplayMode(savedMode);
  }

  async _loadStages() {
    try {
      const resp = await fetch('/api/pipeline/nodes-meta');
      const data = await resp.json();
      if (!data.success) {
        console.error('[PipelineStatusBar] 加载阶段定义失败:', data.message);
        return;
      }

      // 节点 ID → pipeline.py progress_cb key 映射
      // 只收录有 progress_cb 的节点；无 progress_cb 的节点（如 state/micro_oracle 等并行静默执行）不显示在进度条中
      const AGENT_KEY_MAP = {
        context:      'context_builder',
        director:     'scene_director',
        continuity:   'continuity_checker',
        motivation:   'motivation',
        dialogue:     'dialogue',
        reflection:   'role_reflector',
        composer:     'composer',
        auditor:      'auditor',
        thread_mgr:   'thread_manager',
        oracle:       'oracle',
      };

      const meta = data.meta;
      this._stages = Object.entries(AGENT_KEY_MAP)
        .filter(([id]) => meta[id])  // 确保元数据存在
        .map(([id, agentKey]) => ({
          agent: agentKey,
          label: meta[id].label,
          emoji: meta[id].emoji || meta[id].icon || '',
        }));

      console.log('[PipelineStatusBar] 已加载', this._stages.length, '个阶段');
    } catch (err) {
      console.error('[PipelineStatusBar] 加载阶段定义失败:', err);
    }
  }

  _renderStages() {
    if (!this._nodes) return;

    this._nodes.innerHTML = '';

    this._stages.forEach((stage, idx) => {
      const dot = document.createElement('div');
      dot.className = 'pipeline-bar__dot pipeline-bar__dot--pending';

      const label = document.createElement('span');
      label.className = 'pipeline-bar__node-tooltip';
      label.textContent = stage.emoji + ' ' + stage.label;

      const node = document.createElement('div');
      node.className = 'pipeline-bar__node pipeline-bar__node--pending';
      node.dataset.index = idx;
      node.dataset.agent = stage.agent;
      node.appendChild(dot);
      node.appendChild(label);

      this._nodes.appendChild(node);
    });
  }

  // ── 公开方法 ─────────────────────────────────────────

  /**
   * 激活某个阶段
   * @param {string} agentName - Agent 名称（与 progress_cb 的 key 一致）
   */
  activate(agentName) {
    const idx = this._stages.findIndex(s => s.agent === agentName);
    if (idx === -1) return;

    this._activeIndex = idx;
    this._visible = true;

    // 更新 UI
    this._updateUI();
  }

  /**
   * 前进到下一个阶段
   */
  advance() {
    if (this._activeIndex < this._stages.length - 1) {
      this._activeIndex++;
      this._updateUI();
    }
  }

  /**
   * 隐藏状态条并清除所有状态
   */
  hide() {
    this._visible = false;
    this._activeIndex = -1;

    // 隐藏顶部状态条
    if (this._bar) {
      this._bar.classList.remove('pipeline-bar--active');
    }

    // 重置所有节点状态为 pending
    if (this._nodes) {
      const nodeEls = this._nodes.querySelectorAll('.pipeline-bar__node');
      nodeEls.forEach(el => {
        el.classList.remove('pipeline-bar__node--done', 'pipeline-bar__node--active', 'pipeline-bar__node--pending');
        el.classList.add('pipeline-bar__node--pending');
        const dot = el.querySelector('.pipeline-bar__dot');
        if (dot) {
          dot.classList.remove('pipeline-bar__dot--done', 'pipeline-bar__dot--active', 'pipeline-bar__dot--pending');
          dot.classList.add('pipeline-bar__dot--pending');
        }
      });
    }

    // 清除气泡
    this._bubbles = [];
    if (this._bubbleContainer) {
      this._bubbleContainer.innerHTML = '';
    }

    // 清除单行标签
    if (this._statusText) {
      this._statusText.textContent = '';
    }
    if (this._statusLabel) {
      // 根据当前显示模式决定是否隐藏
      const mode = App.state.statusDisplayMode || 'bubbles';
      this._statusLabel.style.display = mode === 'label' ? 'flex' : 'none';
    }

    // 重置进度条
    if (this._progress) {
      this._progress.style.width = '0%';
    }

    // 清除顶部标签
    if (this._label) {
      this._label.textContent = '';
    }
  }

  /**
   * 恢复生成中状态（页面重连后调用）
   * @param {string} currentAgent - 后端当前正在执行的 agent 名称
   */
  restoreGenerating(currentAgent) {
    if (!currentAgent) return;

    const idx = this._stages.findIndex(s => s.agent === currentAgent);
    if (idx === -1) return;

    this._activeIndex = idx;
    this._visible = true;

    // 显示状态条
    if (this._bar) {
      this._bar.classList.add('pipeline-bar--active');
    }

    // 更新 UI
    this._updateUI();
  }

  // ── 显示模式切换 ─────────────────────────────────────

  /**
   * 初始化设置面板中的显示模式切换按钮
   */
  _initDisplayToggle() {
    const toggleContainer = document.getElementById('statusDisplayToggle');
    if (!toggleContainer) return;

    const buttons = toggleContainer.querySelectorAll('.settings-tag-btn');

    buttons.forEach(btn => {
      btn.addEventListener('click', () => {
        const mode = btn.dataset.mode;
        if (!mode) return;

        // 更新按钮激活状态
        buttons.forEach(b => b.classList.remove('settings-tag-btn--active'));
        btn.classList.add('settings-tag-btn--active');

        // 保存到状态 & localStorage
        App.state.statusDisplayMode = mode;
        localStorage.setItem('rain_statusDisplayMode', mode);

        // 应用显示模式
        this._applyDisplayMode(mode);

        // 如果正在生成中，刷新当前阶段显示
        if (this._visible && this._activeIndex >= 0) {
          this._refreshCurrentStage();
        }
      });
    });
  }

  /**
   * 应用显示模式：显示/隐藏对应元素
   * @param {string} mode - 'bubbles' 或 'label'
   */
  _applyDisplayMode(mode) {
    // 气泡容器
    if (this._bubbleContainer) {
      this._bubbleContainer.style.display = mode === 'bubbles' ? 'flex' : 'none';
    }

    // 单行标签容器：只有生成进行中才显示
    if (this._statusLabel) {
      const shouldShow = mode === 'label' && this._visible && this._activeIndex >= 0;
      this._statusLabel.style.display = shouldShow ? 'flex' : 'none';
    }
  }

  /**
   * 刷新当前阶段显示（切换模式后重新渲染）
   */
  _refreshCurrentStage() {
    if (!this._visible || this._activeIndex < 0) return;
    const stage = this._stages[this._activeIndex];
    if (!stage) return;

    const mode = App.state.statusDisplayMode || 'bubbles';

    if (mode === 'bubbles') {
      // 气泡模式：添加当前阶段的气泡
      this._addBubble(stage);
    } else {
      // 单行模式：更新标签文本
      if (this._statusText) {
        this._statusText.textContent = stage.emoji + ' ' + stage.label;
      }
      if (this._statusLabel) {
        this._statusLabel.style.display = 'flex';
      }
    }
  }

  // ── 内部方法 ────────────────────────────────────

  _updateUI() {
    console.log('[PipelineStatusBar] _updateUI called, visible:', this._visible, 'activeIndex:', this._activeIndex);
    if (!this._visible || this._activeIndex === -1) {
      console.log('[PipelineStatusBar] _updateUI early return - not visible or no active index');
      return;
    }

    // 显示状态条
    if (this._bar) {
      this._bar.classList.add('pipeline-bar--active');
      console.log('[PipelineStatusBar] Pipeline bar activated, display:', this._bar.style.display, 'classList:', this._bar.className);
    } else {
      console.error('[PipelineStatusBar] _bar element not found!');
    }

    // 更新节点状态
    if (this._nodes) {
      const nodeEls = this._nodes.querySelectorAll('.pipeline-bar__node');
      nodeEls.forEach((el, idx) => {
        el.classList.remove('pipeline-bar__node--done', 'pipeline-bar__node--active', 'pipeline-bar__node--pending');
        const dot = el.querySelector('.pipeline-bar__dot');
        if (dot) {
          dot.classList.remove('pipeline-bar__dot--done', 'pipeline-bar__dot--active', 'pipeline-bar__dot--pending');
        }
        if (idx < this._activeIndex) {
          el.classList.add('pipeline-bar__node--done');
          if (dot) dot.classList.add('pipeline-bar__dot--done');
        } else if (idx === this._activeIndex) {
          el.classList.add('pipeline-bar__node--active');
          if (dot) dot.classList.add('pipeline-bar__dot--active');
        } else {
          el.classList.add('pipeline-bar__node--pending');
          if (dot) dot.classList.add('pipeline-bar__dot--pending');
        }
      });
    }

    // 更新顶部标签
    if (this._label) {
      const stage = this._stages[this._activeIndex];
      if (stage) {
        this._label.textContent = stage.emoji + ' ' + stage.label;
      }
    }

    // 显示进度条
    if (this._progress) {
      const pct = ((this._activeIndex + 1) / this._stages.length) * 100;
      this._progress.style.width = pct + '%';
    }

    // 根据显示模式更新对应元素
    const mode = App.state.statusDisplayMode || 'bubbles';

    if (mode === 'bubbles') {
      // 气泡模式：添加气泡
      if (this._bubbleContainer && this._stages[this._activeIndex]) {
        this._addBubble(this._stages[this._activeIndex]);
      }
    } else {
      // 单行模式：更新标签文本
      if (this._statusText && this._stages[this._activeIndex]) {
        const stage = this._stages[this._activeIndex];
        this._statusText.textContent = stage.emoji + ' ' + stage.label;
        if (this._statusLabel) {
          this._statusLabel.style.display = 'flex';
        }
      }
    }
  }

  _addBubble(stage) {
    console.log('[PipelineStatusBar] Adding bubble for stage:', stage);
    const bubble = document.createElement('div');
    bubble.className = 'pipeline-bubble';
    bubble.textContent = stage.emoji + ' ' + stage.label;

    this._bubbles.push({ agent: stage.agent, label: stage.label, el: bubble });
    this._bubbleContainer.appendChild(bubble);
    console.log('[PipelineStatusBar] Bubble added, container children count:', this._bubbleContainer.children.length);

    // 限制气泡数量
    if (this._bubbles.length > this._MAX_BUBBLES) {
      const old = this._bubbles.shift();
      if (old.el.parentNode) {
        old.el.parentNode.removeChild(old.el);
        console.log('[PipelineStatusBar] Removed oldest bubble');
      }
    }
  }
}
