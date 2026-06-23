/**
 * locations.js — 地点面板渲染 + 编辑模态框
 *
 * 功能:
 *  - 地点卡片列表（可点击查看/编辑）
 *  - 新增地点 → 空白模态框 + 自动 ID
 *  - 编辑地点 → 保存到运行 Canon
 *  - 删除地点 → 直接从列表移除
 *  - 监听 canon_entries_updated → 刷新
 */

import { App } from './app.js';

export class LocationsRenderer {
  constructor() {
    /** @type {HTMLElement} */
    this._container = null;
    /** @type {HTMLElement} 地点列表容器 */
    this._listContainer = null;
    /** @type {Array} 已知地点列表 */
    this._locations = [];
    /** @type {Object} 动态地点 */
    this._dynamicLocations = {};
    /** @type {string} 当前编辑地点 ID */
    this._editingLocId = '';
    /** @type {string} 编辑模式 'edit' | 'new' */
    this._editMode = 'edit';
  }

  init() {
    this._container = document.getElementById('locationsPanelContent');
    this._listContainer = document.getElementById('locationsListContent');

    // Canon 就绪时加载地点
    App.on('canon_ready', (payload) => {
      if (payload && payload.locations && payload.locations.length > 0) {
        this._locations = payload.locations;
        this.render();
      } else if (payload && payload.locations) {
        this._locations = [];
        this.render();
      }
    });

    // Canon 条目更新后刷新
    App.on('canon_entries_updated', (payload) => {
      if (payload && payload.success && payload.entity_type === 'location') {
        console.log('[Locations] canon_entries_updated:', payload.message);
      }
    });

    // 监听 state_sync 中的 dynamic_locations
    App.on('state_sync', (payload) => {
      if (payload && payload.dynamic_locations) {
        this._dynamicLocations = payload.dynamic_locations;
        // 如果已渲染，追加动态地点
        if (this._locations.length > 0) {
          this.render();
        }
      }
    });

    // 绑定事件
    this._bindEvents();

    // 初始空状态
    this._renderDefaultLocations();

    console.log('[Locations] 初始化完成');
  }

  /**
   * 渲染地点面板
   */
  render() {
    if (!this._listContainer) return;

    if (this._locations.length === 0) {
      this._renderDefaultLocations();
      return;
    }

    let html = '';

    // ── Canon 地点 ──
    this._locations.forEach(loc => {
      const name = loc.name || '未知地点';
      const type = loc.type || '未知';
      const description = loc.description || '';
      const atmosphere = loc.atmosphere || '';
      const parent = loc.parent || '';
      const locId = loc.id || '';

      html += `
        <div class="loc-card" data-loc-id="${this._esc(locId)}">
          <div class="loc-card__name">🏚️ ${this._esc(name)}</div>
          <div class="loc-card__desc">
            类型: <span>${this._esc(type)}</span><br>
            ${description ? `描述: <span>${this._esc(description.substring(0, 200))}</span><br>` : ''}
            ${atmosphere ? `氛围: <span>${this._esc(atmosphere)}</span><br>` : ''}
            ${parent ? `父地点: <span>${this._esc(this._getLocationName(parent))}</span><br>` : ''}
          </div>
        </div>
      `;
    });

    // ── 动态地点 ──
    const dynEntries = Object.entries(this._dynamicLocations || {});
    if (dynEntries.length > 0) {
      html += '<div class="entity-separator">动态地点</div>';
      dynEntries.forEach(([locId, loc]) => {
        const name = loc.name || locId;
        const type = loc.type || '未知';
        const description = loc.description || '';
        const atmosphere = loc.atmosphere || '';

        html += `
          <div class="loc-card" data-loc-id="${this._esc(locId)}">
            <div class="loc-card__name">📍 ${this._esc(name)}
              <span class="dyn-label dyn-label--location">动态</span>
            </div>
            <div class="loc-card__desc">
              类型: <span>${this._esc(type)}</span><br>
              ${description ? `描述: <span>${this._esc(description.substring(0, 200))}</span><br>` : ''}
              ${atmosphere ? `氛围: <span>${this._esc(atmosphere)}</span><br>` : ''}
            </div>
          </div>
        `;
      });
    }

    this._listContainer.innerHTML = html;

    // 绑定点击事件
    this._listContainer.querySelectorAll('.loc-card').forEach(card => {
      card.addEventListener('click', () => {
        const locId = card.dataset.locId;
        if (locId) {
          const loc = this._locations.find(l => l.id === locId);
          if (loc) this._openLocationModal(loc, 'edit');
        }
      });
    });
  }

  /**
   * 添加地点
   * @param {Object} loc
   */
  addLocation(loc) {
    this._locations.push(loc);
    this.render();
  }

  _renderDefaultLocations() {
    if (!this._listContainer) return;

    this._listContainer.innerHTML = `
      <div class="loc-card--empty">
        暂无地点数据<br>
        <small>导入小说后将自动提取地点信息</small>
      </div>
    `;
  }

  // ═══════════════════════════════════════════════════
  // 地点编辑模态框
  // ═══════════════════════════════════════════════════

