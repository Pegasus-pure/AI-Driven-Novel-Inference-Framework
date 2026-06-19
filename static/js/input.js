/**
 * input.js — 玩家交互处理（选择驱动模式）
 *
 * 输入栏已移除，纯选项驱动。此模块仅保留：
 *   - choice_selected → 发送选择到服务端
 *   - narrative_chunk/narrative_complete → 管理 typing 状态
 *   - agent_status → 更新标题按钮状态
 */

import { App } from './app.js';

export class InputHandler {
  constructor() {
  }

  init() {
    // ── 叙事块到达 → 标记为生成中 ──
    App.on('narrative_chunk', () => {
      this._setTypingState(true);
    });

    // ── 叙事完成 → 标记打字结束 ──
    App.on('narrative_complete', () => {
      this._setTypingState(false);
      if (App.state.gamePhase === 'generating') {
        App.setPhase('narrative', 'playing');
        App.emit('beat_complete', { beatCount: App.state.beatCount });
      }
    });

    // ── choice_selected → 发送选择到服务端 ──
    App.on('choice_selected', (data) => {
      if (!data || !data.choice_id) return;
      if (App.state.gamePhase !== 'playing') return;

      if (!App.ws || !App.ws.isConnected()) {
        console.warn('[Input] WebSocket 未连接, 无法发送选择');
        App.emit('error', { code: 'NOT_CONNECTED', message: '连接已断开，请刷新重试' });
        return;
      }

      App.setPhase('narrative', 'generating');
      App.emit('llm_busy', {});

      if (App.choices) {
        App.choices.clear();
      }

      if (App.ws && App.ws.isConnected()) {
        App.ws.send('player_action', {
          text: data.text || '',
          choice_id: data.choice_id,
        });
        App.emit('player_action_sent', { text: data.text || '' });
      }
    });

    // ── agent_status → 更新标题按钮状态 ──
    App.on('agent_status', (payload) => {
      const btn = document.getElementById('titleNovelBtn');
      if (btn) {
        if (payload && payload.label) {
          btn.disabled = true;
          btn.title = '正在生成中，请稍后再试';
        } else {
          btn.disabled = App.state.isMidGame || (App.state.gamePhase === 'generating');
          btn.title = App.state.isMidGame
            ? '游戏进行中，无法切换小说'
            : (App.state.gamePhase === 'generating' ? '正在生成中，请稍后再试' : '点击切换小说');
        }
      }
    });

    console.log('[Input] 初始化完成');
  }

  // ═══════════════════════════════════════════════════
  // 内部方法
  // ═══════════════════════════════════════════════════

  /**
   * 设置打字状态
   * @param {boolean} isTyping
   */
  _setTypingState(isTyping) {
    App.state.isTyping = isTyping;
  }
}
