/**
 * app.js — Rain Web 前端入口（精简版）
 *
 * 全局应用状态 + 事件总线 + 初始化 + 模块导入编排
 * + 小说选择流程状态机
 *
 * 架构: 单例 App 模式 — 所有模块通过 App 共享状态，
 *       通过 bus.on/bus.emit 松耦合通信。
 *       AppState 和 EventBus 已拆至 stores/ 目录。
 *
 * 面板快捷键:
 *   F1 → 剧情    F2 → 世界观    F3 → 角色    F4 → 地点
 *   F5 → 日志    F6 → 存档      F7 → 设置
 */

// ═══════════════════════════════════════════════════════
// 导入
// ═══════════════════════════════════════════════════════

import { WSClient } from './ws-client.js';
import { PanelManager } from './panels.js';
import { Deviation } from './deviation.js';
import { InputHandler } from './input.js';
import { NarrativeRenderer } from './narrative.js';
import { CharactersRenderer } from './characters.js';
import { WorldRulesRenderer } from './world-rules.js';
import { LocationsRenderer } from './locations.js';
import { LogRenderer } from './log-ui.js';
import { SaveUIRenderer } from './save-ui.js';
import { ChoicePanel } from './choices.js';
import { PipelineStatusBar } from './pipeline-status.js';
import { ThreadsRenderer } from './threads.js';
import { RelationNetwork } from './relation-network.js';
import { CharacterSelector } from './soul/character-selector.js';
import { SoulPanel } from './soul/soul-panel.js';
import { NPCCognitionPanel } from './soul/npc-cognition-panel.js';

// 灵魂附生模块（按需动态 import）
let SoulChoiceRenderer;
import { SettingsUI } from './settings-ui.js';
import { state } from './stores/AppState.js';
import { bus } from './stores/EventBus.js';

// ═══════════════════════════════════════════════════════
// 全局单例 App — 向后兼容 facade
// ═══════════════════════════════════════════════════════

/**
 * App 是 state + bus + 模块实例的合并单例。
 * 旧模块 import { App } from './app.js' 无需改动。
 */
const App = {
  // ── 状态委托 ──
  get state() { return state.state; },
  get fsm() { return state.fsm; },
  setPhase: (phase, s) => state.setPhase(phase, s),

  // ── 模块实例（由 init() 填充） ──
  ws: null, panels: null, deviation: null, input: null,
  narrative: null, characters: null, worldRules: null,
  locations: null, log: null, saveUI: null, choices: null,
  pipelineStatus: null, threads: null, relationNetwork: null, charSelector: null,
  soulPanel: null, npcCognition: null,

  // ── 事件总线委托 ──
  on: (event, fn) => bus.on(event, fn),
  emit: (event, data) => bus.emit(event, data),
  off: (event, fn) => bus.off(event, fn),
  emit: (event, data) => bus.emit(event, data),
};

export { App };

// ★★★ 暴露全局 App 供非模块脚本访问（dashboard.js, game-info-bar.js 等）★★★
window.App = App;

// ═══════════════════════════════════════════════════════
// 初始化
// ═══════════════════════════════════════════════════════

