/**
 * narrative.js — 叙事区内容渲染
 *
 * 功能:
 *  - 接收 narrative_chunk → 追加到打字机
 *  - 接收 narrative_complete → 完成叙事行渲染
 *  - 自动滚动到底部
 */

import { App } from './app.js';

export class NarrativeRenderer {
  constructor() {
    /** @type {HTMLElement} */
    this._container = null;
    /** @type {string} 累积的当前行文本 */
    this._currentText = '';
    /** @type {HTMLElement|null} 当前行元素 */
    this._currentLineEl = null;
    /** @type {number} 当前行 chunk 计数 */
    this._chunkCount = 0;
  }

  init() {
    this._container = document.getElementById('narrativeArea');

    // 监听流式叙事块
    App.on('narrative_chunk', (payload) => {
      if (payload && payload.text) {
        this._appendChunk(payload.text, payload.is_complete);
      }
    });

    // 叙事完成 → 添加到最终行
    App.on('narrative_complete', (payload) => {
      this._finalizeNarrative(payload);
    });

    // 连续性警告 → 追加到叙事区
    App.on('continuity_warning', (payload) => {
      this._appendContinuityWarning(payload);
    });

    // 反思通知 → 追加到叙事区
    App.on('reflection_note', (payload) => {
      this._appendReflectionNote(payload);
    });

    // 玩家行动 → 立即显示
    App.on('player_action_sent', (payload) => {
      if (payload && payload.text) {
        this._appendPlayerAction(payload.text);
      }
    });

    // 叙事模式更新 → 显示模式切换标记
    App.on('narrative_mode_update', (payload) => {
      if (payload && payload.mode) {
        this._appendNarrativeMode(payload.mode, payload.label);
      }
    });

    // 初始欢迎消息
    this._appendSystemLine('✦ Rain Web 已就绪 · 输入你的行动开始冒险 ✦');

    console.log('[Narrative] 初始化完成');
  }

  // ═══════════════════════════════════════════════════
  // 公开方法
  // ═══════════════════════════════════════════════════

  /**
   * 添加系统消息
   * @param {string} text
   */
  addSystemLine(text) {
    this._appendSystemLine(text);
  }

  /**
   * 添加叙事文本行
   * @param {string} text
   * @param {string} type - narration|dialogue|system|player|ai
   */
  addLine(text, type = 'narration') {
    const line = document.createElement('div');
    line.className = `narrative-line narrative-line--${type}`;
    line.textContent = text;
    this._container.appendChild(line);
    this._scrollToBottom();
  }

  /**
   * 清空叙事区
   */
  clear() {
    if (this._container) {
      this._container.innerHTML = '';
    }
    this._currentText = '';
    this._currentLineEl = null;
    this._chunkCount = 0;
  }

  // ═══════════════════════════════════════════════════
  // 内部方法
  // ═══════════════════════════════════════════════════

  _appendChunk(text, isComplete) {
    if (!this._container) return;

    if (isComplete) {
      // 最后一块：直接追加为完成行
      if (text) {
        const line = document.createElement('div');
        line.className = 'narrative-line narrative-line--narration';
        line.textContent = text;
        this._container.appendChild(line);
      }
      this._scrollToBottom();
      return;
    }

    // 按换行符分割
    const parts = text.split('\n');
    for (let i = 0; i < parts.length; i++) {
      const part = parts[i];
      if (!part && i < parts.length - 1) {
        // 空行 → 换行
        this._currentLineEl = null;
        continue;
      }
      if (!part) continue;

      // 按【角色名】格式分段
      this._renderSegment(part);
    }

    this._scrollToBottom();
  }

  _renderSegment(text) {
    if (!this._container) return;

    // 检测【角色名】格式的对话
    const dialogueMatch = text.match(/^【(.+?)】/);
    if (dialogueMatch) {
      // 对话行
      const line = document.createElement('div');
      line.className = 'narrative-line narrative-line--dialogue';
      line.innerHTML = `<strong>【${dialogueMatch[1]}】</strong>${text.substring(dialogueMatch[0].length)}`;
      this._container.appendChild(line);
      this._currentLineEl = null;
      return;
    }

    // 检测系统消息
    if (text.startsWith('✦') || text.startsWith('⸻') || text.startsWith('⚡')) {
      const line = document.createElement('div');
      line.className = 'narrative-line narrative-line--system';
      line.textContent = text;
      this._container.appendChild(line);
      this._currentLineEl = null;
      return;
    }

    // 普通叙事文本
    if (!this._currentLineEl) {
      this._currentLineEl = document.createElement('div');
      this._currentLineEl.className = 'narrative-line narrative-line--narration';
      this._container.appendChild(this._currentLineEl);
    }
    this._currentLineEl.textContent += text;
  }

