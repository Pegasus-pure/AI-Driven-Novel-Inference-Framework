/**
 * characters.js — 角色面板渲染 + 编辑模态框
 *
 * 功能:
 *  - 角色卡片列表（alive/dead 区分）
 *  - 点击角色 → 编辑模态框
 *  - 新增角色 → 空白模态框 + 自动 ID
 *  - 删除角色 → 死亡确认模态框 → 标记死亡
 *  - 右侧边栏「当前在场角色」（保持不变）
 *
 * 注意: 世界观渲染已移出至 world-rules.js（独立 F2 面板）
 */

import { App } from './app.js';

export class CharactersRenderer {
  constructor() {
    /** @type {HTMLElement} 角色面板容器 */
    this._charPanel = null;
    /** @type {HTMLElement} 右侧边栏容器 */
    this._sidePanel = null;
    /** @type {HTMLElement} 角色列表容器 */
    this._charListContainer = null;
    /** @type {Array} 当前 Canon 角色 */
    this._canonCharacters = [];
    /** @type {Object} 动态 NPC */
    this._dynamicNpcs = {};
    /** @type {Array} Canon 地点（用于 ID 转名称） */
    this._locations = [];
    /** @type {string} 当前编辑角色 ID（新增时为 ''） */
    this._editingCharId = '';
    /** @type {string} 编辑模式 'edit' | 'new' */
    this._editMode = 'edit';
    /** @type {string} 待删除角色 ID */
    this._pendingDeathCharId = '';
  }

  init() {
    this._charPanel = document.getElementById('charactersPanelContent');
    this._sidePanel = document.getElementById('charSidePanelContent');
    this._charListContainer = document.getElementById('charactersListContent');

    // 监听状态同步
    App.on('state_sync', (payload) => {
      if (payload && payload.characters_state) {
        this._renderCharacters(payload.characters_state);
      }
    });

    // 叙事完成后刷新在场角色
    App.on('narrative_complete', (payload) => {
      if (payload && payload.characters_present) {
        this._renderSidePanel(payload.characters_present);
      }
    });

    // Canon 就绪（增强版：包含 world_rules, meta, source）
    App.on('canon_ready', (payload) => {
      if (payload && payload.characters) {
        this._canonCharacters = payload.characters || [];
        this._locations = payload.locations || [];  // 存储 locations 用于 ID 转名称
        this._renderCanonCharacters();
      }
    });

    // Canon 条目更新后刷新
    App.on('canon_entries_updated', (payload) => {
      if (payload && payload.success) {
        // 局部刷新——等待下一次 canon_ready 全量刷新
        // 或者乐观更新当前列表
        console.log('[Characters] canon_entries_updated:', payload.message);
      }
    });

    // ── 事件绑定 ──
    this._bindEvents();

    // 监听涌现通知 → 显示行内确认按钮
    App.on('emergence_detected', (payload) => {
      this._renderEmergenceInline(payload);
    });

    // 监听 state_sync 中的 dynamic_npcs
    App.on('state_sync', (payload) => {
      if (payload && payload.dynamic_npcs) {
        this._dynamicNpcs = payload.dynamic_npcs;
        // 如果角色列表已渲染，追加动态 NPC
        if (this._canonCharacters.length > 0) {
          this._appendDynamicNpcs();
        }
      }
    });

    console.log('[Characters] 初始化完成');
  }

  // ═══════════════════════════════════════════════════
  // 渲染
  // ═══════════════════════════════════════════════════

