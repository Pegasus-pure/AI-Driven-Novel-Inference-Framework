/**
 * AppState 单元测试
 *
 * AppState 是纯状态管理模块，无 DOM 依赖。
 */

import { describe, it, expect } from 'vitest';
import AppState from '../stores/AppState.js';

function freshState() {
  return new AppState();
}

describe('AppState — 初始状态', () => {
  it('初始 state 应包含所有必要字段', () => {
    const app = freshState();
    expect(app.state.sessionId).toBe('');
    expect(app.state.activePanel).toBe('narrative');
    expect(app.state.beatCount).toBe(0);
    expect(app.state.deviation).toBe(0.0);
    expect(app.state.isConnected).toBe(false);
    expect(app.state.canonReady).toBe(false);
    expect(app.state.gamePhase).toBe('awaiting_start');
    expect(app.state.novelSelectPhase).toBe('idle');
    expect(app.state.isMidGame).toBe(false);
    expect(app.state.statusDisplayMode).toBe('bubbles');
  });
});

describe('AppState — setPhase', () => {
  it('setPhase 应从 novel_select 正确转换', () => {
    const app = freshState();
    // idle → scanning
    const result = app.setPhase('novel_select', 'scanning');
    expect(result).toBe(true);
    expect(app.state.novelSelectPhase).toBe('scanning');
    expect(app.state.gamePhase).toBe('awaiting_start');
    expect(app.fsm.phase).toBe('novel_select');
    expect(app.fsm.state).toBe('scanning');
  });

  it('setPhase 通过合法路径转换到 narrative', () => {
    const app = freshState();
    // 合法路径: idle → list_received → selecting → generating → ready → awaiting_start
    app.setPhase('novel_select', 'list_received');   // idle → list_received
    app.setPhase('novel_select', 'selecting');        // list_received → selecting
    app.setPhase('novel_select', 'generating');       // selecting → generating
    app.setPhase('novel_select', 'ready');            // generating → ready
    const result = app.setPhase('narrative', 'awaiting_start');  // ready → awaiting_start
    expect(result).toBe(true);
    expect(app.state.gamePhase).toBe('awaiting_start');
    expect(app.state.novelSelectPhase).toBe('idle');
    expect(app.fsm.phase).toBe('narrative');
    expect(app.fsm.state).toBe('awaiting_start');
  });

  it('setPhase 同状态应返回 true 且不触发事件', () => {
    const app = freshState();
    app.setPhase('novel_select', 'scanning');
    const result = app.setPhase('novel_select', 'scanning');
    expect(result).toBe(true);
  });

  it('setPhase 非法转换应返回 false', () => {
    const app = freshState();
    // 'idle' → 'playing' 是非法转换（不在 novel_select 阶段）
    const result = app.setPhase('novel_select', 'playing');
    expect(result).toBe(false);
  });
});

describe('AppState — 状态字段', () => {
  it('canonReady 改变时 isMidGame 应不变', () => {
    const app = freshState();
    app.state.canonReady = true;
    app.state.beatCount = 5;
    app.state.isMidGame = true;
    expect(app.state.canonReady).toBe(true);
    expect(app.state.isMidGame).toBe(true);
  });

  it('generationTimerId 应可设置和清除', () => {
    const app = freshState();
    const timerId = setTimeout(() => {}, 1000);
    app.state.generationTimerId = timerId;
    expect(app.state.generationTimerId).toBe(timerId);
    clearTimeout(timerId);
    app.state.generationTimerId = null;
    expect(app.state.generationTimerId).toBeNull();
  });
});
