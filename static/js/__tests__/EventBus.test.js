/**
 * EventBus 单元测试
 *
 * EventBus 是纯逻辑模块，不依赖 DOM，适合作为前端测试起点。
 */

import { describe, it, expect, vi } from 'vitest';
import EventBus from '../stores/EventBus.js';

// 重置 EventBus 状态（因为它是单例）
function freshBus() {
  const bus = new EventBus();
  return bus;
}

describe('EventBus', () => {
  it('应该注册并触发事件监听器', () => {
    const bus = freshBus();
    const handler = vi.fn();
    const data = { key: 'value' };

    bus.on('test_event', handler);
    bus.emit('test_event', data);

    expect(handler).toHaveBeenCalledTimes(1);
    expect(handler).toHaveBeenCalledWith(data);
  });

  it('未注册事件时 emit 不应报错', () => {
    const bus = freshBus();
    expect(() => {
      bus.emit('nonexistent_event', {});
    }).not.toThrow();
  });

  it('一个事件可以注册多个监听器', () => {
    const bus = freshBus();
    const h1 = vi.fn();
    const h2 = vi.fn();

    bus.on('multi', h1);
    bus.on('multi', h2);
    bus.emit('multi', {});

    expect(h1).toHaveBeenCalledTimes(1);
    expect(h2).toHaveBeenCalledTimes(1);
  });

  it('off 应取消注册事件监听器', () => {
    const bus = freshBus();
    const handler = vi.fn();

    bus.on('test', handler);
    bus.off('test', handler);
    bus.emit('test', {});

    expect(handler).not.toHaveBeenCalled();
  });

  it('off 不存在的监听器不应报错', () => {
    const bus = freshBus();
    const handler = vi.fn();

    expect(() => {
      bus.off('nonexistent', handler);
    }).not.toThrow();
  });

  it('一个监听器的异常不应影响其他监听器', () => {
    const bus = freshBus();
    const error = new Error('test error');
    const h1 = vi.fn(() => { throw error; });
    const h2 = vi.fn();

    bus.on('test', h1);
    bus.on('test', h2);
    bus.emit('test', {});

    expect(h2).toHaveBeenCalledTimes(1);
  });

  it('应支持不同事件类型互不干扰', () => {
    const bus = freshBus();
    const h1 = vi.fn();
    const h2 = vi.fn();

    bus.on('event_a', h1);
    bus.on('event_b', h2);
    bus.emit('event_a', { a: 1 });

    expect(h1).toHaveBeenCalledTimes(1);
    expect(h2).not.toHaveBeenCalled();
  });
});

describe('EventBus — 扩展功能', () => {
  it('off 不存在的 event key 不应报错', () => {
    const bus = freshBus();
    expect(() => bus.off('nope', () => {})).not.toThrow();
  });

  it('同一监听器注册多次应触发多次', () => {
    const bus = freshBus();
    const handler = vi.fn();

    bus.on('dup', handler);
    bus.on('dup', handler);
    bus.emit('dup', {});

    expect(handler).toHaveBeenCalledTimes(2);
  });

  it('多次 emit 应多次触发', () => {
    const bus = freshBus();
    const handler = vi.fn();

    bus.on('multi_emit', handler);
    bus.emit('multi_emit', {});
    bus.emit('multi_emit', {});
    bus.emit('multi_emit', {});

    expect(handler).toHaveBeenCalledTimes(3);
  });
});
