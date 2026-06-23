/**
 * choices.js — ChoicePanel 选择按钮组件
 *
 * 在每段叙事完成后，显示 3-4 个结构化选择项，
 * 玩家点击选择后触发 choice_selected 事件。
 */

import { App } from './app.js';

export class ChoicePanel {
  constructor() {
    /** @type {HTMLElement} */
    this._container = null;
    /** @type {Array} */
    this._currentChoices = [];
    /** @type {boolean} */
    this._isDisabled = false;
  }

  init() {
    this._container = document.getElementById('choicePanel');

    if (!this._container) {
      console.warn('[ChoicePanel] 未找到 #choicePanel 容器');
      return;
    }

    // 监听 choices_ready 事件 → 渲染选择按钮
    App.on('choices_ready', (choices) => this.render(choices));

    // 监听 llm_busy → 禁用选择
    App.on('llm_busy', () => this.disable());

    console.log('[ChoicePanel] 初始化完成');
  }

  /**
   * 渲染选择按钮
   *
   * 支持两种模式：
   *   - 灵魂模式: { authentic: [...], conforming: [...] }
   *   - Klass 模式: [{id, text, hint, next_scene_hint}, ...]
   *
   * @param {Object|Array} choices
   */
  render(choices) {
    if (!this._container) return;

    this._container.innerHTML = '';

    if (!choices) {
      this._currentChoices = [];
      this._isDisabled = false;
      return;
    }

    // 灵魂模式：dict 带 authentic/conforming keys
    if (!Array.isArray(choices) && typeof choices === 'object') {
      this._currentActionChoices = {
        authentic: choices.authentic || [],
        conforming: choices.conforming || [],
      };
      this.renderSoulChoice(this._currentBeatId || '');
      return;
    }

    // Klass 模式：数组
    if (!Array.isArray(choices) || choices.length === 0) {
      this._currentChoices = [];
      this._isDisabled = false;
      return;
    }

    for (let i = 0; i < choices.length; i++) {
      const choice = choices[i];
      if (!choice || !choice.id || !choice.text) continue;

      const btn = document.createElement('button');
      btn.className = 'choice-btn';
      btn.dataset.id = choice.id;
      btn.innerHTML = `
        <span class="choice-btn__num">${i + 1}</span>
        <span class="choice-btn__body">
          <span class="choice-btn__text">${this._escapeHtml(choice.text)}</span>
          ${choice.hint ? `<span class="choice-btn__hint">${this._escapeHtml(choice.hint)}</span>` : ''}
        </span>
      `;

      btn.addEventListener('click', () => this._onChoiceClick(choice));
      this._container.appendChild(btn);
    }

    this._currentChoices = choices;
    this._isDisabled = false;

    // 滚动以确保选择面板可见
    if (this._container) {
      this._container.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
  }

  /**
   * 禁用所有选择按钮
   */
  disable() {
    this._isDisabled = true;
    if (!this._container) return;
    this._container.querySelectorAll('.choice-btn').forEach(b => {
      b.disabled = true;
    });
  }

  /**
   * 启用所有选择按钮
   */
  enable() {
    this._isDisabled = false;
    if (!this._container) return;
    this._container.querySelectorAll('.choice-btn').forEach(b => {
      b.disabled = false;
    });
  }

  /**
   * 渲染灵魂附生选择（本我/贴合）- Phase 1
   * @param {string} beatId - 当前 beat ID
   */
  renderSoulChoice(beatId) {
    if (!this._container) return;

    this._currentBeatId = beatId;
    this._isDisabled = false;

    this._container.innerHTML = `
      <div class="soul-choices">
        <button class="soul-btn soul-btn-authentic" data-action="authentic">
          <span class="soul-btn-icon">💠</span>
          <span class="soul-btn-label">本我行动</span>
          <span class="soul-btn-desc">按自己的性格行事</span>
          <span class="soul-btn-effect">冲突 +0.10</span>
        </button>
        <button class="soul-btn soul-btn-conforming" data-action="conforming">
          <span class="soul-btn-icon">🛡️</span>
          <span class="soul-btn-label">贴合角色</span>
          <span class="soul-btn-desc">模仿原主的行事方式</span>
          <span class="soul-btn-effect">冲突 -0.10</span>
        </button>
      </div>
    `;

    this._container.querySelectorAll('.soul-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        const action = btn.dataset.action;
        this._renderActionChoices(action);
      });
    });

    // 滚动以确保选择面板可见
    if (this._container) {
      this._container.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
  }

  /**
   * 渲染二级具体行动选项 - Phase 2
   * @param {string} mode - 'authentic' | 'conforming'
   */
  _renderActionChoices(mode) {
    const actions = this._currentActionChoices[mode] || [];
    if (actions.length === 0) {
      App.emit('choice_selected', { soul_mode: mode, action_id: mode, text: mode === 'authentic' ? '本我行动' : '贴合角色' });
      return;
    }

    this._container.innerHTML = `
      <div class="action-choices">
        <div class="action-choices-header">${mode === 'authentic' ? '💠 本我行动 — 选择具体行动' : '🛡️ 贴合角色 — 选择具体行动'}</div>
      </div>
    `;
    const container = this._container.querySelector('.action-choices');

    actions.forEach(a => {
      const btn = document.createElement('button');
      btn.className = 'action-btn';
      btn.innerHTML = `<span class="action-btn-text">${a.text}</span>${a.hint ? `<span class="action-btn-hint">${a.hint}</span>` : ''}`;
      btn.addEventListener('click', () => {
        App.emit('choice_selected', { soul_mode: mode, action_id: a.id, text: a.text });
      });
      container.appendChild(btn);
    });

    const backBtn = document.createElement('button');
    backBtn.className = 'action-btn action-btn-back';
    backBtn.textContent = '← 返回';
    backBtn.addEventListener('click', () => this.renderSoulChoice(this._currentBeatId));
    container.appendChild(backBtn);
  }

  /**
   * 清空所有选择按钮
   */
  clear() {
    if (this._container) {
      this._container.innerHTML = '';
    }
    this._currentChoices = [];
  }

  /**
   * 点击选择按钮后的处理
   * @param {Object} choice - 被点击的选择项
   * @private
   */
  _onChoiceClick(choice) {
    if (this._isDisabled) return;

    // WS 断开时检测：不发送并恢复按钮
    if (App.ws && !App.ws.isConnected()) {
      console.warn('[ChoicePanel] WebSocket 未连接，无法发送选择');
      // 显示短暂提示后恢复
      this._container.querySelectorAll('.choice-btn').forEach(b => {
        b.disabled = false;
        b.classList.remove('choice-btn--selected');
      });
      this._isDisabled = false;
      return;
    }

    const btn = this._container ? this._container.querySelector(`[data-id="${choice.id}"]`) : null;
    if (btn) {
      // 1. 高亮
      btn.classList.add('choice-btn--selected');
      // 2. 禁用所有按钮（防止快速连续点击）
      this.disable();
      // 3. 0.5s 后 emit choice_selected（匹配 CSS animation 时长）
      setTimeout(() => {
        App.emit('choice_selected', { choice_id: choice.id, text: choice.text });
      }, 500);
    }
  }

  /**
   * HTML 实体转义
   * @param {string} str
   * @returns {string}
   * @private
   */
  _escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
  }
}
