/**
 * fsm.js — 统一分层状态机
 *
 * 整合 gamePhase 和 novelSelectPhase 双状态机为单一分层 FSM。
 *
 * 主阶段:
 *   novel_select — 小说选择流程
 *   narrative    — 叙事循环
 *   error        — 异常状态（可从任意阶段降级）
 *
 * 设计原则:
 *   1. 所有状态转换需经过 transition() 验证
 *   2. 转换时会触发 'fsm:change' 事件
 *   3. 与新老状态表示兼容（双写同步模式）
 *
 * 使用方式:
 *   // 创建实例
 *   const fsm = new UnifiedFSM();
 *
 *   // 转换状态
 *   fsm.transition('narrative', 'awaiting_start');
 *
 *   // 查询状态
 *   fsm.phase;           // 'narrative'
 *   fsm.state;           // 'awaiting_start'
 *   fsm.is('narrative', 'awaiting_start');  // true
 *   fsm.canTransition('narrative', 'awaiting_start');  // boolean
 */

export class UnifiedFSM {
  constructor() {
    /** @type {'novel_select'|'narrative'|'error'} 当前主阶段 */
    this.phase = 'novel_select';

    /** @type {string} 当前子状态 */
    this.state = 'idle';

    /** @type {Function[]} 状态变更监听器 */
    this._listeners = [];
  }

  /**
   * 有效状态转换表
   * phase → state → [toPhase.toState]
   */
  static TRANSITIONS = Object.freeze({
    novel_select: Object.freeze({
      idle: ['novel_select.scanning', 'novel_select.list_received'],
      scanning: ['novel_select.list_received', 'novel_select.error', 'novel_select.idle'],
      list_received: ['novel_select.confirming', 'novel_select.selecting', 'novel_select.idle', 'novel_select.scanning'],
      selecting: ['novel_select.generating', 'novel_select.confirming', 'novel_select.list_received', 'novel_select.idle'],
      confirming: ['novel_select.ready', 'novel_select.idle', 'novel_select.selecting', 'novel_select.generating'],
      generating: ['novel_select.ready', 'novel_select.error', 'novel_select.idle'],
      ready: ['narrative.awaiting_start', 'narrative.generating', 'narrative.playing', 'novel_select.idle'],
      error: ['novel_select.idle', 'novel_select.scanning'],
    }),
    narrative: Object.freeze({
      awaiting_start: ['narrative.generating', 'narrative.playing', 'novel_select.ready'],
      generating: ['narrative.choosing', 'narrative.playing', 'novel_select.ready'],
      choosing: ['narrative.generating', 'novel_select.ready'],
      playing: ['narrative.generating', 'novel_select.ready'],
      error: ['novel_select.idle', 'narrative.awaiting_start'],
    }),
    error: Object.freeze({
      error: ['novel_select.idle', 'narrative.awaiting_start'],
    }),
  });

  /**
   * 执行状态转换
   * @param {'novel_select'|'narrative'|'error'} toPhase 目标主阶段
   * @param {string} toState 目标子状态
   * @returns {boolean} 是否转换成功
   */
  transition(toPhase, toState) {
    const targetKey = `${toPhase}.${toState}`;
    const valid = UnifiedFSM.TRANSITIONS[this.phase]?.[this.state];

    if (!valid || !valid.includes(targetKey)) {
      console.warn(
        `[FSM] 非法转换: ${this.phase}.${this.state} → ${targetKey}`,
        `允许:`, valid,
      );
      return false;
    }

    const prevPhase = this.phase;
    const prevState = this.state;
    this.phase = toPhase;
    this.state = toState;

    this._emit('fsm:change', { prevPhase, prevState, phase: toPhase, state: toState });
    this._emit(`fsm:${toPhase}:${toState}`, { prevPhase, prevState });
    return true;
  }

  /**
   * 检查当前状态是否为指定值
   * @param {string} phase
   * @param {string} state
   * @returns {boolean}
   */
  is(phase, state) {
    return this.phase === phase && this.state === state;
  }

  /**
   * 检查是否可以进行指定转换
   * @param {string} toPhase
   * @param {string} toState
   * @returns {boolean}
   */
  canTransition(toPhase, toState) {
    const targetKey = `${toPhase}.${toState}`;
    const valid = UnifiedFSM.TRANSITIONS[this.phase]?.[this.state];
    return valid ? valid.includes(targetKey) : false;
  }

  /**
   * 注册 FSM 状态变更监听器
   * @param {string} event 事件名 ('fsm:change' | 'fsm:{phase}:{state}')
   * @param {Function} fn
   */
  on(event, fn) {
    this._listeners.push({ event, fn });
  }

  /**
   * 触发事件
   * @param {string} event
   * @param {*} data
   */
  _emit(event, data) {
    for (const { event: e, fn } of this._listeners) {
      if (e === event) {
        try { fn(data); } catch (err) {
          console.error(`[FSM] 事件 "${event}" 出错:`, err);
        }
      }
    }
  }
}