function init() {
  console.log('[App] 小说模拟器 初始化...');

  // 创建模块实例
  App.ws = new WSClient();
  App.panels = new PanelManager();
  App.deviation = new Deviation();
  App.input = new InputHandler();
  App.narrative = new NarrativeRenderer();
  App.characters = new CharactersRenderer();
  App.worldRules = new WorldRulesRenderer();
  App.locations = new LocationsRenderer();
  App.log = new LogRenderer();
  App.saveUI = new SaveUIRenderer();
  App.choices = new ChoicePanel();
  App.pipelineStatus = new PipelineStatusBar();
  App.threads = new ThreadsRenderer();
  App.relationNetwork = new RelationNetwork();
  App.charSelector = new CharacterSelector();
  App.soulPanel = new SoulPanel();
  App.npcCognition = new NPCCognitionPanel();

  // 初始化各模块
  App.panels.init();
  App.deviation.init();
  App.input.init();
  App.narrative.init();
  App.characters.init();
  App.worldRules.init();
  App.locations.init();
  App.log.init();
  App.saveUI.init();
  App.choices.init();
  App.pipelineStatus.init();
  App.charSelector.init();
  App.soulPanel.init();
  App.npcCognition.init();

  // ── agent_status → 驱动管线进度条 + 气泡 ──
  App.on('agent_status', (payload) => {
    // 生成开始时显示中止按钮
    if (payload && payload.agent) {
      App.pipelineStatus.activate(payload.agent);
      showAbortButton();
    } else {
      App.pipelineStatus.hide();
    }
  });

  App.threads.init();

  // 初始化关系网（惰性，等待数据触发）
  App.relationNetwork.init();

  // 连接 WebSocket
  App.ws.connect();

  // 初始化设置面板
  initSettingsPanel();

  // 初始化 UI 设置（从 localStorage 恢复 + 绑定 toggle）
  SettingsUI.init();

  // 初始化欢迎界面
  initWelcomeOverlay();

  // 初始化刷新防护（拦截 F5/Ctrl+R，发送中止）
  _initRefreshGuard();

  // ── "开始冒险"按钮（支持首次启动 + 中止后继续）──
  const startBtn = document.getElementById('startGameBtn');
  if (startBtn) {
    startBtn.addEventListener('click', () => {
      startBtn.disabled = true;
      if (App.state.beatCount > 0) {
        // ★ 游戏已开始 → 从中止处继续生成
        startBtn.textContent = '继续中...';
        App.setPhase('narrative', 'generating');
        App.emit('llm_busy', {});
        App.ws.send('player_action', { text: '' });
      } else {
        // 首次启动灵魂附生
        startBtn.textContent = '启动中...';
        App.ws.send('request_game_start_soul', {
          protagonist_id: App.state._selectedProtagonistId || '',
        });
      }
    });
  }

  // 监听配置信息（预填设置面板）
  App.on('config_info', (payload) => {
    if (payload && payload.providers) {
      for (const [tier, cfg] of Object.entries(payload.providers)) {
        const card = document.querySelector(`.settings-tier-card[data-tier="${tier}"]`);
        if (!card) continue;

        // 1. 同步提供者类型
        const providerType = cfg.type || 'deepseek';
        card.dataset.providerType = providerType;
        const sel = document.querySelector(`.settings-provider-select[data-tier="${tier}"]`);
        if (sel && [...sel.options].some(o => o.value === providerType)) {
          sel.value = providerType;
        }

        // 2. 填充各字段
        if (providerType === 'deepseek') {
          // DeepSeek: 模型下拉，API 密钥
          const modelSel = document.querySelector(`.settings-model-deepseek[data-tier="${tier}"] select`);
          if (modelSel && cfg.model) {
            if ([...modelSel.options].some(o => o.value === cfg.model)) {
              modelSel.value = cfg.model;
            }
          }
          if (cfg.api_key != null) {
            const el = document.querySelector(`[data-field="${tier}-api_key"]`);
            if (el) el.value = cfg.api_key;
          }
        } else {
          // Ollama: 端点输入，模型输入
          if (cfg.endpoint) {
            const el = document.querySelector(`[data-field="${tier}-endpoint"]`);
            if (el) el.value = cfg.endpoint;
          }
          if (cfg.model) {
            const el = document.querySelector(`[data-field="${tier}-model"]`);
            if (el) el.value = cfg.model;
          }
        }

        // 3. 通用字段
        if (cfg.temperature != null) {
          const slider = document.querySelector(`[data-field="${tier}-temperature"]`);
          if (slider) {
            slider.value = cfg.temperature;
            const valEl = document.getElementById(tier + '-temp-val');
            if (valEl) valEl.textContent = parseFloat(cfg.temperature).toFixed(1);
          }
        }
        if (cfg.max_tokens) {
          const el = document.querySelector(`[data-field="${tier}-max_tokens"]`);
          if (el) el.value = cfg.max_tokens;
        }
      }
    }
    // 更新可用模型列表（模型提示已集成在卡片 tag 中）
  });

  // ── 新增：canon_list 事件 → 决策分支 ──
  App.on('canon_list', handleCanonList);

  // ── 新增：mid_game_state_changed → 更新标题按钮 ──
  App.on('mid_game_state_changed', (payload) => {
    updateTitleButton();
  });

  // ── load_complete: 读档后恢复叙事区和游戏状态 ──
  App.on('load_complete', (payload) => {
    const ws = payload.world_state;
    if (!ws) {
      console.warn('[App] load_complete 缺少 world_state');
      return;
    }

    // 1. 完整同步 App.state（与 _applyStateSync 对齐，确保 dashboard/game-info-bar 可用）
    App.state.beatCount = ws.beat_count || 0;
    App.state.gameTime = ws.game_time || '';
    // ★ 位置：如果是 location ID 格式(loc_XXX)，从 characters_state 推断主角位置
    let playerLoc = ws.player_location || '';
    if (playerLoc && /^loc_\d+[a-z]?$/i.test(playerLoc)) {
        const charsState = ws.characters_state || {};
        const pid = ws.protagonist_id || App.state._selectedProtagonistId || '';
        if (pid && charsState[pid] && charsState[pid].location) {
            playerLoc = charsState[pid].location;
        }
    }
    App.state.playerLocation = playerLoc;
    App.state.deviation = ws.divergence || 0;
    App.state.eventLog = ws.event_log || [];
    App.state.charactersState = ws.characters_state || {};
    App.state.narrativeThreads = ws.narrative_threads || {};
    App.state.playerProfile = ws.player_profile || {};
    if (ws.session_id) App.state.sessionId = ws.session_id;
    if (ws.protagonist_id) App.state._selectedProtagonistId = ws.protagonist_id;

    // 更新标题栏
    document.getElementById('beatCount').textContent = App.state.beatCount;
    const titleEl = document.getElementById('titleNovel');
    const novelTitle = ws.novel_title || App.state.novelTitle || '';
    if (titleEl && novelTitle) {
      App.state.novelTitle = novelTitle;
      titleEl.textContent = '《' + novelTitle.replace(/【.*?】/g, '') + '》';
    }

    // 2. 恢复叙事区：仅渲染最后一条 event_log（全文）
    const eventLog = App.state.eventLog;
    if (App.narrative) {
      App.narrative.clear();
      App.narrative.addSystemLine('\u2728 存档已恢复 · 节拍 ' + App.state.beatCount + ' · ' + ws.game_time);
      const lastEntry = eventLog[eventLog.length - 1];
      if (lastEntry && lastEntry.text) {
        App.narrative.addLine(lastEntry.text, lastEntry.type === 'dialogue' ? 'dialogue' : 'narration');
      }
    }

    // 3. 激活叙事面板
    hideWelcome();
    if (App.panels) {
      App.panels.switchPanel('narrative');
    }

    // 4. 设置 running 状态
    App.state.canonReady = true;
    App.state.isChoosing = false;
    App.setPhase('narrative', 'playing');

    // 5. 显示初始选择（灵魂模式）
    const soulDefaults = {
      authentic: [
        { id: 'auth_1', text: '继续冒险', hint: '推进剧情发展', next_scene_hint: '继续冒险' },
        { id: 'auth_2', text: '主动探索周围', hint: '环顾当前场景', next_scene_hint: '探索周围' },
      ],
      conforming: [
        { id: 'conf_1', text: '保持原主形象', hint: '维持当前身份', next_scene_hint: '保持形象' },
        { id: 'conf_2', text: '观察情况', hint: '先不贸然行动', next_scene_hint: '观察情况' },
      ],
    };
    App.emit('choices_ready', soulDefaults);

    // 6. 更新标题按钮
    updateTitleButton();
  });

  // ── canon_ready 增强：存储 world_rules、meta、source ──
  App.on('canon_ready', (payload) => {
    App.state.canonReady = true;
    App.state.novelTitle = payload.novel_title || '';
    App.state.worldRules = payload.world_rules || {};
    App.state.canonMeta = payload.meta || {};
    App.state.canonSource = payload.source || 'initial';
    // ★ 存储角色/地点列表供手动模式验证
    App.state.availableCanonChars = payload.characters || [];
    App.state.availableCanonLocs = payload.locations || [];
    const titleEl = document.getElementById('titleNovel');
    if (titleEl) {
      if (payload.novel_title) {
        titleEl.textContent = '《' + payload.novel_title.replace(/【.*?】/g, '') + '》';
      } else {
        titleEl.textContent = '请选择小说';
      }
    }
    // ★ 手动模式：已选定角色后不再重复隐藏欢迎界面和切换面板（避免闪烁）
    if (App.state.canonSource !== 'manual' || !App.state._selectedProtagonistId) {
      hideWelcome();
      if (App.panels) {
        App.panels.switchPanel('narrative');
      }
    }
    // 设置游戏阶段为灵魂附生等待中
    App.setPhase('novel_select', 'ready');
    // 角色选择器已自动监听 canon_ready → 请求角色列表 → 显示选择界面
    // 更新标题按钮
    updateTitleButton();
  });

  // ── T04/T05: 叙事模式更新 → 通知 deviation 和 narrative ──
  App.on('narrative_mode_update', (payload) => {
    if (payload && payload.mode) {
      App.deviation.setNarrativeMode(payload.mode);
    }
  });

  // ── Choice System: narrative_complete → 转发灵魂选择 ──
  App.on('narrative_complete', (payload) => {
    hideAbortButton();

    // 灵魂附生模式：显示本我/贴合选择
    if (payload && payload.needs_soul_choice) {
      App.state.isChoosing = true;
      if (App.choices && App.choices.renderSoulChoice) {
        // 存储 action choices 供二级渲染使用
        const sd = payload.soul_decision || {};
        App.choices._currentActionChoices = {
          authentic: sd.authentic || [],
          conforming: sd.conforming || [],
        };
        App.choices._currentBeatId = payload.beat_id || '';
        App.choices.renderSoulChoice(payload.beat_id || '');
      }
      // 更新双魂面板
      if (payload.soul_state) {
        App.emit('soul_state_update', payload.soul_state);
      }
      // 更新NPC认知状态
      if (payload.cognitive_dissonance) {
        App.emit('dissonance_update', payload.cognitive_dissonance);
      }
      return;
    }

    // 灵魂附生模式不应收到 choices 字段，仅 soul_decision
    App.state.isChoosing = false;
    // auto 模式下回到 playing 状态，允许输入
    App.setPhase('narrative', 'playing');
  });

  // ── 生成中止确认 ──
  App.on('generation_aborted', (payload) => {
    hideAbortButton();
    showStartButton();
    if (App.pipelineStatus) {
      App.pipelineStatus.hide();
    }
    App.state.isChoosing = false;
    App.setPhase('narrative', 'playing');
    console.log('[App] 生成已中止:', (payload && payload.message) || '');
  });

  // ── Choice System: choice_selected → 清除选择状态 ──
  App.on('choice_selected', () => {
    App.state.isChoosing = false;
  });

  // ═══════════════════════════════════════════════════
  // 灵魂附生模式
  // ═══════════════════════════════════════════════════

  // game_started_soul → 进入灵魂附生游戏模式
  App.on('game_started_soul', (payload) => {
    App.state.canonReady = true;
    App.state.isChoosing = false;
    App.setPhase('narrative', 'playing');

    hideStartButton();

    // 切换到叙事面板
    if (App.panels) {
      App.panels.switchPanel('narrative');
    }

    // 更新标题
    const titleEl = document.getElementById('titleNovel');
    if (titleEl && App.state.novelTitle) {
      titleEl.textContent = '《' + App.state.novelTitle.replace(/【.*?】/g, '') + '》';
    }

    // 更新双魂面板（如果有 soul_state 数据）
    if (payload && payload.soul_state) {
      App.emit('soul_state_update', payload.soul_state);
    }

    console.log('[App] 灵魂附生游戏启动: 主角=%s', payload.protagonist_id);
  });

  // character_selected → 角色已选定，显示主界面 + 开始冒险按钮
  App.on('character_selected', (payload) => {
    App.state.canonReady = true;
    App.state._selectedProtagonistId = payload.protagonist_id;
    App.setPhase('narrative', 'awaiting_start');

    // 切换到叙事面板
    if (App.panels) {
      App.panels.switchPanel('narrative');
    }

    // 更新标题
    const titleEl = document.getElementById('titleNovel');
    if (titleEl && App.state.novelTitle) {
      titleEl.textContent = '《' + App.state.novelTitle.replace(/【.*?】/g, '') + '》';
    }

    // ★ 显示"开始冒险"按钮（手动模式需额外检查条件）
    if (App.state.canonSource === 'manual') {
      updateStartButtonForManual();
    } else {
      showStartButton();
    }
  });

  // return_to_novel_select — 从角色选择界面返回小说选择
  App.on('return_to_novel_select', () => {
    App.state.canonReady = false;
    // 重新显示欢迎界面
    showWelcome();
    App.setPhase('novel_select', 'idle');
  });

  // ═══════════════════════════════════════════════════
  // 提供者选择（启动时选模型）
  // ═══════════════════════════════════════════════════

  // providers_list → 渲染提供者卡片
  App.on('providers_list', (payload) => {
    if (payload && payload.providers) {
      renderProviderCards(payload.providers);
    }
  });

  // provider_set → 提供者已确认（F7 设置面板使用）
  App.on('provider_set', (payload) => {
    if (payload && payload.success) {
      App.state.activeProvider = payload.provider;
      App.state.activeModel = payload.model;
    }
  });

  console.log('[App] 初始化完成');
}

