/**
 * save-ui.js — 存档/读档面板
 *
 * 功能:
 *  - 渲染 3 个存档槽位
 *  - 点击加载/保存/删除
 *  - 快速存档按钮
 *  - 自动存档指示
 */

import { App } from './app.js';

export class SaveUIRenderer {
  constructor() {
    /** @type {HTMLElement} */
    this._container = null;
    /** @type {Array} 槽位数据 */
    this._slots = [];
  }

  init() {
    this._container = document.getElementById('savePanelContent');

    // 存档列表响应
    App.on('save_list', (payload) => {
      if (payload && payload.slots) {
        this._slots = payload.slots;
        this.render();
      }
    });

    // 存档完成 → 刷新列表
    App.on('save_complete', () => {
      this._requestRefresh();
    });

    // 读档完成 → 刷新列表
    App.on('load_complete', () => {
      // 已恢复，刷新存档列表
      setTimeout(() => this._requestRefresh(), 500);
    });

    // 面板切换时刷新
    App.on('panel_changed', (data) => {
      if (data && data.panel === 'save') {
        this._requestRefresh();
      }
    });

    // 刷新按钮
    const btnRefresh = document.getElementById('btnRefreshSaves');
    if (btnRefresh) {
      btnRefresh.addEventListener('click', () => this._requestRefresh());
    }

    // 快速存档按钮
    const btnQuickSave = document.getElementById('btnQuickSave');
    if (btnQuickSave) {
      btnQuickSave.addEventListener('click', () => {
        if (App.ws && App.ws.isConnected()) {
          const slot = this._findEmptySlot();
          App.ws.send('save_game', { slot, name: '快速存档' });
        }
      });
    }

    // 初始加载
    setTimeout(() => this._requestRefresh(), 1000);

    console.log('[SaveUI] 初始化完成');
  }

  /**
   * 渲染存档面板
   */
  render() {
    if (!this._container) return;

    // 保留标题和操作按钮
    let html = '<div class="save-title">💾 存档管理</div>';

    if (this._slots.length === 0) {
      html += '<div class="save-slot save-slot--empty">正在加载存档列表...</div>';
    } else {
      this._slots.forEach(slot => {
        const isEmpty = !slot.name || slot.name === '(空)';
        const name = slot.name || '(空)';
        const beat = slot.beat_id || '';
        const location = slot.location || '';
        const timestamp = slot.timestamp || '';
        const slotNum = slot.slot || 0;

        if (isEmpty) {
          html += `
            <div class="save-slot save-slot--empty" data-slot="${slotNum}">
              <div class="save-slot__info">
                <div class="save-slot__name">📂 槽位 #${slotNum} — 空</div>
                <div class="save-slot__time">点击此槽位保存当前进度</div>
              </div>
              <div class="save-slot__actions">
                <button class="save-btn save-btn--small save-btn--save" data-action="save" data-slot="${slotNum}">💾 保存</button>
              </div>
            </div>
          `;
        } else {
          html += `
            <div class="save-slot" data-slot="${slotNum}">
              <div class="save-slot__info">
                <div class="save-slot__header">
                  <span class="save-slot__name">${name}</span>
                  <span class="save-slot__beat">${beat}</span>
                </div>
                <div class="save-slot__time">${timestamp}${location ? ' · ' + location : ''}</div>
              </div>
              <div class="save-slot__actions">
                <button class="save-btn save-btn--small save-btn--load" data-action="load" data-slot="${slotNum}">📂 读取</button>
                <button class="save-btn save-btn--small save-btn--save" data-action="save" data-slot="${slotNum}">💾 覆盖</button>
                <button class="save-btn save-btn--small save-btn--delete" data-action="delete" data-slot="${slotNum}">🗑️</button>
              </div>
            </div>
          `;
        }
      });
    }

    this._container.innerHTML = html;

    // 绑定事件
    this._bindSlotEvents();
  }

  // ═══════════════════════════════════════════════════
  // 内部方法
  // ═══════════════════════════════════════════════════

  _bindSlotEvents() {
    if (!this._container) return;

    this._container.querySelectorAll('[data-action]').forEach(btn => {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        const action = btn.dataset.action;
        const slot = parseInt(btn.dataset.slot, 10);

        if (!App.ws || !App.ws.isConnected()) {
          console.warn('[SaveUI] WebSocket 未连接');
          return;
        }

        if (action === 'save') {
          const name = prompt('存档名称（留空使用默认）:', '') || '';
          App.ws.send('save_game', { slot, name });
        } else if (action === 'load') {
          if (confirm(`确定要加载槽位 #${slot} 的存档吗？当前进度将丢失。`)) {
            App.ws.send('load_game', { slot });
          }
        } else if (action === 'delete') {
          if (confirm(`确定要删除槽位 #${slot} 的存档吗？此操作不可撤销。`)) {
            App.ws.send('delete_save', { slot });
          }
        }
      });
    });
  }

  _requestRefresh() {
    if (App.ws && App.ws.isConnected()) {
      App.ws.send('list_saves');
    }
  }

  _findEmptySlot() {
    for (let i = 0; i < 3; i++) {
      const slot = this._slots.find(s => s.slot === i);
      if (!slot || slot.name === '(空)') {
        return i;
      }
    }
    return 0; // 如果都满了，覆盖 slot_0
  }
}