  /**
   * 渲染 Canon 角色卡片列表
   */
  _renderCanonCharacters() {
    if (!this._charListContainer) return;

    const characters = this._canonCharacters || [];

    if (characters.length === 0) {
      this._charListContainer.innerHTML = '<div class="char-card--empty">暂无角色数据 — 导入小说后将自动提取角色信息</div>';
      return;
    }

    let html = '';
    const avatarColors = ['#1a3a5c', '#3a1a2c', '#2a1a3c', '#1a3a3a', '#3a2a1a'];

    characters.forEach((c, index) => {
      const name = c.name || '??';
      const initial = name.charAt(0);
      const role = c.role || '';
      const personality = c.personality || {};
      const traits = (c.key_traits || []).join(' · ');
      const appearance = c.appearance || '';
      const abilities = (c.abilities || []).join(' · ');
      const status = c.status || 'alive';
      const isDead = status === 'dead';
      const color = avatarColors[index % avatarColors.length];

      const cardClass = isDead ? 'char-card char-card--dead' : 'char-card';
      const dataId = c.id || '';

      html += `<div class="${cardClass}" data-char-id="${this._esc(dataId)}">`;
      html += `<div class="char-card__avatar" style="background:${color}">${initial}</div>`;
      html += '<div class="char-card__info">';
      html += `<div class="char-card__name">${this._esc(name)}</div>`;
      html += '<div class="char-card__detail">';
      if (role) html += `身份: <span>${this._esc(role)}</span><br>`;

      // 性格特质
      const personalityTraits = personality.traits || [];
      if (personalityTraits.length > 0) {
        html += `性格: <span>${this._esc(personalityTraits.join(' · '))}</span><br>`;
      }

      if (appearance) {
        html += `外貌: <span>${this._esc(appearance.substring(0, 80))}</span><br>`;
      }
      if (abilities) {
        html += `能力: <span>${this._esc(abilities)}</span><br>`;
      }
      if (traits) {
        html += `关键词: <span>${this._esc(traits)}</span><br>`;
      }

      // 起始地点（ID 转名称显示）
      if (c.starting_location) {
        let locName = c.starting_location;
        if (this._locations) {
          const found = this._locations.find(l => l.id === c.starting_location);
          if (found) locName = found.name;
        }
        html += `起始地点: <span>${this._esc(locName)}</span><br>`;
      }

      // 死亡信息
      if (isDead) {
        html += '<div class="char-card__death-info">';
        html += '💀 已死亡';
        if (c.death_cause) html += ` | 原因: <span>${this._esc(c.death_cause)}</span>`;
        if (c.death_location) html += ` | 地点: <span>${this._esc(c.death_location)}</span>`;
        html += '</div>';
      }

      html += '</div></div></div>';
    });

    this._charListContainer.innerHTML = html;

    // 绑定点击事件
    this._charListContainer.querySelectorAll('.char-card').forEach(card => {
      card.addEventListener('click', () => {
        const charId = card.dataset.charId;
        if (charId) {
          const char = characters.find(c => c.id === charId);
          if (char) this._openCharacterModal(char, 'edit');
        }
      });
    });
  }

  /**
   * 渲染角色档案列表（从 characters_state）
   * @param {Object} charactersState
   */
  _renderCharacters(charactersState) {
    // 此方法保留用于右侧在场的渲染
    // 中栏现在显示 canon 角色，不再由 characters_state 驱动
  }

  /**
   * 渲染右侧「当前在场角色」（保持不变）
   * @param {string[]} presentIds
   */
  _renderSidePanel(presentIds) {
    if (!this._sidePanel) return;

    const charsState = App.state.charactersState || {};

    if (!presentIds || presentIds.length === 0) {
      this._sidePanel.innerHTML = '<div class="char-side-card--empty">当前场景无角色在场</div>';
      return;
    }

    let html = '';
    const avatarColors = ['#1a3a5c', '#3a1a2c', '#2a1a3c', '#1a3a3a', '#3a2a1a'];

    presentIds.forEach((charId, index) => {
      const cs = charsState[charId] || {};
      const name = this._getCharName(charId);
      const initial = name.charAt(0);
      const mood = cs.mood || '中性';
      const goal = cs.goal || cs.motivation || '';
      const attitudeText = this._getAttitude(cs.relation_to_player);
      const attitudeClass = this._getAttitudeClass(cs.relation_to_player);
      const color = avatarColors[index % avatarColors.length];

      html += `
        <div class="char-side-card">
          <div class="char-side-card__header">
            <div class="char-side-card__avatar" style="background:${color}">${initial}</div>
            <div class="char-side-card__name">${this._esc(name)}</div>
          </div>
          <div class="char-side-card__row">
            态度: <span class="char-side-card__attitude char-side-card__attitude--${attitudeClass}">${attitudeText}</span><br>
            状态: <span>${mood}</span><br>
            ${goal ? `动机: <span>${this._esc(goal)}</span>` : ''}
          </div>
        </div>
      `;
    });

    this._sidePanel.innerHTML = html;
  }