// ═══════════════════════════════════════════════════════
// F7 设置面板（三级模型 Tab）
// ═══════════════════════════════════════════════════════

function initSettingsPanel() {
  const btnApply = document.getElementById('btnApplySettings');
  const btnReset = document.getElementById('btnResetSettings');
  const statusEl = document.getElementById('settingsStatus');

  // ════════════════════════════════════════════
  // 二级子菜单 ↔ 三级页面导航
  // ════════════════════════════════════════════

  function showPage(pageId) {
    document.querySelectorAll('#panel-settings .settings-page').forEach(p => p.classList.remove('settings-page--active'));
    const target = document.getElementById(pageId);
    if (target) target.classList.add('settings-page--active');
  }

  // 子菜单按钮点击
  document.querySelectorAll('.settings-sub-menu__btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const page = btn.dataset.page;
      const pageMap = {
        api: 'settingsApiPage',
        ui: 'settingsUiPage',
        pipeline: 'settingsPipelinePage',
        game: 'settingsGamePage',
        memory: 'settingsMemoryPage',
        soul: 'settingsSoulPage',
        emergence: 'settingsEmergencePage',
        reflection: 'settingsReflectionPage',
        reward: 'settingsRewardPage',
      };
      const pageId = pageMap[page];
      if (pageId) {
        showPage(pageId);
        if (page === 'pipeline') {
          document.dispatchEvent(new CustomEvent('settings_page_shown', { detail: { page: 'pipeline' } }));
        }
      }
    });
  });

  // 返回按钮
  document.querySelectorAll('.settings-back-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      showPage('settingsSubMenu');
    });
  });

  // 切换侧边栏其他面板时，下次进 F7 从头开始（子菜单）
  App.on('panel_changed', (data) => {
    if (data && data.panel !== 'settings') {
      showPage('settingsSubMenu');
    }
  });

  document.querySelectorAll('.settings-field-slider, .settings-form__slider').forEach(slider => {
    // 用下个兄弟元素显示当前值（如果存在）
    const hint = slider.nextElementSibling;
    const updateHint = () => {
      if (hint && hint.classList.contains('settings-form__hint')) {
        hint.textContent = parseFloat(slider.value).toFixed(2);
      }
    };
    updateHint();
    slider.addEventListener('input', updateHint);

    // 兼容旧的温度值标签（保留）
    const tier = slider.dataset.field ? slider.dataset.field.split('-')[0] : '';
    const valEl = document.getElementById(tier + '-temp-val');
    if (valEl) {
      slider.addEventListener('input', () => {
        valEl.textContent = parseFloat(slider.value).toFixed(1);
      });
    }
  });

  // ── 设置页内开关按钮（reflection/reward 等子页）──
  document.querySelectorAll('[data-toggle]').forEach(label => {
    const field = label.dataset.toggle;
    const checkbox = document.querySelector(`input[data-field="${field}"]`);
    if (!checkbox) return;

    const updateToggle = () => {
      if (checkbox.checked) {
        label.classList.add('settings-tag-btn--active');
        label.textContent = '\u2713 启用';
      } else {
        label.classList.remove('settings-tag-btn--active');
        label.textContent = '\u2717 禁用';
      }
    };

    label.addEventListener('click', () => {
      checkbox.checked = !checkbox.checked;
      updateToggle();
    });

    // 初始状态
    updateToggle();
  });

  // ── UI 设置标签组切换 ──
  document.querySelectorAll('.settings-tag-group').forEach(group => {
    const btns = group.querySelectorAll('.settings-tag-btn');
    btns.forEach(btn => {
      btn.addEventListener('click', () => {
        btns.forEach(b => b.classList.remove('settings-tag-btn--active'));
        btn.classList.add('settings-tag-btn--active');
      });
    });
  });

  // ════════════════════════════════════════════
  // API 设置 — 三层独立配置（每层可独立选提供者/端点/模型）
  // ════════════════════════════════════════════

  // ── 读取单层配置 ──
  function getTierConfig(tier) {
    const providerSelect = document.querySelector(`.settings-provider-select[data-tier="${tier}"]`);
    const providerType = providerSelect ? providerSelect.value : 'deepseek';

    let endpoint, model, apiKey;
    if (providerType === 'deepseek') {
      // DeepSeek: 固定端点，模型从下拉读取
      endpoint = 'https://api.deepseek.com';
      const modelSel = document.querySelector(`.settings-model-deepseek[data-tier="${tier}"] select`);
      model = modelSel ? modelSel.value : '';
      const apiEl = document.querySelector(`[data-field="${tier}-api_key"]`);
      apiKey = apiEl ? apiEl.value.trim() : '';
    } else {
      // Ollama: 端点从 IP 输入自动补齐，模型从输入框读取
      const ep = document.querySelector(`[data-field="${tier}-endpoint"]`);
      endpoint = ep ? ep.value.trim() : '';
      const modelEl = document.querySelector(`[data-field="${tier}-model"]`);
      model = modelEl ? modelEl.value.trim() : '';
      apiKey = '';
    }

    const valField = (field) => {
      const el = document.querySelector(`[data-field="${tier}-${field}"]`);
      if (!el) return '';
      if (field === 'temperature') return parseFloat(el.value) || 0.7;
      if (field === 'max_tokens') return parseInt(el.value) || 2048;
      return el.value.trim();
    };

    const config = {
      type: providerType,
      endpoint: endpoint,
      model: model,
      temperature: parseFloat(valField('temperature')) || 0.7,
      max_tokens: parseInt(valField('max_tokens')) || 2048,
      timeout: tier === 'strong' ? 180 : tier === 'medium' ? 120 : 60,
    };
    if (apiKey) config.api_key = apiKey;
    return config;
  }

  // ── 卡片独立应用按钮 ──
  document.querySelectorAll('.settings-btn--apply').forEach(btn => {
    btn.addEventListener('click', () => {
      const tier = btn.dataset.tier;
      if (!tier) return;
      const config = getTierConfig(tier);
      if (!config.endpoint) {
        showApiStatus(`请填写 ${tier} 的 API 端点`, 'error');
        return;
      }
      showApiStatus(`正在应用 ${tier} 层配置...`, 'loading');
      if (App.ws && App.ws.isConnected()) {
        App.ws.send('update_config', { providers: { [tier]: config } });
      } else {
        showApiStatus('未连接到服务器', 'error');
      }
    });
  });

  // ── 卡片独立重置按钮 ──
  document.querySelectorAll('.settings-btn--reset').forEach(btn => {
    btn.addEventListener('click', () => {
      const tier = btn.dataset.tier;
      if (!tier) return;
      const card = document.querySelector(`.settings-tier-card[data-tier="${tier}"]`);
      if (!card) return;
      card.querySelectorAll('.settings-field-input').forEach(el => {
        if (el.type === 'number') el.value = '';
        else el.value = '';
      });
      card.querySelectorAll('.settings-field-slider').forEach(s => {
        s.value = tier === 'light' ? '0.5' : '0.7';
        const valEl = document.getElementById(tier + '-temp-val');
        if (valEl) valEl.textContent = parseFloat(s.value).toFixed(1);
      });
      showApiStatus(`已重置 ${tier} 层`, 'success');
    });
  });

  // ── 提供者选择 → 切换字段显隐 + 自动填入 ──
  document.querySelectorAll('.settings-provider-select').forEach(sel => {
    sel.addEventListener('change', () => {
      const tier = sel.dataset.tier;
      if (!tier) return;
      const provider = sel.value;
      const card = document.querySelector(`.settings-tier-card[data-tier="${tier}"]`);
      if (!card) return;

      // 更新卡片 dataset —— CSS 根据此属性切换字段显隐
      card.dataset.providerType = provider;

      if (provider === 'deepseek') {
        // DeepSeek: 默认端点固定，不清除用户可能已填的 api_key
        const endpointInput = document.querySelector(`[data-field="${tier}-endpoint"]`);
        if (endpointInput) endpointInput.value = '';
      } else {
        // Ollama: 清空 api_key，保留可能已填的 IP
        const apiKeyInput = document.querySelector(`[data-field="${tier}-api_key"]`);
        if (apiKeyInput) apiKeyInput.value = '';
      }
    });
  });

  // ── Ollama 端点输入：离开焦点时自动补齐 http:// + :11434 ──
  document.querySelectorAll('.settings-field-endpoint input').forEach(input => {
    input.addEventListener('blur', () => {
      const raw = input.value.trim();
      if (!raw) return;
      let ep = raw;
      // 已有完整协议则不处理
      if (!/^https?:\/\//i.test(ep)) {
        ep = 'http://' + ep;
      }
      // 已有端口则不重复追加
      if (!/:\d+/.test(ep)) {
        ep += ':11434';
      }
      input.value = ep;
    });
  });

  // ── DeepSeek 模型下拉同步 ──
  document.querySelectorAll('.settings-model-deepseek select').forEach(sel => {
    sel.addEventListener('change', () => {
      // 选中的值即模型名，getTierConfig 直接读取该 select
    });
  });

  // ── 查询可用模型（每层独立） ──
  document.querySelectorAll('.settings-fetch-btn').forEach(btn => {
    btn.addEventListener('click', async () => {
      const tier = btn.dataset.tier;
      if (!tier) return;

      const endpoint = document.querySelector(`[data-field="${tier}-endpoint"]`);
      const apiKey = document.querySelector(`[data-field="${tier}-api_key"]`);
      const modelInput = document.querySelector(`[data-field="${tier}-model"]`);
      const modelSelect = document.getElementById(`${tier}-model-select`);

      if (!endpoint || !endpoint.value.trim()) {
        showApiStatus(`请先填写 ${tier} 层的 API 端点`, 'error');
        return;
      }

      // 从卡片读取真正的提供者类型
      const card = document.querySelector(`.settings-tier-card[data-tier="${tier}"]`);
      const type = card ? (card.dataset.providerType || 'deepseek') : 'deepseek';

      btn.disabled = true;
      btn.textContent = '⌛';
      if (modelSelect) {
        modelSelect.style.display = 'block';
        modelSelect.innerHTML = '<option value="">请求中...</option>';
      }

      if (App.ws && App.ws.isConnected()) {
        // 临时存储 tier 上下文，model_list 回调中读取
        App.state._fetchModelsTier = tier;
        App.ws.send('fetch_models', {
          type: type,
          endpoint: endpoint.value.trim(),
          api_key: apiKey ? apiKey.value.trim() : '',
        });
      }
    });
  });

  // ── model_list 事件（合并两个上下文：F7 设置面板 + Provider 配置弹窗）──
  App.on('model_list', (payload) => {
    // 上下文 A：F7 设置面板的 tier 模型下拉
    const tier = App.state && App.state._fetchModelsTier;
    if (tier) {

    const modelSelect = document.getElementById(`${tier}-model-select`);
    const modelInput = document.querySelector(`[data-field="${tier}-model"]`);
    const fetchBtn = document.querySelector(`.settings-fetch-btn[data-tier="${tier}"]`);

    if (!modelSelect) return;

    // 统一转小写：部分 API（如 DeepSeek）返回的模型名带大写但只接受小写
    const models = (payload.models || []).map(m => m.toLowerCase());
    const error = payload.error || '';

    if (error) {
      modelSelect.innerHTML = `<option value="">查询失败: ${error}</option>`;
      if (fetchBtn) { fetchBtn.disabled = false; fetchBtn.textContent = '🔄'; }
      return;
    }

    if (models.length === 0) {
      modelSelect.innerHTML = '<option value="">未找到模型</option>';
      if (fetchBtn) { fetchBtn.disabled = false; fetchBtn.textContent = '🔄'; }
      return;
    }

    modelSelect.innerHTML = '<option value="">— 选择模型 —</option>'
      + models.map(m => `<option value="${escapeHtml(m)}">${escapeHtml(m)}</option>`).join('');

    modelSelect.addEventListener('change', () => {
      if (modelSelect.value && modelInput) {
        modelInput.value = modelSelect.value;
      }
    });

    // 保持按钮可点击（记录模型数量但不禁用）
    if (fetchBtn) {
      fetchBtn.disabled = false;
      fetchBtn.textContent = `📋 ${models.length}`;
    }
    return;
  }

    // 上下文 B：Provider 配置弹窗的模型下拉
    {
      const select = window.__providerModelSelect;
      const custom = window.__providerModelCustom;
      const confirmBtn = window.__providerConfirmBtn;
      const fetchBtn = window.__providerFetchBtn;
      if (!select) return;

      // 统一转小写：部分 API（如 DeepSeek）返回的模型名带大写但只接受小写
      const models = (payload.models || []).map(m => m.toLowerCase());
      const error = payload.error || '';

      if (error) {
        select.innerHTML = `<option value="">查询失败: ${error}</option>`;
        select.style.display = 'none';
        custom.style.display = 'block';
        custom.placeholder = '手动输入模型名称';
        if (fetchBtn) {
          fetchBtn.disabled = false;
          fetchBtn.textContent = '🔄 重试';
        }
        return;
      }

      if (models.length === 0) {
        select.innerHTML = '<option value="">未找到可用模型，请手动输入</option>';
        custom.style.display = 'block';
        custom.placeholder = '手动输入模型名称 (如 qwen3.5:9b)';
        if (confirmBtn) confirmBtn.disabled = false;
        return;
      }

      const defaultForType = {
        deepseek: 'deepseek-v4-flash',
        ollama: 'llama3.1:8b',
      };
      const defaultModel = defaultForType[window.__provType] || '';

      select.innerHTML = models.map(m =>
        `<option value="${escapeHtml(m)}" ${m === defaultModel ? 'selected' : ''}>${escapeHtml(m)}</option>`
      ).join('');

      select.style.display = 'block';
      custom.style.display = 'none';

      if (confirmBtn) {
        confirmBtn.disabled = false;
        confirmBtn.textContent = '✅ 确认，开始探索';
      }
      if (fetchBtn) {
        fetchBtn.textContent = `✅ ${models.length} 个模型可用`;
      }
    }
  });

  // ── 端点输入自动补全：已迁移至 .settings-field-endpoint 独有 blur 处理器
  //     (见上方「Ollama 端点输入：离开焦点时自动补齐 http:// + :11434」)

  function showApiStatus(msg, type) {
    const el = document.getElementById('settingsApiStatus');
    if (!el) return;
    el.textContent = msg;
    el.style.color = type === 'error' ? '#f87171' : type === 'success' ? '#4ade80' : 'var(--text-muted)';
    if (type !== 'loading') {
      setTimeout(() => { el.textContent = ''; }, 3000);
    }
  }

  // ── 温度 slider 实时更新 ──
  document.querySelectorAll('.settings-field-slider, .settings-form__slider').forEach(slider => {
    const tier = slider.dataset.field ? slider.dataset.field.split('-')[0] : '';
    const valEl = document.getElementById(tier + '-temp-val');
    if (valEl && !slider._listenerAttached) {
      slider._listenerAttached = true;
      slider.addEventListener('input', () => {
        valEl.textContent = parseFloat(slider.value).toFixed(1);
      });
    }
  });

  // ── 配置应用成功 ──
  App.on('config_updated', (payload) => {
    const statusEl = document.getElementById('settingsApiStatus');
    if (statusEl) {
      statusEl.textContent = '✅ 配置已应用' + (payload && payload.note ? ' · ' + payload.note : '');
      statusEl.style.color = '#4ade80';
      setTimeout(() => { statusEl.textContent = ''; }, 3000);
    }
  });

  // ── 监听通用错误事件 ──
  App.on('error', (payload) => {
    const code = (payload && payload.code) || '';
    const message = (payload && payload.message) || '';

    // 设置面板配置失败 → 已有专门处理
    if (code === 'CONFIG_FAILED') {
      showSettingsStatus('❌ 配置应用失败: ' + message, 'error');
      return;
    }

    // Pipeline 执行失败 → 恢复 UI 状态，允许重试
    if (code === 'PIPELINE_FAILED') {
      console.error('[App] Pipeline 执行失败:', message);
      // 恢复 FSM 状态（同 generation_aborted）
      App.setPhase('novel_select', 'ready');
      App.state.isChoosing = false;
      App.state.beatCount = 0;

      hideAbortButton();
      showStartButton();
      if (App.pipelineStatus) App.pipelineStatus.hide();

      showErrorToast('❌ ' + message + '\n请检查 API 配置后重试');
      return;
    }

    // 生成相关错误 → 清除加载态
    if (code === 'CANON_FAILED' || code === 'INTERNAL_ERROR') {
      // 如果正在叙事中，恢复 UI 允许继续
      if (App.state.phase === 'narrative') {
        hideAbortButton();
        if (App.pipelineStatus) App.pipelineStatus.hide();
        App.state.isChoosing = false;
        App.setPhase('narrative', 'playing');
      }
      App.emit('canon_generation_failed', {
        message: message || '服务器内部错误，请重试',
      });
      return;
    }

    // 通用错误日志
    console.warn('[App] 未处理错误:', code, message);
  });
}

