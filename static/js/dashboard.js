/**
 * Dashboard Panel - 仪表盘面板逻辑
 * 功能：从 App.state 读取游戏概览、世界状态
 * 数据源：window.App.state（由 app.js 的 ES Module 更新）
 */

class DashboardPanel {
    constructor() {
        // DOM 元素
        this.roundEl = document.getElementById('dashboardRound');
        this.timeEl = document.getElementById('dashboardTime');
        this.worldLocationEl = document.getElementById('dashboardWorldLocation');
        this.worldEventsEl = document.getElementById('dashboardWorldEvents');

        // 初始化
        this.init();
    }

    /**
     * 初始化
     */
    init() {
        // 立即从 App.state 读取初始数据
        this.syncFromAppState();

        // 面板显示时同步
        const dashboardBtn = document.querySelector('[data-panel="dashboard"]');
        if (dashboardBtn) {
            dashboardBtn.addEventListener('click', () => this.syncFromAppState());
        }

        // 定时刷新（每 3 秒，轻量级，只读本地 state）
        setInterval(() => this.syncFromAppState(), 3000);
    }

    /**
     * 从 window.App.state 同步数据到仪表盘
     * 这是纯前端操作，不调用 REST API
     */
    syncFromAppState() {
        const app = window.App;
        if (!app || !app.state) return;

        const s = app.state;

        // ── 概览卡片 ──
        if (this.roundEl) {
            this.roundEl.textContent = s.beatCount || 0;
        }
        if (this.timeEl) {
            this.timeEl.textContent = s.gameTime || '--:--';
        }

        // ── 世界状态 ──
        if (this.worldLocationEl) {
            this.worldLocationEl.textContent = s.playerLocation || '未知地点';
        }

        // ── 事件日志 ──
        if (this.worldEventsEl && Array.isArray(s.eventLog)) {
            const recentEvents = s.eventLog.slice(-10);
            this.renderEvents(recentEvents.map(e => {
                const text = typeof e === 'string' ? e : (e.text || JSON.stringify(e));
                // 截断过长文本，避免撑破仪表盘
                return text.length > 80 ? text.slice(0, 77) + '...' : text;
            }));
        }
    }

    /**
     * 渲染事件列表
     * @param {string[]} events - 事件文本列表
     */
    renderEvents(events) {
        if (!this.worldEventsEl) return;
        this.worldEventsEl.innerHTML = '';

        if (!events || events.length === 0) {
            const el = document.createElement('div');
            el.className = 'dashboard__event';
            el.textContent = '暂无活跃事件';
            this.worldEventsEl.appendChild(el);
            return;
        }

        events.forEach(text => {
            const el = document.createElement('div');
            el.className = 'dashboard__event';
            el.textContent = text;
            this.worldEventsEl.appendChild(el);
        });
    }
}

// 导出
if (typeof module !== 'undefined' && module.exports) {
    module.exports = DashboardPanel;
} else {
    window.DashboardPanel = DashboardPanel;
}

// DOM 加载完成后初始化
document.addEventListener('DOMContentLoaded', () => {
    window.dashboardPanel = new DashboardPanel();
});
