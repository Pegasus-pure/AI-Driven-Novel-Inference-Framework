/**
 * character-selector.js — 灵魂附生角色选择界面
 *
 * 流程:
 *   1. canon_ready → 显示角色选择覆盖层
 *   2. 展示所有 Canon 角色卡片（含身份 / 性格 / 关系网摘要）
 *   3. 玩家点击卡片选中 → 弹出确认弹窗（不可逆警告）
 *   4. 确认 → 发送 request_game_start_soul → 进入灵魂附生游戏
 *
 * 数据接口（后端一致）:
 *   - 接收: characters[].npc_relationships[], memory_of_protagonist
 *   - 发送: request_game_start_soul { protagonist_id }
 *   - 接收: game_started_soul { protagonist_id, canon, soul_state }
 */

import { App } from '../app.js';

export class CharacterSelector {
  constructor() {
    /** @type {Array} 角色列表 */
    this._characters = [];
    /** @type {string|null} 当前选中的角色 ID */
    this._selectedId = null;
    /** @type {HTMLElement|null} 覆盖层元素 */
    this._overlay = null;
    /** @type {boolean} 是否已初始化 DOM */
    this._domReady = false;
  }

  // ═══════════════════════════════════════════════════
  // 初始化
  // ═══════════════════════════════════════════════════

  init() {
    // 侦听 canon_ready → 主动请求角色列表
    App.on('canon_ready', (_payload) => {
      // 游戏未开始（beatCount === 0）时才请求角色列表
      if (App.state.beatCount === 0) {
        setTimeout(() => {
          App.ws.send('request_character_list', {});
        }, 100);
      }
    });

    // 收到角色列表 → 显示选择界面
    App.on('character_list', (payload) => {
      if (payload && payload.characters) {
        this._characters = payload.characters;
        // ★ 手动模式：条件满足 + 未选过角 → 弹出；已选过 → 不重复弹
        if (App.state.canonSource === 'manual') {
          if (App.state._selectedProtagonistId) return;  // 已选定，跳过
          const chars = App.state.availableCanonChars || [];
          const locs = App.state.availableCanonLocs || [];
          const wr = App.state.worldRules || {};
          const hasWorldRules = Object.values(wr).some(v => v && String(v).trim());
          if (chars.length >= 1 && locs.length >= 1 && hasWorldRules) {
            this._showSelector();
          }
        } else {
          this._showSelector();
        }
      }
    });

    // 游戏启动成功 → 隐藏选择界面
    App.on('game_started_soul', () => {
      this._hideSelector();
    });

    // 已有的开始游戏也有延迟处理
    App.on('game_started', () => {
      this._hideSelector();
    });

    // 切换小说/重置 → 清理状态
    App.on('reset_ui', () => {
      this._teardown();
    });

    console.log('[CharacterSelector] 初始化完成');
  }

  /**
   * 销毁/重置状态
   */
  _teardown() {
    this._characters = [];
    this._selectedId = null;
    this._hideSelector();
  }

  // ═══════════════════════════════════════════════════
  // DOM 构建
  // ═══════════════════════════════════════════════════

  /**
   * 创建选择界面的 DOM 结构（惰性，首次显示时创建）
   */
  _ensureDOM() {
    if (this._domReady) return;

    // ── 覆盖层 ──
    const overlay = document.createElement('div');
    overlay.className = 'char-selector-overlay';
    overlay.id = 'charSelectorOverlay';
    overlay.style.display = 'none';

    overlay.innerHTML = `
      <div class="char-selector">
        <div class="char-select-header">
          <div class="char-select-header__icon">🫀</div>
          <h2 class="char-select-header__title">选择附身目标</h2>
          <p class="char-select-header__subtitle">
            你的灵魂将附生到所选角色体内，与之共生，体验 TA 的命运
          </p>
          <div class="char-select-header__warning">
            ⚠️ 此选择不可逆 — 一旦确认，无法更换角色或小说
          </div>
        </div>

        <div class="char-selector__grid" id="charSelectorList">
          <!-- 角色卡片由 JS 渲染 -->
        </div>

        <div class="char-selector__footer">
          <button class="btn btn--ghost" id="btnSelectorCancel">
            ← 返回小说选择
          </button>
          <div style="flex:1"></div>
          <button class="btn btn--primary" id="btnSelectorConfirm" disabled style="font-size:var(--text-base);padding:var(--space-3) 32px;">
            🫀 附身于此角色
          </button>
        </div>
      </div>

      <!-- 确认弹窗（不可逆警告） -->
      <div class="char-selector__confirm-overlay" id="selectorConfirmOverlay" style="display:none;">
        <div class="char-selector__confirm-dialog">
          <div class="char-selector__confirm-icon">⚠️</div>
          <h3 class="char-selector__confirm-title">确认附身</h3>
          <p class="char-selector__confirm-text">
            你将灵魂附生到 <strong id="confirmCharName">该角色</strong> 体内。
          </p>
          <ul class="char-selector__confirm-list">
            <li>无法更换附身角色</li>
            <li>无法切换其他小说</li>
            <li>只有一个自动存档位</li>
            <li>遗憾请从头开始</li>
          </ul>
          <div class="char-selector__confirm-actions">
            <button class="btn btn--ghost" id="btnConfirmCancel">
              再想想
            </button>
            <button class="btn btn--primary" id="btnConfirmStart" style="background:rgb(248 81 73 / 0.1);border-color:var(--color-crimson,#f85149);color:var(--color-crimson,#f85149);">
              我已明白，开始游戏
            </button>
          </div>
        </div>
      </div>
    `;

    document.body.appendChild(overlay);
    this._overlay = overlay;

    // ── 事件绑定 ──
    document.getElementById('btnSelectorCancel').addEventListener('click', () => {
      this._hideSelector();
      App.emit('return_to_novel_select');
    });

    document.getElementById('btnSelectorConfirm').addEventListener('click', () => {
      this._showConfirmDialog();
    });

    document.getElementById('btnConfirmCancel').addEventListener('click', () => {
      this._hideConfirmDialog();
    });

    document.getElementById('btnConfirmStart').addEventListener('click', () => {
      this._startGame();
    });

    this._domReady = true;
  }