/**
 * 显示设置面板状态信息
 * @param {string} msg
 * @param {string} type 'success'|'error'|'loading'
 */
function showSettingsStatus(msg, type) {
  const el = document.getElementById('settingsStatus');
  if (!el) return;
  el.textContent = msg;
  el.className = 'settings-status settings-status--' + type;
}

/**
 * 归一化端点地址：自动补 http:// + Ollama 默认端口 11434
 * @param {string} raw - 用户输入
 * @param {'ollama'|'openai'|'deepseek'} providerType
 * @returns {string} 归一化后的基点地址（无路径后缀）
 */
function normalizeEndpoint(raw, providerType) {
  let ep = raw.trim();
  if (!ep) return '';
  // 自动补 http://
  if (!/^https?:\/\//i.test(ep)) {
    ep = 'http://' + ep;
  }
  try {
    const url = new URL(ep);
    // Ollama 无端口默认 11434
    if (providerType === 'ollama' && !url.port) {
      url.port = '11434';
    }
    // 只保留 scheme://host:port，去掉已有路径
    return url.origin;
  } catch {
    // URL 解析失败 → 返回空（由服务端验证报错）
    return '';
  }
}

// ═══════════════════════════════════════════════════════
// 欢迎界面 — 状态机驱动
// ═══════════════════════════════════════════════════════