  /**
   * 打开地点编辑模态框
   * @param {Object|null} location - 地点数据（新增时为 null）
   * @param {string} mode - 'edit' | 'new'
   */
  _openLocationModal(location, mode) {
    this._editMode = mode;
    this._editingLocId = mode === 'edit' && location ? (location.id || '') : '';

    const modal = document.getElementById('locationEditModal');
    const title = document.getElementById('locationModalTitle');
    const deleteBtn = document.getElementById('btnLocDelete');

    if (!modal) return;

    if (mode === 'new') {
      if (title) title.textContent = '➕ 新增地点';
      if (deleteBtn) deleteBtn.style.display = 'none';
    } else {
      if (title) title.textContent = `✏️ 编辑地点: ${(location && location.name) || ''}`;
      if (deleteBtn) deleteBtn.style.display = 'inline-block';
    }

    this._fillLocationForm(location);
    modal.style.display = 'flex';
  }

  /**
   * 填充地点表单
   * @param {Object|null} location
   */
  _fillLocationForm(location) {
    const setVal = (id, value) => {
      const el = document.getElementById(id);
      if (el) el.value = value || '';
    };

    // ── 填充父地点下拉选项 ──
    this._populateParentSelect(location);

    if (!location) {
      ['locEditName', 'locEditType', 'locEditDesc', 'locEditAtmosphere']
        .forEach(id => setVal(id, ''));
      return;
    }

    setVal('locEditName', location.name || '');
    setVal('locEditType', location.type || '');
    setVal('locEditDesc', location.description || '');
    setVal('locEditAtmosphere', location.atmosphere || '');
  }

  /**
   * 填充父地点下拉选项
   * @param {Object|null} location - 当前编辑的地点（排除自身）
   */
  _populateParentSelect(location) {
    const select = document.getElementById('locEditParent');
    if (!select || select.tagName !== 'SELECT') return;

    const currentParentId = location ? (location.parent || '') : '';
    select.innerHTML = '<option value="">无（顶级地点）</option>';
    this._locations.forEach(loc => {
      // 排除自身（编辑模式下）
      if (this._editMode === 'edit' && loc.id === this._editingLocId) return;
      const selected = (loc.id === currentParentId) ? ' selected' : '';
      select.innerHTML += `<option value="${this._esc(loc.id)}"${selected}>${this._esc(loc.name)}</option>`;
    });
  }

  /**
   * 收集地点表单数据
   * @returns {Object}
   */
  _collectLocationForm() {
    const getVal = (id) => {
      const el = document.getElementById(id);
      return el ? el.value.trim() : '';
    };

    return {
      name: getVal('locEditName'),
      type: getVal('locEditType'),
      parent: getVal('locEditParent'),
      description: getVal('locEditDesc'),
      atmosphere: getVal('locEditAtmosphere'),
    };
  }

  /**
   * 保存地点
   */
  _saveLocation() {
    const data = this._collectLocationForm();

    if (!data.name) {
      alert('请至少填写地点名称');
      return;
    }

    const action = this._editMode === 'new' ? 'create' : 'update';

    App.ws.send('update_canon_entry', {
      entity_type: 'location',
      action: action,
      entry_id: this._editingLocId,
      data: data,
    });

    this._closeLocationModal();
  }

  /**
   * 删除地点
   */
  _deleteLocation() {
    if (!this._editingLocId) return;

    if (!confirm(`确定要删除此地点吗？此操作将从列表中完全移除。`)) return;

    App.ws.send('update_canon_entry', {
      entity_type: 'location',
      action: 'delete',
      entry_id: this._editingLocId,
      data: {},
    });

    this._closeLocationModal();
  }

  /**
   * 关闭地点编辑模态框
   */
  _closeLocationModal() {
    const modal = document.getElementById('locationEditModal');
    if (modal) modal.style.display = 'none';
    this._editingLocId = '';
    this._editMode = 'edit';
  }

  // ═══════════════════════════════════════════════════
  // 事件绑定
  // ═══════════════════════════════════════════════════

  _bindEvents() {
    // ── 新增地点按钮 ──
    const btnAdd = document.getElementById('btnAddLocation');
    if (btnAdd) {
      btnAdd.addEventListener('click', () => {
        this._openLocationModal(null, 'new');
      });
    }

    // ── 地点编辑模态框按钮 ──
    const btnSave = document.getElementById('btnLocSave');
    if (btnSave) {
      btnSave.addEventListener('click', () => this._saveLocation());
    }

    const btnCancel = document.getElementById('btnLocCancel');
    if (btnCancel) {
      btnCancel.addEventListener('click', () => this._closeLocationModal());
    }

    const btnDelete = document.getElementById('btnLocDelete');
    if (btnDelete) {
      btnDelete.addEventListener('click', () => this._deleteLocation());
    }
  }

  // ═══════════════════════════════════════════════════
  // 辅助方法
  // ═══════════════════════════════════════════════════

  /**
   * 根据地点 ID 查找显示名称
   * @param {string} locId
   * @returns {string} 地点名称（找不到时回退显示 ID）
   */
  _getLocationName(locId) {
    const found = this._locations.find(l => l.id === locId);
    return found ? found.name : locId;
  }

  _esc(str) {
    if (!str) return '';
    const div = document.createElement('div');
    div.textContent = String(str);
    return div.innerHTML;
  }
}
