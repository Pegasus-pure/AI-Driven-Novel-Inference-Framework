/**
 * pipeline-config.js — 管线配置管理器
 *
 * 功能：
 *   (A) 管线节点图可视化（拖拽式节点图，自动连线）
 *   (B) 功能开关（从 /api/config/define 获取说明，从 /api/config/features 获取当前值）
 *
 * 提交策略：
 *   点击「应用配置」后才统一 POST 到后端 + 刷新节点徽章。
 *   单个开关的勾选/取消仅改变 UI，不触发任何网络请求。
 */

import { PipelineGraph } from './pipeline-graph.js';


export class PipelineConfig {
  constructor(opts = {}) {
    this._onStatus = opts.onStatus || (() => {});
    this._graph = new PipelineGraph();
    this._originalFeatures = {}; // 服务器快照

    this._loadFeatures();
  }

  // ── 加载功能开关 ─────────────────────────────────────
  async _loadFeatures() {
    try {
      const [defineResp, featuresResp] = await Promise.all([
        fetch('/api/config/define'),
        fetch('/api/config/features'),
      ]);

      const defineData = await defineResp.json();
      const featuresData = await featuresResp.json();

      if (defineData.success && featuresData.success) {
        // 记录服务器快照，供「恢复默认」使用
        this._originalFeatures = { ...featuresData.features };
        this._renderFeatureToggles(defineData.define, featuresData.features);
        this._bindActionButtons();
      } else {
        this._onStatus('加载配置定义失败', 'err');
      }
    } catch (err) {
      this._onStatus('加载功能开关失败：' + err.message, 'err');
    }
  }

  // ── 渲染功能开关（仅 UI，不绑定服务端写操作）─────
  _renderFeatureToggles(define, features) {
    const container = document.getElementById('pipelineFeaturesList');
    if (!container) return;

    container.innerHTML = '';

    Object.entries(define).forEach(([key, val]) => {
      if (!key.startsWith('features.') || val.section !== 'features') return;

      const featureKey = key.replace('features.', '');
      const isOn = features[featureKey] !== false;

      const item = document.createElement('div');
      item.className = 'pipeline-feature-row';
      item.innerHTML =
        '<div class="pipeline-feature-row__label">' +
          '<input type="checkbox" class="pipeline-feature-row__cb"' +
          ' data-feature="' + featureKey + '" ' + (isOn ? 'checked' : '') + '>' +
          '<span class="pipeline-feature-row__name">' + (val.label || featureKey) + '</span>' +
        '</div>' +
        '<span class="pipeline-feature-row__desc">' + (val.desc || '') + '</span>';

      // 勾选/取消仅改变 UI，不触发写操作
      container.appendChild(item);
    });
  }

  // ── 绑定「应用配置」/「恢复默认」按钮 ──────────
  _bindActionButtons() {
    const btnApply = document.getElementById('btnApplyPipeline');
    const btnReset = document.getElementById('btnResetPipeline');

    if (btnApply) {
      btnApply.addEventListener('click', () => this._applyConfig());
    }
    if (btnReset) {
      btnReset.addEventListener('click', () => this._resetConfig());
    }
  }

  // ── 应用配置：收集全部开关 → POST → 刷新图 ─────
  async _applyConfig() {
    const container = document.getElementById('pipelineFeaturesList');
    if (!container) return;

    // 收集所有 checkbox 当前值
    const features = {};
    container.querySelectorAll('.pipeline-feature-row__cb').forEach(cb => {
      features[cb.dataset.feature] = cb.checked;
    });

    try {
      const resp = await fetch('/api/config/features', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ features }),
      });
      const data = await resp.json();
      if (data.success) {
        this._originalFeatures = { ...features };
        this._onStatus('管线配置已应用', 'ok');
        // 刷新管线图中的节点徽章
        if (this._graph) {
          await this._graph.refreshFeatureStates();
        }
      } else {
        this._onStatus('应用失败: ' + (data.message || '未知错误'), 'err');
      }
    } catch (err) {
      this._onStatus('应用配置失败：' + err.message, 'err');
    }
  }

  // ── 恢复默认：把开关 UI 回退到服务器快照 ──────────
  _resetConfig() {
    const container = document.getElementById('pipelineFeaturesList');
    if (!container) return;

    container.querySelectorAll('.pipeline-feature-row__cb').forEach(cb => {
      const key = cb.dataset.feature;
      cb.checked = this._originalFeatures[key] !== false;
    });

    // 同步管线图徽章到快照状态
    if (this._graph) {
      for (const [key, value] of Object.entries(this._originalFeatures)) {
        this._graph.updateFeatureState(key, value);
      }
    }

    this._onStatus('已恢复为上次应用的配置', 'ok');
  }


  // ── 页面显示时调用（重新定位视口）────────────────
  showPage() {
    if (this._graph) {
      this._graph.show();
    }
  }
}

// ── 自动初始化 ───────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  const pc = new PipelineConfig({
    onStatus: (msg, type) => {
      const el = document.getElementById('settingsStatus');
      if (el) {
        el.textContent = msg;
        el.className = 'settings-status settings-status--' + type;
      }
    },
  });

  window.__pipelineConfig = pc;


// 监听设置页面显示事件，刷新视口定位
document.addEventListener('settings_page_shown', (e) => {
  if (e.detail && e.detail.page === 'pipeline') {
    pc.showPage();
  }
});
});
