/**
 * settings-ui.js — UI 设置管理器
 *
 * 管理 UI 设置（字体大小 / 背景色）的读写与 localStorage 持久化。
 * 气泡/单行显示模式由 pipeline-status.js 的 _initDisplayToggle() 管理。
 * 字体大小通过 stepper 控件 (-) [数字] (+) 调整，实时生效。
 */

import { App } from './app.js';

const LS_PREFIX = 'rain_';

export class SettingsUI {
  static KEYS = {
    fontSize: LS_PREFIX + 'uiFontSize',
    bgTheme:  LS_PREFIX + 'uiBgTheme',
  };

  static DEFAULTS = {
    fontSize: 15,
    bgTheme:  'dark',
  };

  static FONT_MIN = 12;
  static FONT_MAX = 22;

  /**
   * 初始化：从 localStorage 恢复上次设置 + 绑定 stepper 事件
   */
  static init() {
    this._restoreAll();
    this._bindStepper();
    this._bindBgToggle();
  }

  // ════════════════════════════════════════════
  // 从 localStorage 恢复
  // ════════════════════════════════════════════

  static _restoreAll() {
    const saved = localStorage.getItem(this.KEYS.fontSize);
    const base = saved ? parseInt(saved, 10) || this.DEFAULTS.fontSize : this.DEFAULTS.fontSize;
    const bgTheme = localStorage.getItem(this.KEYS.bgTheme) || this.DEFAULTS.bgTheme;

    this._applyFontSize(base);
    document.documentElement.dataset.bg = bgTheme;
  }

  // ════════════════════════════════════════════
  // 字体 stepper
  // ════════════════════════════════════════════

  static _bindStepper() {
    const input = document.getElementById('fontSizeInput');
    const btnDown = document.getElementById('fontStepDown');
    const btnUp = document.getElementById('fontStepUp');
    if (!input) return;

    // 初始化显示值
    const saved = localStorage.getItem(this.KEYS.fontSize);
    const base = saved ? parseInt(saved, 10) || this.DEFAULTS.fontSize : this.DEFAULTS.fontSize;
    input.value = base;

    // 按钮点击
    if (btnDown) {
      btnDown.addEventListener('click', () => {
        const n = this._getStepperValue();
        if (n > this.FONT_MIN) this._setStepperValue(n - 1);
      });
    }
    if (btnUp) {
      btnUp.addEventListener('click', () => {
        const n = this._getStepperValue();
        if (n < this.FONT_MAX) this._setStepperValue(n + 1);
      });
    }

    // 输入框变更
    input.addEventListener('input', () => {
      const n = this._getStepperValue();
      this._setStepperValue(n);
    });

    // 失焦时校验
    input.addEventListener('blur', () => {
      const n = this._getStepperValue();
      this._setStepperValue(n);
      input.value = this._clampFontSize(n);
    });
  }

  static _getStepperValue() {
    const input = document.getElementById('fontSizeInput');
    if (!input) return this.DEFAULTS.fontSize;
    return parseInt(input.value, 10) || this.DEFAULTS.fontSize;
  }

  static _setStepperValue(n) {
    const clamped = this._clampFontSize(n);
    const input = document.getElementById('fontSizeInput');
    if (input) input.value = clamped;
    this._applyFontSize(clamped);
    localStorage.setItem(this.KEYS.fontSize, clamped);
  }

  static _clampFontSize(n) {
    return Math.max(this.FONT_MIN, Math.min(this.FONT_MAX, n));
  }

  /**
   * 即时应用字体大小：动态设置 CSS 变量，所有元素等比缩放
   * @param {number} base - 基础字号（默认 15）
   */
  static _applyFontSize(base) {
    const root = document.documentElement.style;
    root.setProperty('--font-narrative', base + 'px');
    root.setProperty('--font-ui',       (base - 2) + 'px');
    root.setProperty('--font-title',    (base + 1) + 'px');
    root.setProperty('--font-small',    (base - 3) + 'px');
    root.setProperty('--font-micro',    (base - 4) + 'px');
    root.setProperty('--font-xs',       (base - 2) + 'px');
  }

  // ════════════════════════════════════════════
  // 背景色 toggle
  // ════════════════════════════════════════════

  static _bindBgToggle() {
    const bgToggle = document.getElementById('bgThemeToggle');
    if (!bgToggle) return;

    const savedBg = localStorage.getItem(this.KEYS.bgTheme) || this.DEFAULTS.bgTheme;
    const bgBtns = bgToggle.querySelectorAll('.settings-tag-btn');
    bgBtns.forEach(b => {
      if (b.dataset.theme === savedBg) {
        b.classList.add('settings-tag-btn--active');
      }
      b.addEventListener('click', () => {
        const theme = b.dataset.theme;
        if (!theme) return;
        document.documentElement.dataset.bg = theme;
        localStorage.setItem(this.KEYS.bgTheme, theme);
        bgBtns.forEach(x => x.classList.remove('settings-tag-btn--active'));
        b.classList.add('settings-tag-btn--active');
      });
    });
  }
}
