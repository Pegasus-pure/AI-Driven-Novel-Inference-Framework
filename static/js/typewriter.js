/**
 * typewriter.js — 打字机动画引擎
 *
 * 从 ui-prototype.html 的原生 JS 提取并模块化。
 * 支持逐字渲染、标点停顿、光标闪烁、Esc 跳过。
 */

import { App } from './app.js';

export class Typewriter {
  constructor() {
    /** @type {boolean} 是否正在打字 */
    this._isTyping = false;

    /** @type {boolean} 是否跳过当前动画 */
    this._skipRequested = false;

    /** @type {number|null} 当前 setTimeout ID */
    this._timerId = null;

    /** @type {HTMLElement} 当前正在渲染的行元素 */
    this._currentLineEl = null;
  }

  /**
   * 启动打字机动画
   * @param {Array<{type: string, text: string}>} lines - 行数据
   * @param {HTMLElement} container - 目标容器
   * @param {Function} [onComplete] - 完成后回调
   */
  start(lines, container, onComplete) {
    if (this._isTyping) return;
    this._isTyping = true;
    this._skipRequested = false;

    let lineIndex = 0;
    let charIndex = 0;

    const typeNext = () => {
      // 跳过请求
      if (this._skipRequested) {
        this._finishAll(lines, container, onComplete);
        return;
      }

      if (lineIndex >= lines.length) {
        // 全部完成
        this._finish(onComplete);
        return;
      }

      const line = lines[lineIndex];

      // 创建新行
      if (charIndex === 0) {
        this._currentLineEl = document.createElement('div');
        this._currentLineEl.className = `narrative-line narrative-line--${line.type}`;
        container.appendChild(this._currentLineEl);
      }

      const text = line.text;

      if (charIndex < text.length) {
        // 移除旧光标
        this._removeCursor();

        // 显示已键入字符
        this._currentLineEl.textContent = text.substring(0, charIndex + 1);

        // 添加闪烁光标
        this._addCursor();

        charIndex++;

        // 标点符号延长停顿
        const ch = text[charIndex - 1] || '';
        const isPunctuation = '，。…」—、！？；：'.includes(ch);
        const delay = isPunctuation ? 120 : 35 + Math.random() * 25;

        this._timerId = setTimeout(typeNext, delay);
      } else {
        // 行完成
        this._removeCursor();
        lineIndex++;
        charIndex = 0;
        this._timerId = setTimeout(typeNext, 80);
      }

      // 自动滚动
      container.scrollTop = container.scrollHeight;
    };

    typeNext();
  }

  /**
   * 请求跳过当前动画
   */
  skip() {
    if (this._isTyping) {
      this._skipRequested = true;
    }
  }

  /**
   * 是否正在打字
   * @returns {boolean}
   */
  isTyping() {
    return this._isTyping;
  }

  // ═══════════════════════════════════════════════════
  // 内部方法
  // ═══════════════════════════════════════════════════

  _removeCursor() {
    if (this._currentLineEl) {
      const cursor = this._currentLineEl.querySelector('.cursor-blink');
      if (cursor) cursor.remove();
    }
  }

  _addCursor() {
    if (this._currentLineEl) {
      const cursor = document.createElement('span');
      cursor.className = 'cursor-blink';
      this._currentLineEl.appendChild(cursor);
    }
  }

  _finish(onComplete) {
    this._removeCursor();
    this._isTyping = false;
    this._timerId = null;
    this._currentLineEl = null;
    App.state.isTyping = false;
    if (onComplete) onComplete();
  }

  _finishAll(lines, container, onComplete) {
    // 清除任何进行中的定时器
    if (this._timerId) {
      clearTimeout(this._timerId);
      this._timerId = null;
    }

    // 清除当前行光标
    this._removeCursor();

    // 立即渲染所有剩余行
    for (let i = 0; i < lines.length; i++) {
      // 跳过已部分渲染的行
      const existingLines = container.querySelectorAll('.narrative-line');
      if (i < existingLines.length) {
        // 补全已有行
        const existingEl = existingLines[i];
        existingEl.textContent = lines[i].text;
        const cursor = existingEl.querySelector('.cursor-blink');
        if (cursor) cursor.remove();
      } else {
        // 创建新行
        const el = document.createElement('div');
        el.className = `narrative-line narrative-line--${lines[i].type}`;
        el.textContent = lines[i].text;
        container.appendChild(el);
      }
    }

    container.scrollTop = container.scrollHeight;
    this._finish(onComplete);
    this._skipRequested = false;
  }
}
