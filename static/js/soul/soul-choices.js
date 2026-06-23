/**
 * soul-choices.js — 本我/贴合 二选一组件
 *
 * 在每拍叙事完成后替代旧 choices，显示 [本我] 和 [贴合] 两个选项。
 * 复用 ChoicePanel 的容器 #choicePanel。
 */

import { EventBus } from '../stores/EventBus.js';

export class SoulChoiceRenderer {
  constructor() {
    this._container = document.getElementById('choicePanel');
    this._currentBeatId = '';
  }

  init() {
    if (!this._container) return;
    EventBus.on('soul_choice_needed', (data) => this._render(data));
  }

  _render(data) {
    if (!this._container) return;
    this._currentBeatId = data.beat_id || '';

    this._container.innerHTML = `
      <div class="soul-choices">
        <button class="soul-btn soul-btn-authentic" data-action="authentic">
          <span class="soul-btn-icon">💠</span>
          <span class="soul-btn-label">本我行动</span>
          <span class="soul-btn-desc">按自己的性格行事</span>
          <span class="soul-btn-effect">冲突 +0.10</span>
        </button>
        <button class="soul-btn soul-btn-conforming" data-action="conforming">
          <span class="soul-btn-icon">◇</span>
          <span class="soul-btn-label">贴合行动</span>
          <span class="soul-btn-desc">模仿原主的方式回应</span>
          <span class="soul-btn-effect">冲突 -0.08</span>
        </button>
      </div>
    `;

    this._container.querySelectorAll('.soul-btn').forEach((btn) => {
      btn.addEventListener('click', () => {
        const actionType = btn.dataset.action;
        this._sendChoice(actionType);
      });
    });
  }

  _sendChoice(actionType) {
    import('../ws-client.js').then((mod) => {
      mod.sendSoulChoice(actionType, this._currentBeatId);
    });
  }
}
