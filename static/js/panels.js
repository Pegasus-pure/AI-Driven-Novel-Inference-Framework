/**
 * panels.js — 面板切换
 *
 * 管理 7 个面板的切换：F1-F7 键 + 侧边栏按钮点击
 * 顺序: F1 剧情 → F2 世界观 → F3 角色 → F4 地点 → F5 日志 → F6 存档 → F7 设置
 */

import { App } from './app.js';

export class PanelManager {
  constructor() {
    /** @type {HTMLElement[]} 侧边栏按钮 */
    this._sidebarBtns = [];
    /** @type {HTMLElement[]} 面板元素 */
    this._panels = [];
    /** @type {Object<string,string>} 快捷键映射 */
    this._keyMap = {
      'F0': 'dashboard',
      'F1': 'narrative',
      'F2': 'world',
      'F3': 'characters',
      'F4': 'locations',
      'F5': 'log',
      'F6': 'save',
      'F7': 'settings',
      'F8': 'threads',
    };
  }

  init() {
    this._sidebarBtns = Array.from(document.querySelectorAll('.sidebar__btn'));
    this._panels = Array.from(document.querySelectorAll('.panel'));

    // 侧边栏点击
    this._sidebarBtns.forEach(btn => {
      btn.addEventListener('click', () => {
        const panelName = btn.dataset.panel;
        if (panelName) this.switchPanel(panelName);
      });
    });

    // 键盘快捷键
    document.addEventListener('keydown', (e) => {
      // 不在输入框中时触发快捷键
      const inputEl = document.getElementById('playerInput');
      if (e.target === inputEl) return;

      const panelName = this._keyMap[e.key];
      if (panelName) {
        e.preventDefault();
        this.switchPanel(panelName);
      }
    });

    console.log('[Panels] 初始化完成, 快捷键:', Object.keys(this._keyMap));
  }

  /**
   * 切换到指定面板
   * @param {string} panelName - narrative|world|characters|locations|log|save|settings
   */
  switchPanel(panelName) {
    App.state.activePanel = panelName;

    // 切换面板显示
    this._panels.forEach(p => {
      p.classList.toggle('panel--active', p.id === `panel-${panelName}`);
    });

    // 切换侧边栏高亮
    this._sidebarBtns.forEach(btn => {
      btn.classList.toggle('sidebar__btn--active', btn.dataset.panel === panelName);
    });

    // 切换到剧情面板时的操作
    if (panelName === 'narrative') {
      // 输入栏已移除，无需聚焦
    }

    // 切换到存档面板时刷新列表
    if (panelName === 'save') {
      App.emit('refresh_saves');
    }

    App.emit('panel_changed', { panel: panelName });
  }
}