  // ═══════════════════════════════════════════════════
  // 角色编辑模态框
  // ═══════════════════════════════════════════════════

  /**
   * 打开角色编辑模态框
   * @param {Object|null} character - 角色数据（新增时为 null）
   * @param {string} mode - 'edit' | 'new'
   */
  _openCharacterModal(character, mode) {
    this._editMode = mode;
    this._editingCharId = mode === 'edit' && character ? (character.id || '') : '';

    const modal = document.getElementById('characterEditModal');
    const title = document.getElementById('characterModalTitle');
    const deleteBtn = document.getElementById('btnCharDelete');

    if (!modal) return;

    if (mode === 'new') {
      if (title) title.textContent = '➕ 新增角色';
      if (deleteBtn) deleteBtn.style.display = 'none';
    } else {
      if (title) title.textContent = `✏️ 编辑角色: ${(character && character.name) || ''}`;
      if (deleteBtn) deleteBtn.style.display = 'inline-block';
    }

    this._fillCharacterForm(character);
    modal.style.display = 'flex';
  }

  /**
   * 填充角色表单
   * @param {Object|null} character
   */
  _fillCharacterForm(character) {
    const setVal = (id, value) => {
      const el = document.getElementById(id);
      if (el) el.value = value || '';
    };

    if (!character) {
      // 空白表单
      const ids = ['charEditName', 'charEditRole', 'charEditAliases', 'charEditTraits',
        'charEditSpeechStyle', 'charEditMotivation', 'charEditFear', 'charEditMoral',
        'charEditAppearance', 'charEditAbilities', 'charEditKeyTraits', 'charEditStartLoc'];
      ids.forEach(id => setVal(id, ''));
      return;
    }

    setVal('charEditName', character.name || '');
    setVal('charEditRole', character.role || '');

    // 数组字段：逗号连接
    const aliases = Array.isArray(character.aliases) ? character.aliases.join(', ') : (character.aliases || '');
    setVal('charEditAliases', aliases);

    const personality = character.personality || {};
    const traits = Array.isArray(personality.traits) ? personality.traits.join(', ') : (personality.traits || '');
    setVal('charEditTraits', traits);
    setVal('charEditSpeechStyle', personality.speech_style || '');
    setVal('charEditMotivation', personality.core_motivation || '');
    setVal('charEditFear', personality.core_fear || '');
    setVal('charEditMoral', personality.moral_alignment || '');

    setVal('charEditAppearance', character.appearance || '');

    const abilities = Array.isArray(character.abilities) ? character.abilities.join(', ') : (character.abilities || '');
    setVal('charEditAbilities', abilities);

    const keyTraits = Array.isArray(character.key_traits) ? character.key_traits.join(', ') : (character.key_traits || '');
    setVal('charEditKeyTraits', keyTraits);

    const startLocId = character.starting_location || '';
    if (this._locations && this._locations.length > 0 && startLocId) {
      const found = this._locations.find(l => l.id === startLocId);
      setVal('charEditStartLoc', found ? found.name : startLocId);
    } else {
      setVal('charEditStartLoc', startLocId);
    }
  }

  /**
   * 收集角色表单数据
   * @returns {Object}
   */
  _collectCharacterForm() {
    const getVal = (id) => {
      const el = document.getElementById(id);
      return el ? el.value.trim() : '';
    };

    const splitTags = (id) => {
      const raw = getVal(id);
      if (!raw) return [];
      return raw.split(',').map(s => s.trim()).filter(s => s);
    };

    return {
      name: getVal('charEditName'),
      role: getVal('charEditRole'),
      aliases: splitTags('charEditAliases'),
      personality: {
        traits: splitTags('charEditTraits'),
        speech_style: getVal('charEditSpeechStyle'),
        core_motivation: getVal('charEditMotivation'),
        core_fear: getVal('charEditFear'),
        moral_alignment: getVal('charEditMoral'),
      },
      appearance: getVal('charEditAppearance'),
      abilities: splitTags('charEditAbilities'),
      key_traits: splitTags('charEditKeyTraits'),
      starting_location: (() => {
        const raw = getVal('charEditStartLoc');
        if (this._locations) {
          const found = this._locations.find(l => l.name === raw);
          if (found) return found.id;
        }
        return raw;
      })(),
    };
  }

