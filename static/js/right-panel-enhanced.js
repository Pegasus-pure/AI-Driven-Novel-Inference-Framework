/**
 * Right Panel Enhancement - 右侧面板增强逻辑
 * 功能：增强 Soul Tab（OCEAN 人格雷达图、道德阵营、内心独白）和 Cognition Tab（NPC 认知冲突）
 * API：GET /api/soul/profile、GET /api/npc/dissonance
 */

class RightPanelEnhancement {
    constructor() {
        // DOM 元素（Soul Tab）
        this.soulTabEl = document.getElementById('soulTab');
        this.oceanChartEl = document.getElementById('oceanChart');
        this.moralAlignmentEl = document.getElementById('moralAlignment');
        this.innerMonologueEl = document.getElementById('innerMonologue');
        
        // DOM 元素（Cognition Tab）
        this.cognitionTabEl = document.getElementById('cognitionTab');
        this.dissonanceListEl = document.getElementById('dissonanceList');
        
        // 状态
        this.soulProfile = null;
        this.dissonances = null;
        
        // 初始化
        this.init();
    }
    
    /**
     * 初始化
     */
    async init() {
        // 加载初始数据
        await Promise.all([
            this.loadSoulProfile(),
            this.loadNpcDissonances()
        ]);
        
        // 设置 WebSocket 监听器
        this.setupWebSocketListeners();
        
        // 监听标签页切换
        this.setupTabListeners();
    }
    
    /**
     * 加载灵魂档案
     */
    async loadSoulProfile() {
        try {
            const sessionId = this.getSessionId();
            if (!sessionId) {
                return;
            }
            
            const response = await fetch(`/api/soul/profile?session_id=${sessionId}`);
            if (!response.ok) {
                return;
            }
            const result = await response.json();
            
            if (result.success) {
                this.soulProfile = result.data;
                this.updateSoulUI(this.soulProfile);
            }
        } catch (error) {
            // API 不可用时静默忽略
        }
    }
    
    /**
     * 加载 NPC 认知冲突
     */
    async loadNpcDissonances() {
        try {
            const sessionId = this.getSessionId();
            if (!sessionId) {
                return;
            }
            
            const response = await fetch(`/api/npc/dissonance?session_id=${sessionId}`);
            if (!response.ok) {
                return;
            }
            const result = await response.json();
            
            if (result.success) {
                this.dissonances = result.data;
                this.updateCognitionUI(this.dissonances);
            }
        } catch (error) {
            // API 不可用时静默忽略
        }
    }
    
    /**
     * 设置 WebSocket 监听器
     */
    setupWebSocketListeners() {
        // 监听 WebSocket 消息
        window.addEventListener('ws-message', (event) => {
            const message = event.detail;
            
            if (message.type === 'soul_profile_update') {
                this.soulProfile = message.data;
                this.updateSoulUI(this.soulProfile);
            }
            
            if (message.type === 'npc_dissonance_update') {
                this.dissonances = message.data;
                this.updateCognitionUI(this.dissonances);
            }
        });
    }
    
    /**
     * 设置标签页监听器
     */
    setupTabListeners() {
        // 监听 Soul Tab 显示
        if (this.soulTabEl) {
            const observer = new MutationObserver((mutations) => {
                mutations.forEach((mutation) => {
                    if (mutation.type === 'attributes' && mutation.attributeName === 'style') {
                        const isVisible = this.soulTabEl.style.display !== 'none';
                        if (isVisible) {
                            // Tab 显示时刷新数据
                            this.loadSoulProfile();
                        }
                    }
                });
            });
            
            observer.observe(this.soulTabEl, { attributes: true });
        }
        
        // 监听 Cognition Tab 显示
        if (this.cognitionTabEl) {
            const observer = new MutationObserver((mutations) => {
                mutations.forEach((mutation) => {
                    if (mutation.type === 'attributes' && mutation.attributeName === 'style') {
                        const isVisible = this.cognitionTabEl.style.display !== 'none';
                        if (isVisible) {
                            // Tab 显示时刷新数据
                            this.loadNpcDissonances();
                        }
                    }
                });
            });
            
            observer.observe(this.cognitionTabEl, { attributes: true });
        }
    }
    
