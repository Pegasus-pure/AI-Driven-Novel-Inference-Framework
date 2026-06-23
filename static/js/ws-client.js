/**
 * ws-client.js — WebSocket 客户端
 *
 * 功能:
 *  - WebSocket 连接/断开
 *  - 指数退避自动重连（最大 5 次）
 *  - 消息收发 + 自动路由到 App 事件总线
 *  - 小说选择流程协议适配 (canon_list, canon_generation_status)
 */

import { App } from './app.js';

export class WSClient {
  constructor() {
    /** @type {WebSocket|null} */
    this._ws = null;

    /** @type {number} 重连尝试次数 */
    this._reconnectAttempts = 0;

    /** @type {number} 最大重连次数 */
    this._maxReconnect = 5;

    /** @type {number|null} 重连定时器 ID */
    this._reconnectTimer = null;

    /** @type {boolean} 是否主动断开（不触发重连） */
    this._intentionalClose = false;

    /** @type {string} 最后发送的消息（用于重连后重发） */
    this._lastSentAction = '';

    /** @type {string} WebSocket URL */
    this._url = '';
  }

  /**
   * 建立 WebSocket 连接
   */
  connect() {
    // 从 localStorage 恢复 session_id
    if (!App.state.sessionId) {
      const savedSessionId = localStorage.getItem('rain_session_id');
      if (savedSessionId) {
        App.state.sessionId = savedSessionId;
        console.log('[WS] 从 localStorage 恢复 session:', savedSessionId);
      }
    }

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = window.location.host || 'localhost:8000';
    let url = `${protocol}//${host}/ws`;

    // 重连时携带 session_id
    if (App.state.sessionId) {
      url += `?session_id=${App.state.sessionId}`;
    }

    this._url = url;
    this._intentionalClose = false;

    console.log(`[WS] 连接: ${url}`);
    this._ws = new WebSocket(url);

    this._ws.onopen = () => {
      console.log('[WS] 已连接');
      App.state.isConnected = true;
      this._reconnectAttempts = 0;
      this._updateConnectionStatus(true);
      App.emit('ws_connected', {});
    };

    this._ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        this._routeMessage(msg);
      } catch (e) {
        console.error('[WS] 消息解析失败:', e, event.data);
      }
    };

    this._ws.onclose = (event) => {
      console.log(`[WS] 断开: code=${event.code}`);
      App.state.isConnected = false;
      this._updateConnectionStatus(false);

      if (!this._intentionalClose) {
        this._scheduleReconnect();
      }

      App.emit('ws_disconnected', { code: event.code });
    };

    this._ws.onerror = (error) => {
      console.error('[WS] 错误:', error);
    };
  }

  /**
   * 发送消息
   * @param {string} type 消息类型
   * @param {Object} payload 消息负载
   */
  send(type, payload = {}) {
    if (!this._ws || this._ws.readyState !== WebSocket.OPEN) {
      console.warn('[WS] 未连接，无法发送:', type);
      return false;
    }

    const msg = JSON.stringify({ type, payload });
    this._ws.send(msg);

    // 记住最后发送的玩家行动（用于重连后重发）
    if (type === 'player_action') {
      this._lastSentAction = msg;
    }

    return true;
  }

  /**
   * 发送灵魂附生选择（本我/贴合）
   * @param {string} actionType - "authentic" | "conforming"
   * @param {string} beatId - 当前 beat ID
   */
  sendSoulChoice(actionType, beatId) {
    return this.send('player_action', {
      text: '',
      choice_id: '',
      soul_choice: {
        action_type: actionType,
        beat_id: beatId,
      },
    });
  }

  /**
   * 主动断开（不触发重连）
   */
  disconnect() {
    this._intentionalClose = true;
    if (this._reconnectTimer) {
      clearTimeout(this._reconnectTimer);
      this._reconnectTimer = null;
    }
    if (this._ws) {
      this._ws.close();
      this._ws = null;
    }
  }

  /**
   * 是否已连接
   * @returns {boolean}
   */
  isConnected() {
    return this._ws && this._ws.readyState === WebSocket.OPEN;
  }

  // ═══════════════════════════════════════════════════
  // 内部方法
  // ═══════════════════════════════════════════════════

  /**
   * 消息路由：将服务器消息分发到 App 事件总线
   * @param {Object} msg
   */
  _routeMessage(msg) {
    const type = msg.type || '';
    const payload = msg.payload || {};

    // ── 使用 if/else if 链确保单一消息只匹配一个处理分支 ──
    if (type === 'connected' || type === 'reconnected') {
      // 连接确认 → 保存 session_id + 自动请求 canon_list
      App.state.sessionId = payload.session_id || '';
      localStorage.setItem('rain_session_id', App.state.sessionId);
      console.log(`[WS] 会话: ${App.state.sessionId}`);

      // 连接/重连后自动请求扫描 novel 目录
      this.send('request_canon_list', {});
    } else if (type === 'state_sync') {
      this._applyStateSync(payload);
      // 应用 state_sync 后同步 FSM 状态：如果游戏已开始（beat_count > 0）
      // 且 FSM 仍在 novel_select 阶段，自动切换到 narrative
      if (payload.beat_count > 0 && App.fsm.phase === 'novel_select') {
        App.fsm.transition('narrative', 'awaiting_start');
      }
    } else if (type === 'canon_list') {
      // canon_list → 更新 App.state（事件转发交由 emit 统一处理）
      App.state.hasExistingCanon = !!payload.has_existing_canon;
      App.state.availableTxtFiles = payload.txt_files || [];
      App.state.availableCanons = payload.canons || [];
      // ★ 合并 running canons（手动模式创建的小说）到可选列表
      if (payload.running_canons) {
        App.state.availableRunningCanons = payload.running_canons;
      }
    } else if (type === 'deviation_update') {
      App.state.deviation = payload.value || 0;
    } else if (type === 'error') {
      this._handleError(payload);
    }
    // canon_generation_status 等其它消息不需要特殊处理，直接通过 emit 透传

    // ── 统一事件分发：所有消息都通过事件总线转发 ──
    App.emit(type, payload);
    App.emit('message', { type, payload });
  }

  /**
   * 应用服务器发送的状态同步
   * @param {Object} payload
   */
  _applyStateSync(payload) {
    if (payload.beat_count !== undefined) {
      App.state.beatCount = payload.beat_count;
      const beatCountEl = document.getElementById('beatCount');
      if (beatCountEl) beatCountEl.textContent = payload.beat_count;

      // ── isMidGame 由 FSM + beatCount 自动推导，无需手动设置 ──
      const newIsMidGame = payload.beat_count > 0;
      if (App.state.isMidGame !== newIsMidGame) {
        App.emit('mid_game_state_changed', { isMidGame: App.state.isMidGame });
      }
    }
    if (payload.game_time !== undefined) {
      App.state.gameTime = payload.game_time;
    }
    if (payload.player_location !== undefined) {
      App.state.playerLocation = payload.player_location;
    }
    if (payload.characters_state) {
      App.state.charactersState = payload.characters_state;
    }
    if (payload.divergence !== undefined) {
      App.state.deviation = payload.divergence;
    }
    if (payload.event_log) {
      App.state.eventLog = payload.event_log;
    }
    if (payload.player_profile) {
      App.state.playerProfile = payload.player_profile;
    }
    if (payload.canon_ready !== undefined) {
      App.state.canonReady = payload.canon_ready;
    }
    if (payload.novel_title !== undefined && payload.novel_title !== "") {
      const novelTitleBtn = document.getElementById('novelTitleBtn');
      if (novelTitleBtn) {
        novelTitleBtn.textContent = '《' + payload.novel_title + '》';
      }
    }
    if (payload.protagonist_id) {
      App.state._selectedProtagonistId = payload.protagonist_id;
    }
    if (payload.narrative_threads) {
      App.state.narrativeThreads = payload.narrative_threads;
    }

    // ── 根据 beat_count 显示/隐藏欢迎界面 ──
    if (payload.beat_count !== undefined) {
      const overlay = document.getElementById('welcomeOverlay');
      if (overlay) {
        if (payload.beat_count > 0) {
          // 游戏中：隐藏欢迎界面
          overlay.style.display = 'none';
          overlay.classList.add('welcome-overlay--hidden');

          // 激活叙事面板
          if (App.panels) {
            App.panels.switchPanel('narrative');
          }

          // 如果后端正在生成，恢复管线状态条并显示中止按钮
          if (payload.is_generating && App.pipelineStatus) {
            App.pipelineStatus.restoreGenerating(payload.current_agent);
            showAbortButton();
          } else {
            // 不在生成中 → 隐藏中止按钮
            hideAbortButton();
          }
        } else {
          // 未开始：显示欢迎界面
          overlay.style.display = 'flex';
          overlay.classList.remove('welcome-overlay--hidden');
        }
      }
    }
  }

  /**
   * 处理错误消息
   * @param {Object} payload
   */
  _handleError(payload) {
    const code = payload.code || '';
    const message = payload.message || '';

    switch (code) {
      case 'CANNOT_SWITCH_MID_GAME':
        console.warn('[WS] 拒绝切换小说:', message);
        alert('⚠️ ' + message);
        break;

      case 'INVALID_CANON_JSON':
        // 不再使用 alert()，通过 canon_generation_failed 事件让 UI 恢复
        console.warn('[WS] Canon 加载失败:', message);
        App.emit('canon_generation_failed', {
          message: message || 'Canon 文件无效，请检查后重试',
        });
        break;

      case 'CANON_GENERATION_FAILED':
        console.error('[WS] Canon 生成完全失败:', message);
        App.emit('canon_generation_failed', {
          message: message || '世界观数据生成失败',
        });
        break;

      default:
        // 其他错误由 App.on('error') 的处理函数接管
        console.warn('[WS] 未处理的错误:', code, message);
        break;
    }
  }

  /**
   * 指数退避重连
   */
  _scheduleReconnect() {
    if (this._reconnectAttempts >= this._maxReconnect) {
      console.warn(`[WS] 重连失败，已达最大尝试次数 (${this._maxReconnect})`);
      App.emit('ws_reconnect_failed', { attempts: this._reconnectAttempts });
      return;
    }

    const delay = Math.min(1000 * Math.pow(2, this._reconnectAttempts), 30000);
    this._reconnectAttempts++;

    console.log(`[WS] 将在 ${delay}ms 后尝试第 ${this._reconnectAttempts} 次重连...`);

    this._reconnectTimer = setTimeout(() => {
      this.connect();
    }, delay);
  }

  /**
   * 更新连接状态指示器
   * @param {boolean} connected
   */
  _updateConnectionStatus(connected) {
    const el = document.getElementById('connectionStatus');
    if (el) {
      el.textContent = connected ? '●' : '○';
      el.style.color = connected ? '#7ee787' : '#f85149';
      el.title = connected ? 'WebSocket 已连接' : 'WebSocket 已断开';
    }
  }
}
