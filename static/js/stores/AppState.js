/**
 * AppState — 全局游戏状态容器
 *
 * 从 app.js 的 AppState 类中拆出。
 * 管理 29 个游戏状态字段 + FSM 状态机 + 模块实例引用。
 *
 * 用法:
 *   import { state } from './stores/AppState.js';
 *   state.sessionId = 'abc';
 *   state.setPhase('narrative', 'playing');
 */

import { UnifiedFSM } from '../fsm.js';

class AppState {
  constructor() {
    /** @type {Object} 全局游戏状态 */
    this.state = {
      sessionId: '',
      activePanel: 'narrative',
      beatCount: 0,
      deviation: 0.0,
      isTyping: false,
      isConnected: false,
      isChoosing: false,
      gameTime: '初始',
      playerLocation: '',
      charactersState: {},
      eventLog: [],
      actionHints: [],
      canonReady: false,
      novelTitle: '',
      worldRules: {},
      canonMeta: {},
      canonSource: 'initial',
      playerProfile: {},          // 玩家档案（灵魂附生后与主角合并）

      // ── UI 显示模式 ──
      statusDisplayMode: 'bubbles',  // 'bubbles' | 'label'

      // ── 新增：游戏阶段状态 ──
      gamePhase: 'awaiting_start',     // 'awaiting_start' | 'generating' | 'playing'

      // ── 新增：小说选择流程状态 ──
      novelSelectPhase: 'idle',       // 'idle' | 'scanning' | 'list_received' | 'confirming'
                                      // | 'selecting' | 'generating' | 'ready'
      generationTimerId: null,        // 扫描超时定时器 ID
      hasExistingCanon: false,        // 是否存在已生成的 canon
      availableTxtFiles: [],          // novel/ 下的 .txt 列表
      availableCanons: [],            // novel/ 下的 canon_*.json 列表
      isMidGame: false,               // 游戏中禁止切换（beatCount > 0）
      selectedCanonFile: '',          // 当前选中的 canon 文件路径
      _selectedProtagonistId: '',     // 玩家选中的主角 ID
    };

    /** @type {UnifiedFSM} 统一状态机 */
    this.fsm = new UnifiedFSM();

    // 将 isMidGame 改为从 FSM 推导的 getter，不再独立维护
    Object.defineProperty(this.state, 'isMidGame', {
      get: () => this.fsm.phase === 'narrative' && this.state.beatCount > 0,
      configurable: true,
    });

    // 模块实例（初始化后设置）
    this.ws = null;
    this.panels = null;
    this.deviation = null;
    this.input = null;
    this.narrative = null;
    this.characters = null;
    this.worldRules = null;
    this.locations = null;
    this.log = null;
    this.saveUI = null;
    this.choices = null;
    this.pipelineStatus = null;
    this.threads = null;
  }

  /**
   * 设置游戏阶段（双写同步：App.state + App.fsm）
   * @param {'novel_select'|'narrative'|'error'} phase 主阶段
   * @param {string} state 子状态
   * @returns {boolean} 是否转换成功
   */
  setPhase(phase, state) {
    // 同状态直接返回，避免自转换和重复事件
    if (this.fsm.phase === phase && this.fsm.state === state) {
      return true;
    }
    // 先检查 FSM 是否允许此转换
    if (!this.fsm.canTransition(phase, state)) {
      console.warn(
        `[App] setPhase: 非法转换 ${this.fsm.phase}.${this.fsm.state} → ${phase}.${state}，已忽略`,
      );
      return false;
    }
    // 1. 更新旧 App.state 兼容
    switch (phase) {
      case 'narrative':
        this.state.gamePhase = state;
        this.state.novelSelectPhase = 'idle';
        break;
      case 'novel_select':
        this.state.novelSelectPhase = state;
        this.state.gamePhase = 'awaiting_start';
        break;
      case 'error':
        this.state.novelSelectPhase = 'error';
        this.state.gamePhase = 'awaiting_start';
        break;
    }
    // 2. 更新新 FSM
    this.fsm.transition(phase, state);
    return true;
  }
}

export const state = new AppState();
export default AppState;