    /**
     * 更新 Soul Tab UI
     * @param {Object} profile - 灵魂档案数据
     */
    updateSoulUI(profile) {
        if (!profile) return;
        
        // 更新 OCEAN 人格雷达图
        if (this.oceanChartEl && profile.ocean) {
            this.renderOceanChart(profile.ocean);
        }
        
        // 更新道德阵营
        if (this.moralAlignmentEl && profile.moral_alignment) {
            this.renderMoralAlignment(profile.moral_alignment);
        }
        
        // 更新内心独白
        if (this.innerMonologueEl && profile.inner_monologue) {
            this.innerMonologueEl.textContent = profile.inner_monologue;
        }
    }
    
    /**
     * 渲染 OCEAN 人格雷达图
     * @param {Object} ocean - OCEAN 数据
     */
    renderOceanChart(ocean) {
        // Chart.js 未加载时使用文本替代
        if (!this.oceanChartEl) return;
        
        // 简单文本渲染替代雷达图
        const labels = ['开放性', '尽责性', '外向性', '宜人性', '神经质'];
        const values = [
            ocean.openness,
            ocean.conscientiousness,
            ocean.extraversion,
            ocean.agreeableness,
            ocean.neuroticism
        ];
        
        this.oceanChartEl.innerHTML = labels.map((label, i) => {
            const pct = Math.round((values[i] || 0) * 100);
            return `<div style="display:flex;align-items:center;gap:6px;font-size:0.6rem;margin-bottom:4px;">
                <span style="color:#808098;width:50px;text-align:right;">${label}</span>
                <div style="flex:1;height:7px;background:#16162a;border-radius:3px;overflow:hidden;">
                    <div style="width:${pct}%;height:100%;background:#da77f2;border-radius:3px;"></div>
                </div>
                <span style="color:#a0a0b0;width:24px;">${(values[i] || 0).toFixed(2)}</span>
            </div>`;
        }).join('');
    }
    
    /**
     * 渲染道德阵营指示器
     * @param {string} alignment - 道德阵营
     */
    renderMoralAlignment(alignment) {
        if (!this.moralAlignmentEl) return;
        // 使用文本标签展示道德阵营
        this.moralAlignmentEl.innerHTML = `<span style="color:#ffd43b;font-size:0.6rem;">${alignment || '中立'}</span>`;
    }
    
    /**
     * 更新 Cognition Tab UI
     * @param {Object} data - NPC 认知冲突数据
     */
    updateCognitionUI(data) {
        if (!data || !this.dissonanceListEl) return;
        
        this.dissonanceListEl.innerHTML = '';
        
        if (!data.npc_dissonances || data.npc_dissonances.length === 0) {
            const emptyEl = document.createElement('div');
            emptyEl.className = 'dissonance-empty';
            emptyEl.textContent = '暂无认知冲突';
            this.dissonanceListEl.appendChild(emptyEl);
            return;
        }
        
        data.npc_dissonances.forEach(dissonance => {
            const chip = document.createElement('div');
            chip.className = 'dissonance-chip';
            chip.innerHTML = `
                <div class="dissonance-chip__name">${dissonance.npc_name}</div>
                <div class="dissonance-chip__type">${dissonance.conflict_type}</div>
                <div class="dissonance-chip__level">${Math.round(dissonance.conflict_level * 100)}%</div>
            `;
            
            // 点击查看详情
            chip.addEventListener('click', () => {
                this.showDissonanceDetail(dissonance);
            });
            
            this.dissonanceListEl.appendChild(chip);
        });
    }
    
    /**
     * 显示认知冲突详情
     * @param {Object} dissonance - 认知冲突数据
     */
    showDissonanceDetail(dissonance) {
        // TODO: 显示模态框或侧边栏展示详情
        console.log('[RightPanel] 认知冲突详情：', dissonance);
    }
    
    /**
     * 获取 session_id
     */
    getSessionId() {
        const urlParams = new URLSearchParams(window.location.search);
        let sessionId = urlParams.get('session_id');
        
        if (!sessionId) {
            sessionId = localStorage.getItem('session_id');
        }
        
        return sessionId;
    }
}

// 导出（支持 ES6 模块和全局变量）
if (typeof module !== 'undefined' && module.exports) {
    module.exports = RightPanelEnhancement;
} else {
    window.RightPanelEnhancement = RightPanelEnhancement;
}

// 自动初始化（当 DOM 加载完成后）
document.addEventListener('DOMContentLoaded', () => {
    window.rightPanelEnhancement = new RightPanelEnhancement();
});
