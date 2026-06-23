/**
 * EventBus — 独立事件总线
 *
 * 从 app.js 的 AppState 中拆出，用于模块间松耦合通信。
 *
 * 用法:
 *   import { bus } from './stores/EventBus.js';
 *   bus.on('some_event', (data) => { ... });
 *   bus.emit('some_event', { key: 'value' });
 */

class EventBus {
  constructor() {
    /** @type {Object<string,Function[]>} */
    this._listeners = {};
  }

  /**
   * 注册事件监听
   * @param {string} event
   * @param {Function} fn
   */
  on(event, fn) {
    if (!this._listeners[event]) this._listeners[event] = [];
    this._listeners[event].push(fn);
  }

  /**
   * 触发事件
   * @param {string} event
   * @param {*} data
   */
  emit(event, data) {
    const fns = this._listeners[event] || [];
    for (const fn of fns) {
      try { fn(data); } catch (e) {
        console.error(`[EventBus] 事件 "${event}" 出错:`, e);
      }
    }
  }

  /**
   * 移除事件监听
   * @param {string} event
   * @param {Function} fn
   */
  off(event, fn) {
    const fns = this._listeners[event];
    if (!fns) return;
    const idx = fns.indexOf(fn);
    if (idx !== -1) fns.splice(idx, 1);
  }
}

export const bus = new EventBus();
export default EventBus;
