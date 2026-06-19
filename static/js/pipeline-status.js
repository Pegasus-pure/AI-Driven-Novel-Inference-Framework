/**
 * pipeline-status.js — Agent 流水线状态条
 *
 * 监听 agent_status 事件，在标题栏下方显示 Pipeline 各层处理进度，
 * 并在叙事区内（选项区域上方）显示生成状态文字。
 * agent name 列表与 pipeline.py 中 progress_cb 的 key 保持一致。
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

    // 叙事区内的生成状态标签（选项区域上方）
    /** @type {HTMLElement} */
    this._statusLabel = null;
    /** @type {HTMLElement} */
    this._statusText = null;

    /** @type {Array} 流水线层级定义（agent name 必须匹配服务端 pipeline.py 中 progress_cb 的 key） */
    this._stages = [
      { agent: 'context_builder',   label: '上下文',   short: '\u{1F4CB}' },
      { agent: 'scene_director',    label: '导演',     short: '\u{1F3AC}' },
      { agent: 'continuity_checker', label: '审计',    short: '\u{1F50D}' },
      { agent: 'motivation',        label: '动机',     short: '\u{1F9E0}' },
      { agent: 'dialogue',          label: '对话',     short: '\u{1F4AC}' },
      { agent: 'role_reflector',    label: '反思',     short: '\u{2728}' },
      { agent: 'composer',          label: '编剧',     short: '\u{270F}' },
      { agent: 'auditor',           label: '验收',     short: '\u{1F4CB}' },
      { agent: 'thread_manager',    label: '线索',     short: '\u{1F9F5}' },
      { agent: 'oracle',            label: '神谕',     short: '\u{1F52E}' },
    ];

    /** @type {number} 当前活跃层级索引 (-1 = 无) */
    this._activeIndex = -1;
    /** @type {boolean} */
    this._visible = false;
    /** @type {number|null} 隐藏超时 */
    this._hideTimeout = null;
  }

  init() {
    this._bar = document.getElementById('pipelineBar');
    this._nodes = document.getElementById('pipelineNodes');
    this._label = document.getElementById('pipelineLabel');
    this._progress = document.getElementById('pipelineProgress');

    // 叙事区状态标签
    this._statusLabel = document.getElementById('pipelineStatusLabel');
    if (this._statusLabel) {
      this._statusText = this._statusLabel.querySelector('.pipeline-status-label__text');
    }

    if (!this._bar || !this._nodes) {
      console.warn('[PipelineStatus] 未找到容器元素');
      return;
    }

    // 渲染流水线节点
    this._renderNodes();

    // 监听 agent_status 事件
    App.on('agent_status', (payload) => this._onAgentStatus(payload));

    // 监听叙事块到达 → 隐藏状态标签
    App.on('narrative_chunk', () => this._hideStatusLabel());

    // 监听叙事完成 → 隐藏流水线
    App.on('narrative_complete', () => this._scheduleHide());

    console.log('[PipelineStatus] 初始化完成');
  }

  // ═══════════════════════════════════════════════
  // 内部方法
  // ═══════════════════════════════════════════════

  /**
   * 渲染流水线节点
   */
  _renderNodes() {
    this._nodes.innerHTML = '';

    this._stages.forEach((stage) => {
      const node = document.createElement('div');
      node.className = 'pipeline-bar__node pipeline-bar__node--pending';
      node.dataset.agent = stage.agent;

      node.innerHTML = `
        <span class="pipeline-bar__dot pipeline-bar__dot--pending"></span>
        <span class="pipeline-bar__node-text">${stage.short} ${stage.label}</span>
      `;

      this._nodes.appendChild(node);
    });
  }

  /**
   * 处理 agent_status 事件
   * @param {Object} payload - { agent: string|null, label: string }
   */
  _onAgentStatus(payload) {
    if (!payload) return;

    const agent = payload.agent || null;
    const label = payload.label || '';

    if (!agent) {
      // agent = null → Pipeline 完成，安排隐藏
      this._scheduleHide();
      return;
    }

    // 找到当前 agent 在 stages 中的索引（-1 表示未知 agent）
    const foundIndex = this._stages.findIndex(s => s.agent === agent);

    // 始终更新叙事区状态标签（不依赖 agent 匹配）
    this._updateStatusLabel(label, foundIndex);

    // 只有已知 agent 才更新顶部流水线条
    if (foundIndex >= 0) {
      this._activeIndex = foundIndex;
      this._show();

      // 更新节点状态
      const nodeEls = this._nodes.querySelectorAll('.pipeline-bar__node');
      nodeEls.forEach((el, i) => {
        const dot = el.querySelector('.pipeline-bar__dot');
        el.classList.remove('pipeline-bar__node--done', 'pipeline-bar__node--active', 'pipeline-bar__node--pending');

        if (i < foundIndex) {
          el.classList.add('pipeline-bar__node--done');
          if (dot) {
            dot.className = 'pipeline-bar__dot pipeline-bar__dot--done';
          }
        } else if (i === foundIndex) {
          el.classList.add('pipeline-bar__node--active');
          if (dot) {
            dot.className = 'pipeline-bar__dot pipeline-bar__dot--active';
          }
        } else {
          el.classList.add('pipeline-bar__node--pending');
          if (dot) {
            dot.className = 'pipeline-bar__dot pipeline-bar__dot--pending';
          }
        }
      });

      // 更新标签文字
      if (this._label) {
        this._label.textContent = label || `${this._stages[foundIndex].label}生成中...`;
      }

      // 更新进度条
      if (this._progress) {
        const pct = ((foundIndex + 1) / this._stages.length) * 100;
        this._progress.style.width = `${pct}%`;
      }
    }

    // 取消隐藏定时器
    if (this._hideTimeout) {
      clearTimeout(this._hideTimeout);
      this._hideTimeout = null;
    }
  }

  /**
   * 显示流水线条
   */
  _show() {
    if (this._visible) return;
    this._visible = true;
    this._bar.classList.add('pipeline-bar--active');
  }

  /**
   * 隐藏流水线条（延迟 0.5s 渐隐）
   */
  _scheduleHide() {
    // 先设为已完成
    const nodeEls = this._nodes.querySelectorAll('.pipeline-bar__node');
    nodeEls.forEach(el => {
      const dot = el.querySelector('.pipeline-bar__dot');
      el.classList.remove('pipeline-bar__node--active', 'pipeline-bar__node--pending');
      el.classList.add('pipeline-bar__node--done');
      if (dot) {
        dot.className = 'pipeline-bar__dot pipeline-bar__dot--done';
      }
    });

    if (this._progress) {
      this._progress.style.width = '100%';
    }
    if (this._label) {
      this._label.textContent = '';
    }

    // 延迟隐藏
    if (this._hideTimeout) {
      clearTimeout(this._hideTimeout);
    }
    this._hideTimeout = setTimeout(() => {
      this._bar.classList.remove('pipeline-bar--active');
      this._visible = false;
      this._activeIndex = -1;
      this._hideTimeout = null;
    }, 800);
  }

  /**
   * 更新叙事区内的生成状态标签（选项区域上方）
   * @param {string} label - 状态文字
   * @param {number} stageIndex - 当前阶段索引（-1 表示未知 agent）
   */
  _updateStatusLabel(label, stageIndex) {
    if (!this._statusLabel || !this._statusText) return;

    // 显示状态文字
    this._statusText.textContent = label || '正在生成...';
    this._statusLabel.style.display = 'flex';

    // 更新圆点
    const dot = this._statusLabel.querySelector('.pipeline-status-label__dot');
    if (dot) {
      if (stageIndex >= 0) {
        dot.textContent = stageIndex + 1;
        dot.style.background = '#3B6D11';
      } else {
        // 未知 agent → 显示圆点脉冲但无编号
        dot.textContent = '';
        dot.style.background = '#639922';
      }
    }
  }

  /**
   * 隐藏叙事区状态标签（narrative_chunk 事件触发）
   */
  _hideStatusLabel() {
    if (!this._statusLabel) return;
    this._statusLabel.style.display = 'none';
  }
}