function initWelcomeOverlay() {
  // ── 标题栏按钮：点击弹出欢迎界面 ──
  const titleBtn = document.getElementById('titleNovelBtn');
  titleBtn.addEventListener('click', () => {
    // 游戏中禁止切换
    if (App.state.isMidGame) {
      return;
    }
    showWelcome();
  });

  // ── 保留已有按钮 ──
  const btnKeep = document.getElementById('btnKeepCanon');
  if (btnKeep) {
    btnKeep.addEventListener('click', () => {
      // ★ 运行 Canon（手动创建模式）：通过标题加载
      if (App.state.selectedCanonType === 'running' && App.state.selectedCanonTitle) {
        App.ws.send('load_running_canon', {
          title: App.state.selectedCanonTitle,
        });
        return;
      }
      const sourceFile = App.state.selectedCanonFile;
      if (!sourceFile) {
        // 没有选中 canon，选第一个
        if (App.state.availableCanons.length > 0) {
          App.state.selectedCanonFile = App.state.availableCanons[0].source_file;
        }
      }
      if (App.state.selectedCanonFile) {
        App.ws.send('load_existing_canon', {
          source_file: App.state.selectedCanonFile,
        });
      }
    });
  }

  // ── 导入 Canon JSON 按钮 ──
  const btnImportJson = document.getElementById('btnImportJson');
  const importJsonInput = document.getElementById('importJsonInput');
  if (btnImportJson && importJsonInput) {
    btnImportJson.addEventListener('click', () => importJsonInput.click());
    importJsonInput.addEventListener('change', async () => {
      const file = importJsonInput.files[0];
      if (!file) return;
      const text = await file.text();
      if (App.ws && App.ws.isConnected()) {
        App.ws.send('import_canon_json', {
          filename: file.name,
          content: text,
        });
      }
    });
  }

  // ── Canon JSON 模板下载 ──
  const templateLink = document.getElementById('canonTemplateLink');
  if (templateLink) {
    templateLink.addEventListener('click', (e) => {
      e.preventDefault();
      downloadCanonTemplate();
    });
  }

  // ── 从头创建空白 Canon（两处按钮）──
  function _setupCreateEmptyBtn(btnId, inputId) {
    const btn = document.getElementById(btnId);
    const input = document.getElementById(inputId);
    if (!btn || !input) return;
    btn.addEventListener('click', () => {
      const title = input.value.trim();
      if (!title) {
        input.style.borderColor = 'var(--text-red)';
        return;
      }
      btn.disabled = true;
      btn.textContent = '创建中...';
      if (App.ws && App.ws.isConnected()) {
        App.ws.send('create_empty_canon', { title: title });
      }
    });
  }
  _setupCreateEmptyBtn('btnCreateEmpty', 'emptyCanonTitle');
  _setupCreateEmptyBtn('btnCreateEmpty2', 'emptyCanonTitle2');

  // ── 初始状态：显示欢迎界面 → 开始扫描 ──
  App.setPhase('novel_select', 'idle');
  const overlay = document.getElementById('welcomeOverlay');
  if (overlay) {
    overlay.classList.remove('welcome-overlay--hidden');
  }
  hideAllWelcomeSections();

  // 直接开始扫描（提供者配置由 F7 设置面板管理，不在欢迎界面选择）
  startScanning();
  // ws.connect() 稍后执行，经由 ws_connected 事件自动触发 request_canon_list

  // ── 关闭欢迎界面 ──
  const btnClose = document.getElementById('btnWelcomeClose');
  if (btnClose) {
    btnClose.addEventListener('click', () => {
      hideWelcome();
    });
  }

  // ── 刷新（重新扫描 canon 文件）──
  const btnRefresh = document.getElementById('btnWelcomeRefresh');
  if (btnRefresh) {
    btnRefresh.addEventListener('click', () => {
      hideAllWelcomeSections();
      App.setPhase('novel_select', 'idle');
      startScanning();
      if (App.ws && App.ws.isConnected()) {
        App.ws.send('request_canon_list', {});
      }
    });
  }

  // ── "重新扫描"按钮 ──
  const btnRescan = document.getElementById('btnRescan');
  if (btnRescan) {
    btnRescan.addEventListener('click', () => {
      btnRescan.style.display = 'none';
      const scanning = document.getElementById('initialScanning');
      if (scanning) {
        scanning.style.display = 'flex';
        const scanningText = document.querySelector('.initial-scanning__text');
        if (scanningText) scanningText.textContent = '正在重新扫描小说目录...';
      }
      if (App.ws && App.ws.isConnected()) {
        App.ws.send('request_canon_list', {});
      }
    });
  }

  // ── 扫描超时检测：使用递归 setTimeout 替代 setInterval ──
  //    避免请求堆积，支持外部清理
  let scanRetries = 0;

  function _scanTimeout() {
    // 如果已经收到 canon_list（状态已切换），清除定时器
    if (App.state.novelSelectPhase !== 'scanning') {
      App.state.generationTimerId = null;
      return;
    }
    scanRetries++;
    if (scanRetries > 3) {
      // 3 次重试后（45 秒），显示重新扫描按钮
      App.state.generationTimerId = null;
      console.warn('[App] 扫描超时，显示重新扫描按钮');
      const scanningText = document.querySelector('.initial-scanning__text');
      if (scanningText) scanningText.textContent = '⚠️ 扫描失败，请检查服务器连接';
      if (btnRescan) btnRescan.style.display = 'inline-block';
      return;
    }
    // 每 15 秒重试一次
    console.log(`[App] 扫描超时 (${scanRetries}/3)，重新请求 canon_list`);
    const scanningText = document.querySelector('.initial-scanning__text');
    if (scanningText) scanningText.textContent = `正在扫描小说目录... (重试 ${scanRetries}/3)`;
    if (App.ws && App.ws.isConnected()) {
      App.ws.send('request_canon_list', {});
    }
    // 继续轮询
    App.state.generationTimerId = setTimeout(_scanTimeout, 15000);
  }
  App.state.generationTimerId = setTimeout(_scanTimeout, 15000);

  // ── "中止生成" 按钮（事件委托，独立于 startBtn 存在）──
  document.addEventListener('click', function _abortDelegation(e) {
    const btn = e.target.closest('#abortGameBtn');
    if (!btn) return;
    console.log('[App] 中止按钮点击');
    // 1. 尝试 WebSocket
    if (App.ws && App.ws.isConnected()) {
      App.ws.send("abort_generation", {});
      console.log('[App] 通过 WebSocket 发送中止');
    } else {
      console.warn('[App] WebSocket 未连接');
    }
    // 2. 同时通过 HTTP 兜底
    const sid = App.state.sessionId || localStorage.getItem('rain_session_id');
    if (sid) {
      fetch('/api/abort?session_id=' + encodeURIComponent(sid), { method: 'POST' })
        .then(r => r.json())
        .then(d => console.log('[App] HTTP 中止结果:', d))
        .catch(e => console.warn('[App] HTTP 中止失败:', e));
    }
  });

}

