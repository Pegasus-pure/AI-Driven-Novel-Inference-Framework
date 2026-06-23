/**
 * world-rules.js — 世界观独立面板渲染 + 编辑模态框
 *
 * 功能:
 *  - 世界观信息渲染（F2 独立面板）
 *  - 世界观编辑模态框联动（#worldRulesEditModal）
 *
 * 将世界观从角色面板中移出，成为独立侧边栏面板。
 */

import { App } from './app.js';

export class WorldRulesRenderer {
  constructor() {
    /** @type {HTMLElement} 世界观面板容器 */
    this._worldPanel = null;
    /** @type {Object} 当前 Canon world_rules */
    this._worldRules = {};
    /** @type {Object} 当前 Canon meta */
    this._canonMeta = {};
  }

  init() {
    this._worldPanel = document.getElementById('worldPanelContent');

    // Canon 就绪
    App.on('canon_ready', (payload) => {
      if (payload) {
        this._worldRules = payload.world_rules || {};
        this._canonMeta = payload.meta || {};
        this._renderWorldRules();
      }
    });

    // Canon 条目更新后刷新
    App.on('canon_entries_updated', (payload) => {
      if (payload && payload.success) {
        console.log('[WorldRules] canon_entries_updated:', payload.message);
      }
    });

    // 绑定事件
    this._bindEvents();

    console.log('[WorldRules] 初始化完成');
  }

  // ═══════════════════════════════════════════════════
  // 渲染
  // ═══════════════════════════════════════════════════

  /**
   * 渲染世界观面板内容
   */
  _renderWorldRules() {
    if (!this._worldPanel) return;

    const wr = this._worldRules || {};
    const meta = this._canonMeta || {};

    let html = '<div class="world-panel-title">🌍 世界观';
    html += ' <button class="world-rules-section__edit-btn" id="btnEditWorldRules">✏️ 编辑</button>';
    html += '</div>';

    // Meta 信息
    if (meta.title) {
      html += `<div class="world-rules-item">📖 书名: <span>${this._esc(meta.title)}</span></div>`;
    }
    if (meta.author) {
      html += `<div class="world-rules-item">✍️ 作者: <span>${this._esc(meta.author)}</span></div>`;
    }
    if (meta.genre && meta.genre.length > 0) {
      const genres = Array.isArray(meta.genre) ? meta.genre.join(' · ') : meta.genre;
      html += `<div class="world-rules-item">🏷️ 类型: <span>${this._esc(genres)}</span></div>`;
    }
    if (meta.extraction_confidence != null) {
      const conf = (parseFloat(meta.extraction_confidence) * 100).toFixed(0);
      html += `<div class="world-rules-item">🎯 提取置信度: <span>${conf}%</span></div>`;
    }

    // World Rules
    if (wr.era) {
      html += `<div class="world-rules-item">⏳ 时代: <span>${this._esc(wr.era)}</span></div>`;
    }

    if (wr.species && Array.isArray(wr.species) && wr.species.length > 0) {
      html += `<div class="world-rules-item">🧬 物种: <span>${this._esc(wr.species.join(' · '))}</span></div>`;
    }

    if (wr.magic_system && typeof wr.magic_system === 'object' && Object.keys(wr.magic_system).length > 0) {
      html += '<div class="world-rules-item">✨ 魔法系统: <span>已定义</span></div>';
    }

    if (wr.society && typeof wr.society === 'object' && Object.keys(wr.society).length > 0) {
      html += '<div class="world-rules-item">🏛️ 社会结构: <span>已定义</span></div>';
    }

    const hasAny = meta.title || wr.era || (wr.species && wr.species.length > 0) ||
      Object.keys(wr.magic_system || {}).length > 0 ||
      Object.keys(wr.society || {}).length > 0;

    if (!hasAny) {
      html += '<div class="world-rules-item--empty">暂无世界观信息 — 导入小说后将自动提取</div>';
    }

    this._worldPanel.innerHTML = html;

    // 重新绑定编辑按钮（因为 innerHTML 重建了 DOM）
    const editBtn = document.getElementById('btnEditWorldRules');
    if (editBtn) {
      editBtn.addEventListener('click', () => this._openWorldRulesModal());
    }
  }

  // ═══════════════════════════════════════════════════
  // 世界观编辑模态框
  // ═══════════════════════════════════════════════════

  /**
   * 打开世界观编辑模态框
   */
  _openWorldRulesModal() {
    const wr = this._worldRules || {};

    const setVal = (id, value) => {
      const el = document.getElementById(id);
      if (el) el.value = value || '';
    };

    setVal('wrEditEra', wr.era || '');

    // JSON 字段格式化
    const magicJson = wr.magic_system ? JSON.stringify(wr.magic_system, null, 2) : '';
    setVal('wrEditMagic', magicJson);

    const societyJson = wr.society ? JSON.stringify(wr.society, null, 2) : '';
    setVal('wrEditSociety', societyJson);

    const species = Array.isArray(wr.species) ? wr.species.join(', ') : (wr.species || '');
    setVal('wrEditSpecies', species);

    const modal = document.getElementById('worldRulesEditModal');
    if (modal) modal.style.display = 'flex';
  }

  /**
   * 保存世界观规则
   */
  _saveWorldRules() {
    const getVal = (id) => {
      const el = document.getElementById(id);
      return el ? el.value.trim() : '';
    };

    const parseJsonField = (id) => {
      const raw = getVal(id);
      if (!raw) return {};
      try {
        return JSON.parse(raw);
      } catch (e) {
        return {};
      }
    };

    const splitTags = (id) => {
      const raw = getVal(id);
      if (!raw) return [];
      return raw.split(',').map(s => s.trim()).filter(s => s);
    };

    const worldRulesData = {
      era: getVal('wrEditEra'),
      magic_system: parseJsonField('wrEditMagic'),
      society: parseJsonField('wrEditSociety'),
      species: splitTags('wrEditSpecies'),
    };

    App.ws.send('update_canon_entry', {
      entity_type: 'world_rule',
      action: 'update',
      entry_id: 'world_rules',
      data: { world_rules: worldRulesData },
    });

    this._closeWorldRulesModal();
  }

  /**
   * 关闭世界观编辑模态框
   */
  _closeWorldRulesModal() {
    const modal = document.getElementById('worldRulesEditModal');
    if (modal) modal.style.display = 'none';
  }

  // ═══════════════════════════════════════════════════
  // 事件绑定
  // ═══════════════════════════════════════════════════

  _bindEvents() {
    // ── 世界观编辑模态框按钮 ──
    const btnWrSave = document.getElementById('btnWrSave');
    if (btnWrSave) {
      btnWrSave.addEventListener('click', () => this._saveWorldRules());
    }

    const btnWrCancel = document.getElementById('btnWrCancel');
    if (btnWrCancel) {
      btnWrCancel.addEventListener('click', () => this._closeWorldRulesModal());
    }
  }

  // ═══════════════════════════════════════════════════
  // 辅助方法
  // ═══════════════════════════════════════════════════

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
