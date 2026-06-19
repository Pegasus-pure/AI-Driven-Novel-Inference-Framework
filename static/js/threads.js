/**
 * threads.js — 叙事线索面板渲染 (F8)
 *
 * 功能:
 *  - 渲染活跃线索 (active) 和已演化线索 (evolved)
 *  - 每个线索显示标题、类型、问题、强度/复杂度/张力条
 *  - 涉及角色显示
 *
 * 数据源: App.state.narrative_threads
 *   { active: [...], evolved: [...] }
 */

import { App } from './app.js';

export class ThreadsRenderer {
  constructor() {
    /** @type {HTMLElement} */
    this._container = null;
    /** @type {Object} 当前线索数据 */
    this._threads = { active: [], evolved: [] };
    /** @type {Object} Canon 角色数据（用于 ID → 名称转换） */
    this._canonCharacters = [];
  }

  init() {
    this._container = document.getElementById('threadsPanelContent');

    if (!this._container) {
      console.warn('[Threads] 未找到 #threadsPanelContent 容器');
      return;
    }

    // 监听状态同步 → 更新线索
    App.on('state_sync', (payload) => {
      if (payload && payload.narrative_threads) {
        this._threads = payload.narrative_threads;
        // 如果线索面板可见，渲染
        if (document.getElementById('panel-threads')?.classList.contains('panel--active')) {
          this.render();
        }
      }
    });

    // 面板切换时渲染
    App.on('panel_changed', (data) => {
      if (data && data.panel === 'threads') {
        this.render();
      }
    });

    // Canon 就绪时保存角色数据
    App.on('canon_ready', (payload) => {
      if (payload && payload.characters) {
        this._canonCharacters = payload.characters || [];
      }
    });

    // 初始空状态
    this._renderEmpty();

    console.log('[Threads] 初始化完成');
  }

  /**
   * 渲染线索面板
   */
  render() {
    if (!this._container) return;

    const active = this._threads.active || [];
    const evolved = this._threads.evolved || [];

    if (active.length === 0 && evolved.length === 0) {
      this._renderEmpty();
      return;
    }

    let html = `<div class="threads-title">🧵 叙事线索`;
    if (active.length > 0) {
      html += ` <span class="threads-title__count">${active.length} 活跃</span>`;
    }
    html += `</div>`;

    // ── 活跃线索 ──
    if (active.length > 0) {
      html += `<div class="threads-section-title">● 活跃线索</div>`;
      active.forEach(t => {
        html += this._renderThreadCard(t, false);
      });
    }

    // ── 已演化线索 ──
    if (evolved.length > 0) {
      html += `<div class="threads-section-title">○ 已演化线索</div>`;
      evolved.forEach(t => {
        html += this._renderThreadCard(t, true);
      });
    }

    this._container.innerHTML = html;
  }

  /**
   * 渲染单个线索卡片
   * @param {Object} t - 线索数据
   * @param {boolean} isEvolved - 是否已演化
   * @returns {string} HTML
   */
  _renderThreadCard(t, isEvolved) {
    if (!t) return '';

    const title = t.title || '未命名线索';
    const type = t.type || 'side';
    const typeLabel = type === 'main' ? '主线' : '支线';
    const question = t.question || '';
    const intensity = typeof t.intensity === 'number' ? t.intensity : 0;
    const complexity = typeof t.complexity === 'number' ? t.complexity : 0;
    const tension = typeof t.tension === 'number' ? t.tension : 0;
    const charIds = t.involved_characters || [];
    const status = t.status || '';
    const outcome = t.outcome || '';

    const cardClass = isEvolved ? 'thread-card thread-card--evolved' : 'thread-card';
    const typeClass = type === 'main' ? 'thread-card__type--main' : 'thread-card__type--side';

    let html = `<div class="${cardClass}">`;
    html += '<div class="thread-card__header">';
    html += `<span class="thread-card__title">🧵 ${this._esc(title)}</span>`;
    if (isEvolved) {
      const statusLabel = { resolved: '已解决', transformed: '已转化', abandoned: '已废弃' };
      html += `<span class="thread-card__status">${statusLabel[status] || status || '已完成'}</span>`;
    } else {
      html += `<span class="thread-card__type ${typeClass}">${typeLabel}</span>`;
    }
    html += '</div>';

    // 核心问题
    if (question) {
      html += `<div class="thread-card__question">❓ ${this._esc(question)}</div>`;
    }

    // 统计条
    if (!isEvolved) {
      html += '<div class="thread-card__stats">';
      html += this._statBar('强度', intensity, 'intensity');
      html += this._statBar('复杂度', complexity, 'complexity');
      html += this._statBar('张力', tension, 'tension');
      html += '</div>';
    }

    // 涉及角色
    if (charIds.length > 0) {
      const charNames = charIds.map(id => {
        const found = this._canonCharacters.find(c => c.id === id);
        return found ? found.name : id;
      }).join(' · ');
      html += `<div class="thread-card__chars">涉及: <span>${this._esc(charNames)}</span></div>`;
    }

    // 演化结果
    if (isEvolved && outcome) {
      html += `<div class="thread-card__outcome">${this._esc(outcome)}</div>`;
    }

    html += '</div>';
    return html;
  }

  /**
   * 渲染统计条
   * @param {string} label - 标签
   * @param {number} value - 0.0~1.0
   * @param {string} type - css class 后缀
   * @returns {string} HTML
   */
  _statBar(label, value, type) {
    const pct = Math.round(Math.max(0, Math.min(1, value)) * 100);
    return `
      <div class="thread-card__stat">
        <span>${label}</span>
        <div class="thread-card__stat-bar">
          <div class="thread-card__stat-fill thread-card__stat-fill--${type}" style="width:${pct}%"></div>
        </div>
        <span>${Math.round(value * 10)}/10</span>
      </div>
    `;
  }

  /**
   * 渲染空状态
   */
  _renderEmpty() {
    if (!this._container) return;
    this._container.innerHTML = `
      <div class="threads-title">🧵 叙事线索</div>
      <div class="thread-card--empty">暂无活跃线索 — 开始冒险后将自动追踪故事脉络</div>
    `;
  }

  /**
   * HTML 实体转义
   * @param {string} str
   * @returns {string}
   */
  _esc(str) {
    if (!str) return '';
    const div = document.createElement('div');
    div.textContent = String(str);
    return div.innerHTML;
  }
}
