/**
 * soul-panel.js — 双魂面板组件
 *
 * 显示玩家灵魂 vs 原主灵魂的对比状态、支配比、内心独白。
 * 位于页面右侧面板，NPC 认知状态之上。
 * 监听 soul_state_update 事件（由后端 stream_beat 自动推送）。
 */

import { App } from '../app.js';

export class SoulPanel {
  constructor() {
    /** @type {HTMLElement} 面板容器 */
    this._container = null;
    /** @type {HTMLElement} 面板内容区 */
    this._content = null;
  }

  init() {
    this._container = document.getElementById('soulPanel');
    this._content = document.getElementById('soulPanelContent');

    // 监听灵魂状态更新
    App.on('soul_state_update', (data) => this._update(data));

    // 监听游戏模式切换（显示/隐藏）
    App.on('game_mode_changed', (mode) => {
      if (this._container) {
        this._container.style.display = mode === 'soul_possession' ? 'block' : 'none';
      }
    });

    // 从 state 恢复（如果有 soul_state）
    const soulState = App.state && App.state.soulState;
    if (soulState) {
      this._update(soulState);
    }

    console.log('[SoulPanel] 初始化完成');
  }

  /**
   * 更新面板数据
   * @param {Object} data - soul_state_update payload
   */
  _update(data) {
    if (!data || !this._content) return;

    const soul = data.soul || {};
    const playerProfile = soul.player || {};
    const canonProfile = soul.canon || {};
    const blendRatio = soul.blend_ratio != null ? soul.blend_ratio : 0.5;
    const innerVoice = soul.inner_voice || null;

    // 更新 UI
    this._setText('#soul-player-name', playerProfile.soul_name || '异界旅人');
    this._setText('#soul-player-motivation', playerProfile.core_motivation || '');

    this._setText('#soul-canon-name', canonProfile.name || '原主');
    this._setText('#soul-canon-role', canonProfile.role || '');

    // 支配比滑块
    const slider = this._content.querySelector('#blend-slider');
    const label = this._content.querySelector('#blend-label');
    if (slider) slider.value = Math.round(blendRatio * 100);
    if (label) {
      const pct = Math.round(blendRatio * 100);
      label.textContent = blendRatio >= 0.5
        ? `玩家主导 ${pct}%`
        : `原主主导 ${100 - pct}%`;
    }

    // 内心独白
    const voiceEl = this._content.querySelector('#soul-inner-voice');
    if (voiceEl) {
      voiceEl.textContent = innerVoice || '';
      voiceEl.style.display = innerVoice ? 'block' : 'none';
    }

    // 保存到 state 供后续恢复
    if (App.state) {
      App.state.soulState = data;
    }
  }

  /** 设置文本内容 */
  _setText(selector, text) {
    const el = this._content.querySelector(selector);
    if (el) el.textContent = text || '';
  }
}