// ═══════════════════════════════════════════════════════
// 刷新防护 — 拦截 F5/Ctrl+R，发送中止命令
// ═══════════════════════════════════════════════════════

/**
 * 初始化刷新防护
 * 拦截 Ctrl+R 和页面关闭，发送中止请求到后端
 */
function _initRefreshGuard() {
  console.log('[App] 初始化刷新防护');
  // ── beforeunload: 页面关闭/刷新时自动中止（无法自定义弹窗）──
  window.addEventListener('beforeunload', (e) => {
    const sid = App.state.sessionId || localStorage.getItem('rain_session_id');
    const isActive = App.state.isMidGame || App.state.canonReady || App.state.gamePhase === 'generating';
    if (isActive && sid) {
      console.warn('[App] 页面关闭/刷新，发送中止请求');
      navigator.sendBeacon('/api/abort?session_id=' + encodeURIComponent(sid));
      // 设置 returnValue 触发浏览器默认离开确认
      e.returnValue = '';
    }
  });

  // ── 拦截所有刷新快捷键 ──
  document.addEventListener('keydown', (e) => {
    const isRefreshKey = (
      e.key === 'F5' ||
      ((e.key === 'r' || e.key === 'R') && (e.ctrlKey || e.metaKey))
    );
    if (!isRefreshKey) return;

    const isActive = App.state.isMidGame || App.state.canonReady || App.state.beatCount > 0;
    if (!isActive) {
      // 未开始游戏：允许正常刷新
      return;
    }

    e.preventDefault();
    e.stopPropagation();
    console.warn('[App] 拦截刷新快捷键:', e.key);
    _showRefreshConfirmModal();
  });
}

/**
 * 显示确认刷新的自定义弹窗
 */
function _showRefreshConfirmModal() {
  let modal = document.getElementById('refreshConfirmModal');
  if (!modal) {
    modal = document.createElement('div');
    modal.id = 'refreshConfirmModal';
    modal.className = 'modal-overlay';
    modal.innerHTML = [
      '<div class="refresh-modal__content">',
      '  <div class="refresh-modal__icon">&#x26A0;&#xFE0F;</div>',
      '  <h2 class="refresh-modal__title">确认刷新页面？</h2>',
      '  <p class="refresh-modal__desc">',
      '    当前大模型正在生成剧情内容，刷新页面将中止所有管线任务。</p>',
      '  <p class="refresh-modal__desc">',
      '    页面刷新后游戏将回到初始状态。</p>',
      '  <div class="refresh-modal__actions">',
      '    <button id="refreshConfirmBtn" class="refresh-modal__btn--danger">确认刷新并中止</button>',
      '    <button id="refreshCancelBtn" class="refresh-modal__btn--secondary">取消</button>',
      '  </div>',
      '</div>',
    ].join('');
    document.body.appendChild(modal);
  }

  // 确认刷新
  const confirmBtn = document.getElementById('refreshConfirmBtn');
  if (confirmBtn) {
    confirmBtn.onclick = function() {
      // 通过 WebSocket 发送中止
      if (App.ws && typeof App.ws.send === 'function') {
        App.ws.send('abort_generation', {});
      }
      // 同时通过 HTTP 发送（兜底）
      const sid = App.state.sessionId || localStorage.getItem('rain_session_id');
      if (sid) {
        navigator.sendBeacon('/api/abort?session_id=' + encodeURIComponent(sid));
      }
      modal.style.display = 'none';
      // 保留 session_id 以便刷新后重连恢复会话
      // 执行刷新
      window.location.reload();
    };
  }

  // 取消刷新
  const cancelBtn = document.getElementById('refreshCancelBtn');
  if (cancelBtn) {
    cancelBtn.onclick = function() {
      modal.style.display = 'none';
    };
  }

  modal.style.display = 'flex';
}

/**
 * 处理 canon_list 消息：分支到确认弹窗或选择界面
 * @param {Object} payload
 */
