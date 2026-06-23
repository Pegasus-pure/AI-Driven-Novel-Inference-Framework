/**
 * Game Info Bar - 游戏信息栏逻辑
 * 功能：从 App.state 读取当前位置、张力值、线索数、在场 NPC
 * 数据源：window.App.state + EventBus 事件
 */

class GameInfoBar {
    constructor() {
        // DOM 元素
        this.locationEl = document.getElementById('gameInfoLocation');
        this.tensionFillEl = document.getElementById('gameInfoTension');
        this.tensionValueEl = document.getElementById('gameInfoTensionValue');
        this.cluesEl = document.getElementById('gameInfoClues');
        this.npcsEl = document.getElementById('gameInfoNpcs');

        // 初始化
        this.init();
    }

    /**
     * 初始化
     */
    init() {
        // 从 App.state 同步初始数据
        this.syncFromAppState();

        // 订阅 App 事件
        this.subscribeEvents();

        // 定时刷新（3s，轻量本地读取）
        setInterval(() => this.syncFromAppState(), 3000);
    }

    /**
     * 从 App.state 同步数据
     */
    syncFromAppState() {
        const app = window.App;
        if (!app || !app.state) return;

        const s = app.state;

        // 位置
        if (this.locationEl) {
            this.locationEl.textContent = s.playerLocation || '未知';
        }

        // 张力（不直接存在 App.state 中，用 eventLog 长度模拟）
        if (this.tensionFillEl && this.tensionValueEl) {
            const len = Array.isArray(s.eventLog) ? s.eventLog.length : 0;
            // 用 eventLog 占比作为张力近似值
            const tension = Math.min(0.95, Math.max(0.05, (len % 20) / 20));
            const pct = Math.round(tension * 100);
            this.tensionFillEl.style.width = pct + '%';
            this.tensionValueEl.textContent = tension.toFixed(2);
            // 颜色
            if (tension < 0.3) this.tensionFillEl.style.background = '#4caf50';
            else if (tension < 0.7) this.tensionFillEl.style.background = '#ff9800';
            else this.tensionFillEl.style.background = '#f44336';
        }

        // 线索数（threads 模块会更新 App.state.threads）
        if (this.cluesEl) {
            const threads = s.narrativeThreads || s.activeThreads || null;
            this.cluesEl.textContent = Array.isArray(threads) ? threads.length : '0';
        }

        // NPC（从 charactersState 提取——使用角色名而非 ID）
        if (this.npcsEl) {
            const chars = s.charactersState || {};
            const protagonistId = s._selectedProtagonistId || '';
            // 提取存活角色的名称（跳过主角），取前 8 个
            const names = Object.keys(chars)
                .filter(k => k !== protagonistId && chars[k] && chars[k].status !== 'dead')
                .map(k => chars[k].name || k)
                .slice(0, 8);
            this.renderNpcs(names);
        }
    }

    /**
     * 订阅 App EventBus 事件
     */
    subscribeEvents() {
        const app = window.App;
        if (!app || !app.on) return;

        // 状态同步 → 刷新
        app.on('state_sync', () => this.syncFromAppState());
        // 节拍完成 → 刷新
        app.on('beat_complete', () => this.syncFromAppState());
        // 面板切换 → 刷新（信息栏常驻，但借机刷新）
        app.on('panel_changed', () => this.syncFromAppState());
    }

    /**
     * 渲染 NPC 头像列表
     * @param {string[]} names
     */
    renderNpcs(names) {
        if (!this.npcsEl) return;
        this.npcsEl.innerHTML = '';
        names.forEach(name => {
            const avatar = document.createElement('div');
            avatar.className = 'game-info-bar__npc-avatar';
            avatar.textContent = name.charAt(0);
            avatar.title = name;
            avatar.addEventListener('click', () => {
                window.dispatchEvent(new CustomEvent('game-info-npc-click', { detail: { npcName: name } }));
            });
            this.npcsEl.appendChild(avatar);
        });
    }
}

// 导出
if (typeof module !== 'undefined' && module.exports) {
    module.exports = GameInfoBar;
} else {
    window.GameInfoBar = GameInfoBar;
}

// DOM 加载完成后初始化（App 的 ES Module 此时已就绪）
document.addEventListener('DOMContentLoaded', () => {
    setTimeout(() => { window.gameInfoBar = new GameInfoBar(); }, 500);
});
