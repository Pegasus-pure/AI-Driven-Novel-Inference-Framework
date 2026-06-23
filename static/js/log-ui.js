/**
 * log-ui.js — 事件日志面板渲染
 *
 * 从 eventLog 渲染节拍事件列表
 */

import { App } from './app.js';

export class LogRenderer {
  constructor() {
    /** @type {HTMLElement} */
    this._container = null;
  }

  init() {
    this._container = document.getElementById('logPanelContent');

    // 监听状态同步（含 event_log）
    App.on('state_sync', (payload) => {
      if (payload && payload.event_log) {
        this._renderLog(payload.event_log);
      }
    });

    // 叙事完成后追加新日志
    App.on('narrative_complete', (payload) => {
      if (payload && payload.beat_id) {
        // 请求服务器发送最新日志
        if (App.ws && App.ws.isConnected()) {
          App.ws.send('list_saves'); // 这会触发 state_sync
        }
      }
    });

    // 初始渲染空状态
    this._renderEmpty();

    console.log('[Log] 初始化完成');
  }

  /**
   * 渲染事件日志
   * @param {Array} eventLog
   */
  _renderLog(eventLog) {
    if (!this._container) return;

    if (!eventLog || eventLog.length === 0) {
      this._renderEmpty();
      return;
    }

    let html = '<div class="log-title">📜 事件日志</div>';

    eventLog.forEach(entry => {
      const beatId = entry.beat_id || '';
      const time = entry.time || '';
      const type = entry.type || '';
      const text = (entry.text || '').substring(0, 150);

      let entryClass = '';
      if (type === 'event' || text.includes('✦') || text.includes('⚡')) {
        entryClass = 'log-entry__text--event';
      } else if (text.includes('偏离') || text.includes('命运')) {
        entryClass = 'log-entry__text--important';
      }

      html += `
        <div class="log-entry">
          <span class="log-entry__time">${beatId}</span>
          <span class="log-entry__text ${entryClass}">${text || '(无描述)'}</span>
        </div>
      `;
    });

    this._container.innerHTML = html;
  }

  _renderEmpty() {
    if (!this._container) return;

    this._container.innerHTML = `
      <div class="log-title">📜 事件日志</div>
      <div class="log-entry--empty">暂无事件 — 开始冒险后将记录关键事件</div>
    `;
  }
}