  /**
   * 保存角色
   */
  _saveCharacter() {
    const data = this._collectCharacterForm();

    if (!data.name) {
      alert('请至少填写角色姓名');
      return;
    }

    const action = this._editMode === 'new' ? 'create' : 'update';

    App.ws.send('update_canon_entry', {
      entity_type: 'character',
      action: action,
      entry_id: this._editingCharId,
      data: data,
    });

    this._closeCharacterModal();
  }

  /**
   * 关闭角色编辑模态框
   */
  _closeCharacterModal() {
    const modal = document.getElementById('characterEditModal');
    if (modal) modal.style.display = 'none';
    this._editingCharId = '';
    this._editMode = 'edit';
  }

  // ═══════════════════════════════════════════════════
  // 角色删除 = 标记死亡
  // ═══════════════════════════════════════════════════

  /**
   * 点击「标记死亡」按钮 → 打开死亡确认模态框
   */
  _openDeathConfirm() {
    // 关闭角色编辑模态框
    this._closeCharacterModal();

    // 记住要删除的角色 ID
    this._pendingDeathCharId = this._editingCharId;

    // 清空死亡信息表单
    const ids = ['deathLocation', 'deathTime', 'deathCause'];
    ids.forEach(id => {
      const el = document.getElementById(id);
      if (el) el.value = '';
    });

    const modal = document.getElementById('deathConfirmModal');
    if (modal) modal.style.display = 'flex';
  }

  /**
   * 确认死亡
   */
  _confirmDeath() {
    const getVal = (id) => {
      const el = document.getElementById(id);
      return el ? el.value.trim() : '';
    };

    const deathInfo = {
      death_location: getVal('deathLocation'),
      death_time: getVal('deathTime'),
      death_cause: getVal('deathCause'),
    };

    App.ws.send('update_canon_entry', {
      entity_type: 'character',
      action: 'delete',
      entry_id: this._pendingDeathCharId,
      data: deathInfo,
    });

    this._closeDeathConfirm();
  }

  /**
   * 关闭死亡确认模态框
   */
  _closeDeathConfirm() {
    const modal = document.getElementById('deathConfirmModal');
    if (modal) modal.style.display = 'none';
    this._pendingDeathCharId = '';
  }

  // ═══════════════════════════════════════════════════
  // 动态 NPC 渲染 + 涌现实体通知
  // ═══════════════════════════════════════════════════

  /**
   * 在角色列表底部追加动态 NPC
   */
  _appendDynamicNpcs() {
    if (!this._charListContainer) return;
    const npcEntries = Object.entries(this._dynamicNpcs || {});
    if (npcEntries.length === 0) return;

    let html = '<div class="entity-separator">动态 NPC</div>';
    const avatarColors = ['#1a1a3a', '#2a1a3a', '#1a2a3a', '#2a1a2a'];

    npcEntries.forEach(([charId, npc], index) => {
      const name = npc.name || charId;
      const initial = name.charAt(0);
      const role = npc.role || '动态角色';
      const description = (npc.description || npc.appearance || '').substring(0, 80);
      const color = avatarColors[index % avatarColors.length];

      html += `<div class="char-card" data-char-id="${this._esc(charId)}">`;
      html += `<div class="char-card__avatar" style="background:${color}">${initial}</div>`;
      html += '<div class="char-card__info">';
      html += `<div class="char-card__name">${this._esc(name)}`;
      html += `<span class="dyn-label dyn-label--npc">动态 NPC</span>`;
      html += `</div>`;
      html += '<div class="char-card__detail">';
      html += `身份: <span>${this._esc(role)}</span><br>`;
      if (description) {
        html += `描述: <span>${this._esc(description)}</span><br>`;
      }
      if (npc.location) {
        html += `位置: <span>${this._esc(npc.location)}</span><br>`;
      }
      html += '</div></div></div>';
    });

    this._charListContainer.insertAdjacentHTML('beforeend', html);
  }

