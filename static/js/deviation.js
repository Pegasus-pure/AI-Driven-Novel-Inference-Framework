/**
 * deviation.js — 双极偏离度进度条
 *
 * 双极样式 -1.0~1.0，中间 0 点为基准：
 *   负值（回归 Canon）→ 蓝色系
 *   正值（自由创作）→ 橙红色系
 */

import { App } from './app.js';

export class Deviation {
  constructor() {
    /** @type {HTMLElement} 进度条填充 */
    this._fillEl = null;
    /** @type {HTMLElement} 数值显示 */
    this._valueEl = null;
  }

  init() {
    this._fillEl = document.getElementById('deviationFill');
    this._valueEl = document.getElementById('deviationValue');

    // 监听偏离度更新事件
    App.on('deviation_update', (payload) => {
      if (payload && payload.value !== undefined) {
        this.update(payload.value);
      }
    });

    // 叙事完成时也更新偏离度
    App.on('narrative_complete', (payload) => {
      if (payload && payload.deviation !== undefined) {
        this.update(payload.deviation);
      }
    });

    // 初始化为 0
    this.update(0.0);
  }

  /**
   * 更新叙事模式指示器
   * @param {string} mode - 模式标识
   */
  setNarrativeMode(mode) {
    const el = document.getElementById('narrativeModeTag');
    if (!el) return;
    const indicator = document.getElementById('modeIndicator');
    if (indicator) {
      indicator.textContent = this._modeLabel(mode);
    }
    el.style.display = 'inline-flex';
  }

  /**
   * 获取模式中文标签
   * @param {string} mode
   * @returns {string}
   */
  _modeLabel(mode) {
    const labels = {
      exploration: '探索',
      dialogue: '对话',
      conflict: '冲突',
      revelation: '揭示',
      daily_life: '日常',
    };
    return labels[mode] || mode;
  }

  /**
   * 更新偏离度显示（双极）
   * @param {number} value - -1.0 ~ 1.0
   */
  update(value) {
    const clamped = Math.max(-1.0, Math.min(1.0, value));
    const pct = ((clamped + 1) / 2) * 100;  // -1~1 映射到 0~100%

    if (this._fillEl) {
      // 从中间向两侧延伸
      const center = 50;
      const width = Math.abs(clamped) * 50;  // 最大到 50%
      if (clamped >= 0) {
        this._fillEl.style.left = `${center}%`;
        this._fillEl.style.width = `${width}%`;
      } else {
        this._fillEl.style.left = `${center - width}%`;
        this._fillEl.style.width = `${width}%`;
      }
      this._fillEl.style.background = this._getBipolarColor(clamped);
    }

    if (this._valueEl) {
      const prefix = clamped >= 0 ? '+' : '';
      this._valueEl.textContent = `${prefix}${clamped.toFixed(2)}`;
      this._valueEl.style.color = this._getBipolarColor(clamped);
    }
  }

  /**
   * 双极颜色映射
   * @param {number} value - -1.0~1.0
   * @returns {string}
   */
  _getBipolarColor(value) {
    const abs = Math.abs(value);
    if (value < 0) {
      // 负值：蓝色系（遵循 Canon）
      if (abs > 0.6) return 'var(--deviation-negative-high)';
      if (abs > 0.3) return 'var(--deviation-negative-mid)';
      return 'var(--deviation-negative-low)';
    } else {
      // 正值：橙红色系（自由创作）
      if (abs > 0.6) return 'var(--deviation-positive-high)';
      if (abs > 0.3) return 'var(--deviation-positive-mid)';
      return 'var(--deviation-positive-low)';
    }
  }
}