function handleCanonList(payload) {
  // 始终更新可用文件数据（即使重复消息也刷新列表）
  App.state.hasExistingCanon = !!payload.has_existing_canon;
  App.state.availableTxtFiles = payload.txt_files || [];
  App.state.availableCanons = payload.canons || [];

  // 幂等守卫：如果已离开 scanning/idle 阶段（如已进入 confirming/selecting），
  // 只更新数据，不重复触发状态转换和 UI 切换
  const skipStates = ['confirming', 'selecting', 'generating', 'ready'];
  if (App.fsm.phase === 'novel_select' && skipStates.includes(App.fsm.state)) {
    console.log('[App] handleCanonList: 当前状态为', App.fsm.state, '，跳过重复处理');
    return;
  }

  // 清除扫描超时定时器
  if (App.state.generationTimerId) {
    clearTimeout(App.state.generationTimerId);
    App.state.generationTimerId = null;
  }

  App.state.selectedCanonFile = '';

  hideAllWelcomeSections();

  // 隐藏初始扫描状态
  const scanning = document.getElementById('initialScanning');
  if (scanning) scanning.style.display = 'none';

  // 隐藏重新扫描按钮
  const btnRescan = document.getElementById('btnRescan');
  if (btnRescan) btnRescan.style.display = 'none';

  // 现在可以安全地转换状态
  App.setPhase('novel_select', 'list_received');

  if (App.state.hasExistingCanon) {
    // 有 canon → 确认弹窗
    showConfirmDialog(App.state.availableCanons);
  } else {
    // 无 canon → 显示导入引导
    App.setPhase('novel_select', 'selecting');
    const selector = document.getElementById('novelSelector');
    if (selector) selector.style.display = 'block';
  }
  // ★ 始终显示"从头创建"入口
  const createSection = document.getElementById('createEmptySection');
  if (createSection) createSection.style.display = 'block';

  // 如果扫描结果为空，显示重新扫描按钮
  const hasAny = (payload.txt_files && payload.txt_files.length > 0) ||
                  (payload.canons && payload.canons.length > 0);
  if (!hasAny && btnRescan) {
    btnRescan.style.display = 'inline-block';
  }
  // 显示刷新按钮
  const btnRefresh = document.getElementById('btnWelcomeRefresh');
  if (btnRefresh) btnRefresh.style.display = 'inline-block';
}

/**
 * 显示确认弹窗（有 canon 时）
 * @param {Array} canons - canon 摘要列表
 */
function showConfirmDialog(canons) {
  App.setPhase('novel_select', 'confirming');

  const dialog = document.getElementById('confirmDialog');
  const list = document.getElementById('confirmCanonList');

  if (!dialog || !list) return;
  dialog.style.display = 'block';

  // ★ 合并 running canons（手动创建的小说）
  const runningCanons = App.state.availableRunningCanons || [];
  const allItems = [
    ...canons.map(c => ({ ...c, _type: 'canon' })),
    ...runningCanons.map(c => ({ ...c, _type: 'running' })),
  ];

  list.innerHTML = '';

  if (allItems.length === 0) {
    list.innerHTML = '<p style="color:#8b949e;font-size:13px;">无世界观数据</p>';
    return;
  }

  allItems.forEach((item, index) => {
    const card = document.createElement('div');
    card.className = 'confirm-canon-item';
    if (index === 0) {
      card.classList.add('confirm-canon-item--selected');
      App.state.selectedCanonFile = item._type === 'running' ? null : item.source_file;
      App.state.selectedCanonTitle = item.title;
      App.state.selectedCanonType = item._type;
    }

    const metaParts = [];
    if (item.char_count !== undefined) metaParts.push(item.char_count + ' 角色');
    if (item.loc_count !== undefined) metaParts.push(item.loc_count + ' 地点');
    if (item._type === 'running') metaParts.push('手动创建');

    card.innerHTML = `<div class="confirm-canon-item__name">📖 ${item.title}</div>
      ${metaParts.length ? '<div class="confirm-canon-item__meta">' + metaParts.join(' · ') + '</div>' : ''}`;

    card.addEventListener('click', () => {
      list.querySelectorAll('.confirm-canon-item').forEach(c => c.classList.remove('confirm-canon-item--selected'));
      card.classList.add('confirm-canon-item--selected');
      App.state.selectedCanonFile = item._type === 'running' ? null : item.source_file;
      App.state.selectedCanonTitle = item.title;
      App.state.selectedCanonType = item._type;
    });

    list.appendChild(card);
  });

}


/**
 * 更新标题栏按钮状态
 */
function updateTitleButton() {
  const btn = document.getElementById('titleNovelBtn');
  const novel = document.getElementById('titleNovel');
  if (!btn) return;

  if (App.state.isMidGame) {
    // 游戏中：灰化 + tooltip
    btn.disabled = true;
    btn.title = '游戏进行中，无法切换小说';
  } else if (App.state.gamePhase === 'generating') {
    // 生成中禁止切换
    btn.disabled = true;
    btn.title = '正在生成中，请稍后再试';
  } else if (App.state.canonReady && App.state.novelTitle) {
    // 已选择小说
    btn.disabled = false;
    btn.title = '《' + App.state.novelTitle + '》— 点击更换小说';
  } else {
    // 未选择
    btn.disabled = false;
    btn.title = '点击选择小说';
  }

  if (novel) {
    if (App.state.canonReady && App.state.novelTitle) {
      novel.textContent = '《' + App.state.novelTitle.replace(/【.*?】/g, '') + '》';
    } else {
      novel.textContent = '请选择小说';
    }
  }
}

/**
 * 隐藏欢迎界面内所有子区域
 */
function hideAllWelcomeSections() {
  const ids = ['confirmDialog', 'novelSelector', 'initialScanning', 'createEmptySection'];
  ids.forEach(id => {
    const el = document.getElementById(id);
    if (el) el.style.display = 'none';
  });
}

// ═══════════════════════════════════════════════════════
// 欢迎界面 显示/隐藏
// ═══════════════════════════════════════════════════════

function showWelcome() {
  const overlay = document.getElementById('welcomeOverlay');
  if (!overlay) return;
  overlay.classList.remove('welcome-overlay--hidden');

  if (App.ws && App.ws.isConnected()) {
    App.setPhase('novel_select', 'idle');
    hideAllWelcomeSections();
    startScanning();
    App.ws.send('request_canon_list', {});
  }
}

function hideWelcome() {
  const overlay = document.getElementById('welcomeOverlay');
  if (!overlay) return;
  overlay.classList.add('welcome-overlay--hidden');
}

/**
 * 显示非阻塞错误通知 toast
 * @param {string} msg
 */
function showErrorToast(msg) {
  const existing = document.getElementById('errorToast');
  if (existing) existing.remove();

  const toast = document.createElement('div');
  toast.id = 'errorToast';
  toast.className = 'error-toast';
  toast.innerHTML = msg.replace(/\n/g, '<br>');
  document.body.appendChild(toast);

  // 3.5 秒后自动消失
  setTimeout(() => {
    toast.classList.add('error-toast--fadeout');
    setTimeout(() => { if (toast.parentNode) toast.parentNode.removeChild(toast); }, 400);
  }, 3500);
}

// ═══════════════════════════════════════════════════════
// 提供者选择（启动时选模型）
// ═══════════════════════════════════════════════════════

let _selectedProvider = null;
let _providerData = {};

/**
 * 渲染提供者选择卡片
 */
function renderProviderCards(providers) {
  const cards = document.getElementById('providerCards');
  if (!cards) return;

  const entries = Object.entries(providers);
  if (entries.length === 0) {
    cards.innerHTML = `
      <div class="provider-card" style="cursor:default;opacity:0.6;width:100%;">
        <div class="provider-card__label">未检测到可用模型配置</div>
        <div class="provider-card__desc">请在 config.yaml 中添加提供者</div>
      </div>`;
    return;
  }

  _providerData = providers;

  const providerInfo = {
    deepseek: { icon: '🔷', desc: '云端 API，高性能', tag: '推荐' },
    ollama: { icon: '🖥️', desc: '本地运行，隐私优先', tag: '本地' },
  };

  cards.innerHTML = entries.map(([name, cfg]) => {
    const info = providerInfo[cfg.type] || { icon: '🔌', desc: '', tag: cfg.type };
    return `
      <div class="provider-card" data-provider="${name}">
        <div class="provider-card__icon">${info.icon}</div>
        <div class="provider-card__name">${escapeHtml(name)}</div>
        <div class="provider-card__desc">${info.desc}</div>
        <div class="provider-card__tag">${info.tag}</div>
      </div>
    `;
  }).join('');

  // 绑定选择事件
  cards.querySelectorAll('.provider-card').forEach(card => {
    card.addEventListener('click', () => {
      cards.querySelectorAll('.provider-card').forEach(c => c.classList.remove('provider-card--selected'));
      card.classList.add('provider-card--selected');
      _selectedProvider = card.dataset.provider;
      showProviderConfig(_selectedProvider);
    });
  });
}