  // ═══════════════════════════════════════════════════
  // 显示 / 隐藏
  // ═══════════════════════════════════════════════════

  _showSelector() {
    this._ensureDOM();
    if (!this._overlay) return;

    this._renderCharacterList();
    this._overlay.style.display = 'flex';
    this._selectedId = null;
    document.getElementById('btnSelectorConfirm').disabled = true;

    // 隐藏欢迎界面（避免重叠）
    const welcomeOverlay = document.getElementById('welcomeOverlay');
    if (welcomeOverlay) welcomeOverlay.classList.add('welcome-overlay--hidden');
  }

  _hideSelector() {
    if (this._overlay) {
      this._overlay.style.display = 'none';
      this._hideConfirmDialog();
    }
  }

  _showConfirmDialog() {
    const overlay = document.getElementById('selectorConfirmOverlay');
    if (!overlay) return;

    const char = this._characters.find(c => c.id === this._selectedId);
    const nameEl = document.getElementById('confirmCharName');
    if (nameEl && char) {
      nameEl.textContent = char.name || '该角色';
    }

    overlay.style.display = 'flex';
  }

  _hideConfirmDialog() {
    const overlay = document.getElementById('selectorConfirmOverlay');
    if (overlay) overlay.style.display = 'none';
  }

  // ═══════════════════════════════════════════════════
  // 角色列表渲染
  // ═══════════════════════════════════════════════════

  _renderCharacterList() {
    const list = document.getElementById('charSelectorList');
    if (!list) return;

    if (this._characters.length === 0) {
      list.innerHTML = `
        <div class="char-selector__empty">
          <p>暂无角色数据</p>
          <p class="char-selector__hint">请先导入小说以查看可选角色</p>
        </div>`;
      return;
    }

    const avatarColors = ['#1a3a5c', '#3a1a2c', '#2a1a3c', '#1a3a3a', '#3a2a1a',
                          '#2a1a3c', '#1a2a3a', '#3a1a2a', '#1a3a2a', '#3a2a2a'];

    let html = '';
    this._characters.forEach((c, index) => {
      const name = c.name || '??';
      const initial = name.charAt(0);
      const role = c.role || '';
      const traits = c.personality_traits || [];
      const appearance = (c.appearance || '').substring(0, 80);
      const location = c.starting_location || '';
      const abilities = c.abilities || c.skills || '';
      const relCount = c.relationship_count || 0;
      const color = avatarColors[index % avatarColors.length];

      html += `
        <div class="char-card-v2" data-char-id="${this._esc(c.id)}">
          <div class="char-card-v2__check">✓</div>
          <div class="char-card-v2__avatar" style="background:${color}">${this._esc(initial)}</div>
          <div class="char-card-v2__body">
            <div class="char-card-v2__name">${this._esc(name)}</div>
            ${role ? `<div class="char-card-v2__role">${this._esc(role)}</div>` : ''}
            <div class="char-card-v2__traits">
              ${traits.map(t => `<span class="char-card-v2__trait">${this._esc(t)}</span>`).join('')}
            </div>
            ${appearance ? `<div class="char-card-v2__detail">${this._esc(appearance)}...</div>` : ''}
            <div class="char-card-v2__footer">
              <span class="char-card-v2__stat">🕸️ <strong>${relCount}</strong> 条关系</span>
              ${location ? `<span class="char-card-v2__stat">📍 <strong>${this._esc(location)}</strong></span>` : ''}
              ${abilities ? `<span class="char-card-v2__stat">⚡ <strong>${this._esc(abilities)}</strong></span>` : ''}
            </div>
          </div>
        </div>
      `;
    });

    list.innerHTML = html;

    // 绑定点击选择事件
    list.querySelectorAll('.char-card-v2').forEach(card => {
      card.addEventListener('click', () => {
        const charId = card.dataset.charId;
        if (!charId) return;

        // 取消其他卡片的选中态
        list.querySelectorAll('.char-card-v2').forEach(c => {
          c.classList.remove('char-card-v2--selected');
        });
        card.classList.add('char-card-v2--selected');

        this._selectedId = charId;
        document.getElementById('btnSelectorConfirm').disabled = false;

        // 滚动卡片到可见区域
        card.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
      });
    });
  }

  // ═══════════════════════════════════════════════════
  // 启动游戏
  // ═══════════════════════════════════════════════════

  _startGame() {
    if (!this._selectedId) return;

    const btn = document.getElementById('btnConfirmStart');
    btn.disabled = true;
    btn.textContent = '已确认...';

    // 隐藏角色选择界面
    this._hideSelector();
    this._hideConfirmDialog();

    // 通知 App：角色已选定，准备进入主界面
    App.emit('character_selected', {
      protagonist_id: this._selectedId,
      protagonist_name: this._characters.find(c => c.id === this._selectedId)?.name || '',
    });
  }

  // ═══════════════════════════════════════════════════
  // 辅助方法
  // ═══════════════════════════════════════════════════

  _esc(str) {
    if (!str) return '';
    const div = document.createElement('div');
    div.textContent = String(str);
    return div.innerHTML;
  }
}