  _finalizeNarrative(payload) {
    // 叙事完成，清除当前行引用
    this._currentLineEl = null;
    this._currentText = '';
    this._chunkCount = 0;

    // ── 移除 action_hints 的 💡 提示行显示，改为通过 choices 驱动 ──
    // action_hints 不再显示为系统消息行

    // 如果 payload 中有 choices，通过 App 事件转发（由 app.js 的 narrative_complete 监听处理）
    // 这里不做处理，避免重复

    // 显示方向建议（最高优先级的一条）
    if (payload && payload.suggestions && payload.suggestions.length > 0) {
      const topSuggestion = payload.suggestions[0];
      this._appendSystemLine(`💡 ${topSuggestion.direction} — ${topSuggestion.reason}`);
    }

    // 显示结尾钩子
    if (payload && payload.ending_hook) {
      const hookLine = document.createElement('div');
      hookLine.className = 'narrative-line narrative-line--ending_hook';
      hookLine.textContent = payload.ending_hook;
      this._container.appendChild(hookLine);
    }

    // 更新节拍计数
    if (payload && payload.beat_id) {
      const beatNum = payload.beat_id.replace('beat_', '');
      document.getElementById('beatCount').textContent = beatNum;
    }

    this._scrollToBottom();
  }

  _appendPlayerAction(text) {
    if (!this._container) return;
    const line = document.createElement('div');
    line.className = 'narrative-line narrative-line--player';
    line.textContent = `> ${text}`;
    this._container.appendChild(line);
    this._scrollToBottom();
  }

  _appendSystemLine(text) {
    if (!this._container) return;
    const line = document.createElement('div');
    line.className = 'narrative-line narrative-line--system';
    line.textContent = text;
    this._container.appendChild(line);
    this._scrollToBottom();
  }

  /**
   * 追加连续性检查警告
   * @param {Object} payload - { issue, description, rewrite_count }
   */
  _appendContinuityWarning(payload) {
    if (!this._container || !payload) return;

    const description = payload.description || '发现叙事矛盾';
    const rewriteCount = payload.rewrite_count || 0;

    if (rewriteCount > 0) {
      const line = document.createElement('div');
      line.className = 'narrative-line narrative-line--rewrite';
      line.textContent = `⚡ 重写 #${rewriteCount}: ${description}`;
      this._container.appendChild(line);
    } else {
      const line = document.createElement('div');
      line.className = 'narrative-line narrative-line--continuity';
      line.textContent = `⚡ 连续性检查: ${description}`;
      this._container.appendChild(line);
    }

    this._scrollToBottom();
  }

  /**
   * 追加角色反思通知
   * @param {Object} payload - { char_id, char_name, emotion_shift }
   */
  _appendReflectionNote(payload) {
    if (!this._container || !payload) return;

    const charName = payload.char_name || payload.char_id || '未知角色';
    const emotionShift = payload.emotion_shift || {};

    if (emotionShift.from && emotionShift.to) {
      const line = document.createElement('div');
      line.className = 'narrative-line narrative-line--reflection';
      line.textContent = `💭 角色反思: ${charName}的情绪从"${emotionShift.from}"变为"${emotionShift.to}"`;
      this._container.appendChild(line);
    } else if (payload.summary) {
      const line = document.createElement('div');
      line.className = 'narrative-line narrative-line--reflection';
      line.textContent = `💭 ${payload.summary}`;
      this._container.appendChild(line);
    }

    this._scrollToBottom();
  }

  _appendNarrativeMode(mode, label) {
    if (!this._container) return;
    const line = document.createElement('div');
    line.className = 'narrative-line narrative-line--mode';
    line.textContent = `⸻ 叙事模式：${label || mode} ⸻`;
    this._container.appendChild(line);
    this._scrollToBottom();
  }

  _scrollToBottom() {
    if (this._container) {
      this._container.scrollTop = this._container.scrollHeight;
    }
  }
}
