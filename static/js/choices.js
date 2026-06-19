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
   * @param {Array} choices - 选择项数组 [{id, text, hint, next_scene_hint}]
   */
  render(choices) {
    if (!this._container) return;

    // 清空容器
    this._container.innerHTML = '';

    if (!choices || !Array.isArray(choices) || choices.length === 0) {
      this._currentChoices = [];
      this._isDisabled = false;
      return;
    }

    // 为每个 choice 创建一个按钮
    for (let i = 0; i < choices.length; i++) {
      const choice = choices[i];
      if (!choice || !choice.id || !choice.text) continue;

      const btn = document.createElement('button');
      btn.className = 'choice-btn';
      btn.dataset.id = choice.id;
      btn.innerHTML = `
        <span class="choice-btn__num">(${i + 1})</span>
        <span class="choice-btn__text">${this._escapeHtml(choice.text)}</span>
        ${choice.hint ? `<span class="choice-btn__hint">— ${this._escapeHtml(choice.hint)}</span>` : ''}
      `;

      btn.addEventListener('click', () => this._onChoiceClick(choice));
      this._container.appendChild(btn);
    }

    this._currentChoices = choices;
    this._isDisabled = false;
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