/**
 * 显示提供者配置字段
 */
function showProviderConfig(providerName) {
  const config = document.getElementById('providerConfig');
  const modelSelect = document.getElementById('providerModelSelect');
  const modelCustomInput = document.getElementById('providerModelCustom');
  const fetchBtn = document.getElementById('btnFetchModels');
  const keyField = document.getElementById('providerKeyField');
  const keyInput = document.getElementById('providerKeyInput');
  const confirmBtn = document.getElementById('btnConfirmProvider');

  if (!config) return;
  config.style.display = 'flex';

  const data = _providerData[providerName] || {};
  const provType = data.type || '';

  // 显示/隐藏 API 密钥字段
  if (provType === 'deepseek' && !data.has_key) {
    keyField.style.display = 'flex';
    keyInput.placeholder = '输入 DeepSeek API 密钥';
  } else {
    keyField.style.display = 'none';
  }

  // 重置模型选择状态
  modelSelect.style.display = 'none';
  modelSelect.innerHTML = '<option value="">查询中...</option>';
  modelCustomInput.style.display = 'none';
  modelCustomInput.value = '';
  fetchBtn.disabled = false;
  fetchBtn.textContent = '🔍 查询可用模型';
  confirmBtn.disabled = true;
  confirmBtn.textContent = '请先选择模型';

  // 移除旧事件绑定
  const newFetchBtn = fetchBtn.cloneNode(true);
  fetchBtn.parentNode.replaceChild(newFetchBtn, fetchBtn);
  const newConfirmBtn = confirmBtn.cloneNode(true);
  confirmBtn.parentNode.replaceChild(newConfirmBtn, confirmBtn);

  // 查询模型按钮
  newFetchBtn.addEventListener('click', () => {
    newFetchBtn.disabled = true;
    newFetchBtn.textContent = '正在查询...';
    modelSelect.style.display = 'block';
    modelSelect.innerHTML = '<option value="">请求中...</option>';

    const enteredKey = keyInput ? keyInput.value.trim() : '';
    if (App.ws && App.ws.isConnected()) {
      App.ws.send('fetch_models', {
        type: provType,
        endpoint: data.endpoint || '',
        api_key: enteredKey || data.api_key || '',
      });
    }
  });

  // 确认按钮（绑定在 model_list 回调之后设置）
  newConfirmBtn.addEventListener('click', () => {
    const model = modelSelect.style.display !== 'none' && modelSelect.value
      ? modelSelect.value
      : modelCustomInput.value.trim();
    if (!model) {
      newConfirmBtn.textContent = '请选择或输入模型';
      return;
    }
    const apiKey = keyInput ? keyInput.value.trim() : '';
    newConfirmBtn.disabled = true;
    newConfirmBtn.textContent = '正在配置...';
    if (App.ws && App.ws.isConnected()) {
      App.ws.send('set_provider', {
        provider: providerName,
        model: model,
        api_key: apiKey,
      });
    }
  });

  // 存储回调引用供 model_list 事件使用
  window.__providerModelSelect = modelSelect;
  window.__providerModelCustom = modelCustomInput;
  window.__providerConfirmBtn = newConfirmBtn;
  window.__providerFetchBtn = newFetchBtn;
  window.__provType = provType;
}

/**
 * 开始扫描小说（由 provider_set 事件触发）
 */
function startScanning() {
  App.setPhase('novel_select', 'scanning');
  const scanning = document.getElementById('initialScanning');
  if (scanning) scanning.style.display = 'flex';
}

/**
 * 进入空状态：不加载任何小说，直接进入主界面
/**
 * 显示"开始冒险"按钮（替代旧的 Enter 触发）
 */
function showStartButton() {
  const btn = document.getElementById('startGameBtn');
  if (btn) {
    btn.style.display = 'flex';
    btn.disabled = false;
    // 根据游戏状态设置按钮文字
    const span = btn.querySelector('.start-btn__text');
    if (span) {
      span.textContent = App.state.beatCount > 0 ? '继续冒险' : '开始冒险';
    }
  }
}

/**
 * 手动模式：检查条件后更新开始按钮状态
 */
function updateStartButtonForManual() {
  const btn = document.getElementById('startGameBtn');
  if (!btn) return;

  const chars = App.state.availableCanonChars || [];
  const locs = App.state.availableCanonLocs || [];
  const wr = App.state.worldRules || {};
  const hasWorldRules = Object.values(wr).some(v => v && String(v).trim());

  const met = chars.length >= 1 && locs.length >= 1 && hasWorldRules;
  const missing = [];
  if (chars.length < 1) missing.push('角色');
  if (locs.length < 1) missing.push('地点');
  if (!hasWorldRules) missing.push('世界观');

  btn.style.display = 'flex';
  if (met) {
    btn.disabled = false;
    btn.title = '';
    const span = btn.querySelector('.start-btn__text');
    if (span) span.textContent = '开始冒险';
    const hint = btn.querySelector('.start-btn__hint');
    if (hint) hint.textContent = '进入叙事';
  } else {
    btn.disabled = true;
    btn.title = '缺少: ' + missing.join(', ');
    const span = btn.querySelector('.start-btn__text');
    if (span) span.textContent = '开始冒险';
    const hint = btn.querySelector('.start-btn__hint');
    if (hint) hint.textContent = '需要' + missing.join(' + ');
  }
}

// 监听 canon_entries_updated 以更新手动模式按钮
App.on('canon_entries_updated', () => {
  if (App.state.canonSource === 'manual' && App.state._selectedProtagonistId) {
    updateStartButtonForManual();
  }
});

/**
 * 隐藏"开始冒险"按钮
 */
function hideStartButton() {
  const btn = document.getElementById('startGameBtn');
  if (btn) {
    btn.style.display = 'none';
    btn.disabled = true;
  }
}

/**
 * 显示中止按钮（生成开始时调用）
 */
function showAbortButton() {
  const btn = document.getElementById("abortGameBtn");
  if (btn) {
    btn.style.display = "flex";
    btn.disabled = false;
  }
  hideStartButton();
}
// 暴露为全局函数，供 ws-client.js 调用
window.showAbortButton = showAbortButton;

/**
 * 隐藏中止按钮（生成完成时调用）
 */
function hideAbortButton() {
  const btn = document.getElementById("abortGameBtn");
  if (btn) {
    btn.style.display = "none";
    btn.disabled = true;
  }
}
window.hideAbortButton = hideAbortButton;

/**
 * HTML 实体转义
 * @param {string} str
 * @returns {string}
 */
function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}

/**
 * 下载 Canon JSON 模板
 */
function downloadCanonTemplate() {
  const template = {
    "meta": {
      "title": "我的小说",
      "author": "作者名",
      "genre": ["奇幻"],
      "extraction_confidence": 1.0,
      "extraction_timestamp": new Date().toISOString()
    },
    "title": "我的小说",
    "author": "",
    "characters": [
      {
        "id": "char_001",
        "name": "主角名",
        "aliases": [],
        "role": "主角",
        "personality": {
          "traits": ["勇敢", "善良"],
          "speech_style": "直率",
          "core_motivation": "保护家人",
          "core_fear": "失去",
          "moral_alignment": "善良"
        },
        "appearance": "",
        "abilities": [],
        "relationships": [],
        "first_appearance": "",
        "key_traits": [],
        "anti_rules": []
      }
    ],
    "locations": [
      {
        "id": "loc_001",
        "name": "主要地点",
        "type": "城市",
        "description": "",
        "atmosphere": ""
      }
    ],
    "world_rules": {
      "era": "",
      "magic_system": {},
      "society": {},
      "species": []
    },
    "timeline": []
  };

  const blob = new Blob([JSON.stringify(template, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = 'canon_template.json';
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

// ═══════════════════════════════════════════════════════
// 启动
// ═══════════════════════════════════════════════════════

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', init);
} else {
  init();
}
