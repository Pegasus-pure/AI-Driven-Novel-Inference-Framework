/**
 * npc-cognition-panel.js — NPC 认知状态指示器
 *
 * 在右侧边栏的角色卡片下方扩展显示：
 *   - 认知冲突阶段指示（normal / subtle / questioning / confrontational / adapted）
 *   - dissonance 进度条
 *   - NPC 对主角的态度变化提示
 *
 * 数据源: soul_state_update → npc_dissonance
 */

import { App } from '../app.js';

export class NPCCognitionPanel {
  constructor() {
    /** @type {boolean} 是否有 dissonance 数据 */
    this._hasData = false;
  }

  init() {
    // 监听 soul_state_update → 更新认知状态
    App.on('soul_state_update', (data) => {
      if (data && data.npc_dissonance) {
        this._updateDissonance(data.npc_dissonance);
      }
    });

    // 监听 state_sync → 角色在场列表更新后追加认知状态
    App.on('state_sync', () => {
      // characters.js 负责渲染在场角色列表
      // 我们只需在有 dissonance 数据时追加指示器
    });

    console.log('[NPCCognitionPanel] 初始化完成');
  }

  /**
   * 更新认知冲突指示
   * @param {Object} dissonanceMap - { char_id: {phase, dissonance_score, ...} }
   */
  _updateDissonance(dissonanceMap) {
    if (!dissonanceMap || Object.keys(dissonanceMap).length === 0) return;

    this._hasData = true;

    // 遍历每个 NPC 的 dissonance 状态，注入到对应的角色卡片下方
    for (const [charId, state] of Object.entries(dissonanceMap)) {
      this._injectDissonance(charId, state);
    }
  }

  /**
   * 在角色卡片下方插入认知冲突指示器
   */
  _injectDissonance(charId, state) {
    // 查找侧边栏中对应的角色卡片（通过 data-char-id）
    const sideCards = document.querySelectorAll('.char-side-card');
    let targetCard = null;

    for (const card of sideCards) {
      // 卡片上没有直接 data-char-id，但从内容中可以推断
      // 更可靠的方式是通过 characters.js 渲染时添加 data 属性
      // 这里作为备用方案，通过查找卡片内的名称匹配
      const dataAttr = card.dataset.charId;
      if (dataAttr === charId) {
        targetCard = card;
        break;
      }
    }

    if (!targetCard) return;

    // 检查是否已有认知指示器
    let indicator = targetCard.querySelector('.cognition-indicator');
    if (!indicator) {
      indicator = document.createElement('div');
      indicator.className = 'cognition-indicator';
      targetCard.appendChild(indicator);
    }

    const phase = state.phase || 'normal';
    const score = state.dissonance_score != null ? state.dissonance_score : 0;
    const affinity = state.affinity != null ? state.affinity : 0;

    const phaseLabels = {
      'normal': '正常',
      'subtle': '微妙',
      'questioning': '质疑',
      'confrontational': '对峙',
      'adapted': '适应',
    };

    const phaseColors = {
      'normal': 'var(--text-gray)',
      'subtle': 'var(--text-yellow)',
      'questioning': 'var(--text-orange)',
      'confrontational': 'var(--text-red)',
      'adapted': 'var(--text-green)',
    };

    const phaseLabel = phaseLabels[phase] || phase;
    const phaseColor = phaseColors[phase] || 'var(--text-gray)';
    const barColor = score > 0.6 ? 'var(--text-red)' : (score > 0.3 ? 'var(--text-yellow)' : 'var(--text-green)');

    indicator.innerHTML = `
      <div class="cognition-indicator__phase" style="color:${phaseColor}">
        ● ${phaseLabel}
      </div>
      <div class="cognition-indicator__bar">
        <div class="cognition-indicator__fill" style="width:${Math.min(score * 100, 100)}%;background:${barColor}"></div>
      </div>
      <div class="cognition-indicator__affinity">
        亲近: ${this._formatAffinity(affinity)}
      </div>
    `;
  }

  _formatAffinity(value) {
    if (value >= 0.7) return '友好 ❤️';
    if (value >= 0.3) return '有好感 💚';
    if (value >= -0.3) return '中立 💭';
    if (value >= -0.7) return '冷淡 💔';
    return '敌视 ❌';
  }
}