  /**
   * 渲染涌现实体行内确认通知
   * @param {Object} payload - { name, type, hits, samples, profile }
   */
  _renderEmergenceInline(payload) {
    if (!this._charListContainer || !payload) return;

    const narrativeArea = document.getElementById('narrativeArea');
    if (!narrativeArea) return;

    const container = document.createElement('div');
    container.className = 'narrative-line narrative-line--system';
    container.style.marginBottom = '0';
    container.style.paddingBottom = '4px';

    const name = payload.name || '未知实体';
    const type = payload.type === 'location' ? '地点' : '角色';

    container.innerHTML = `
      ✦ 检测到可能的涌现实体: <strong style="color:var(--text-yellow)">${this._esc(name)}</strong> (${type})
      <div class="emergence-inline">
        <button class="emergence-inline__btn emergence-inline__btn--detail" data-action="detail">🔍 查看详情</button>
        <button class="emergence-inline__btn emergence-inline__btn--confirm" data-action="confirm">✅ 确认纳入</button>
        <button class="emergence-inline__btn emergence-inline__btn--dismiss" data-action="dismiss">❌ 忽略</button>
      </div>
    `;

    narrativeArea.appendChild(container);
    narrativeArea.scrollTop = narrativeArea.scrollHeight;

    // 绑定按钮事件
    container.querySelectorAll('[data-action]').forEach(btn => {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        const action = btn.dataset.action;

        if (action === 'detail') {
          this._openEmergenceModal(payload);
        } else if (action === 'confirm') {
          container.style.opacity = '0.4';
          if (App.ws && App.ws.isConnected()) {
            App.ws.send('confirm_emergence', {
              entity_name: payload.name,
              entity_type: payload.type,
            });
          }
          container.innerHTML = `✦ 涌现实体 <strong style="color:var(--text-green)">${this._esc(name)}</strong> 已确认纳入`;
          container.style.opacity = '1';
        } else if (action === 'dismiss') {
          container.style.opacity = '0.3';
          container.innerHTML = `✦ 涌现实体 ${this._esc(name)} 已被忽略`;
          if (App.ws && App.ws.isConnected()) {
            App.ws.send('dismiss_emergence', {
              entity_name: payload.name,
            });
          }
        }
      });
    });
  }

  /**
   * 打开涌现实体详情弹窗
   * @param {Object} payload
   */
  _openEmergenceModal(payload) {
    const modal = document.getElementById('emergenceModal');
    if (!modal) return;

    const typeEl = document.getElementById('emergenceType');
    const hitsEl = document.getElementById('emergenceHits');
    const samplesEl = document.getElementById('emergenceSamples');
    const profileEl = document.getElementById('emergenceProfileText');
    const confirmBtn = document.getElementById('btnEmergenceConfirm');
    const dismissBtn = document.getElementById('btnEmergenceDismiss');

    if (typeEl) {
      const isLoc = payload.type === 'location';
      typeEl.textContent = isLoc ? '📍 地点' : '👤 角色';
      typeEl.className = `emergence-card__type emergence-card__type--${isLoc ? 'location' : 'npc'}`;
    }
    if (hitsEl) hitsEl.textContent = String(payload.hits || 1);
    if (samplesEl) {
      const samples = payload.samples || [];
      samplesEl.innerHTML = '<div style="font-size:11px;color:#484f58;margin-bottom:6px;">提及原文:</div>' +
        samples.map(s => `<div class="emergence-card__sample">"${this._esc(s)}"</div>`).join('') ||
        '<div class="emergence-card__sample" style="color:#484f58;">(无提及原文)</div>';
    }
    if (profileEl) {
      profileEl.textContent = payload.profile || payload.description || '（自动提取中...）';
    }

    // 绑定确认按钮
    const newConfirm = confirmBtn.cloneNode(true);
    confirmBtn.parentNode.replaceChild(newConfirm, confirmBtn);
    newConfirm.addEventListener('click', () => {
      if (App.ws && App.ws.isConnected()) {
        App.ws.send('confirm_emergence', {
          entity_name: payload.name,
          entity_type: payload.type,
        });
      }
      modal.style.display = 'none';
    });

    // 绑定忽略按钮
    const newDismiss = dismissBtn.cloneNode(true);
    dismissBtn.parentNode.replaceChild(newDismiss, dismissBtn);
    newDismiss.addEventListener('click', () => {
      modal.style.display = 'none';
    });

    modal.style.display = 'flex';
  }

  // ═══════════════════════════════════════════════════
  // 事件绑定
  // ═══════════════════════════════════════════════════

  _bindEvents() {
    // ── 新增角色按钮 ──
    const btnAdd = document.getElementById('btnAddCharacter');
    if (btnAdd) {
      btnAdd.addEventListener('click', () => {
        this._openCharacterModal(null, 'new');
      });
    }

    // ── 角色编辑模态框按钮 ──
    const btnSave = document.getElementById('btnCharSave');
    if (btnSave) {
      btnSave.addEventListener('click', () => this._saveCharacter());
    }

    const btnCancel = document.getElementById('btnCharCancel');
    if (btnCancel) {
      btnCancel.addEventListener('click', () => this._closeCharacterModal());
    }

    const btnDelete = document.getElementById('btnCharDelete');
    if (btnDelete) {
      btnDelete.addEventListener('click', () => this._openDeathConfirm());
    }

    // ── 死亡确认模态框按钮 ──
    const btnDeathConfirm = document.getElementById('btnDeathConfirm');
    if (btnDeathConfirm) {
      btnDeathConfirm.addEventListener('click', () => this._confirmDeath());
    }

    const btnDeathCancel = document.getElementById('btnDeathCancel');
    if (btnDeathCancel) {
      btnDeathCancel.addEventListener('click', () => this._closeDeathConfirm());
    }

    // ── 模态框遮罩关闭 ──
    document.querySelectorAll('.modal-overlay').forEach(overlay => {
      overlay.addEventListener('click', (e) => {
        if (e.target === overlay) {
          overlay.style.display = 'none';
          this._editingCharId = '';
          this._editMode = 'edit';
          this._pendingDeathCharId = '';
        }
      });
    });

    // ── Esc 关闭所有模态框 ──
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') {
        document.querySelectorAll('.modal-overlay').forEach(o => { o.style.display = 'none'; });
        this._editingCharId = '';
        this._editMode = 'edit';
        this._pendingDeathCharId = '';
      }
    });
  }

  // ═══════════════════════════════════════════════════
  // 辅助方法
  // ═══════════════════════════════════════════════════

  /**
   * 获取角色显示名称（三级 fallback）
   * @param {string} charId - 角色 ID
   * @returns {string} 角色名称
   */
  _getCharName(charId) {
    // 1. 从 characters_state 运行时数据获取
    const cs = (App.state.charactersState || {})[charId] || {};
    if (cs.name) return cs.name;
    // 2. 从 canon 静态数据按 ID 查找
    const canon = this._canonCharacters.find(c => c.id === charId);
    if (canon && canon.name) return canon.name;
    // 3. 保底：返回 ID 本身
    return charId;
  }

  _esc(str) {
    if (!str) return '';
    const div = document.createElement('div');
    div.textContent = String(str);
    return div.innerHTML;
  }

  _getAttitude(relation) {
    if (!relation) return '中立';
    if (typeof relation === 'number') {
      if (relation >= 0.7) return '友好';
      if (relation >= 0.3) return '有好感';
      if (relation >= -0.3) return '中立';
      if (relation >= -0.7) return '冷淡';
      return '敌视';
    }
    const s = String(relation);
    if (s.includes('友善') || s.includes('友好')) return '友好';
    if (s.includes('有好感')) return '有好感';
    if (s.includes('中立')) return '中立';
    if (s.includes('冷淡')) return '冷淡';
    if (s.includes('敌视') || s.includes('敌意')) return '敌视';
    if (s.includes('戒备') || s.includes('警惕')) return '警惕';
    return '中立';
  }

  _getAttitudeClass(relation) {
    const attitude = this._getAttitude(relation);
    if (attitude === '友好' || attitude === '有好感') return 'friendly';
    if (attitude === '冷淡' || attitude === '警惕') return 'cautious';
    if (attitude === '敌视') return 'hostile';
    return 'neutral';
  }
}
