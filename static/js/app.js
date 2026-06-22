/**
 * app.js — Rain Web 前端入口
 *
 * 全局应用状态 + 事件总线 + 初始化 + 模块导入编排
 * + 小说选择流程状态机
 *
 * 架构: 单例 AppState 模式 — 所有模块通过 App.state 共享状态，
 *       通过 App.on/App.emit 松耦合通信。
 *
 * 面板快捷键:
 *   F1 → 剧情    F2 → 世界观    F3 → 角色    F4 → 地点
 *   F5 → 日志    F6 → 存档      F7 → 设置
 */

// ═══════════════════════════════════════════════════════
// 导入所有模块
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
import { UnifiedFSM } from './fsm.js';
import { SettingsUI } from './settings-ui.js';

// ═══════════════════════════════════════════════════════
// 全局应用状态
// ═══════════════════════════════════════════════════════

class AppState {
  constructor() {
    /** @type {Object} 全局游戏状态 */
    this.state = {
      sessionId: '',
      activePanel: 'narrative',
      beatCount: 0,
      deviation: 0.0,
      isTyping: false,
      isConnected: false,
      isChoosing: false,
      gameTime: '初始',
      playerLocation: '',
      charactersState: {},
      eventLog: [],
      actionHints: [],
      canonReady: false,
      novelTitle: '',
      worldRules: {},
      canonMeta: {},
      canonSource: 'initial',

      // ── UI 显示模式 ──
      statusDisplayMode: 'bubbles',  // 'bubbles' | 'label'

      // ── 新增：游戏阶段状态 ──
      gamePhase: 'awaiting_start',     // 'awaiting_start' | 'generating' | 'playing'

      // ── 新增：小说选择流程状态 ──
      novelSelectPhase: 'idle',       // 'idle' | 'scanning' | 'list_received' | 'confirming'
                                      // | 'selecting' | 'generating' | 'ready'
      generationStartTime: null,      // Date.now() 生成开始时间
      generationTimerId: null,        // 120s 超时定时器 ID
      generationElapsedInterval: null, // 每秒更新已用时的 interval ID
      hasExistingCanon: false,        // 是否存在已生成的 canon
      availableTxtFiles: [],          // novel/ 下的 .txt 列表
      availableCanons: [],            // novel/ 下的 canon_*.json 列表
      isMidGame: false,               // 游戏中禁止切换（beatCount > 0）
      selectedCanonFile: '',          // 当前选中的 canon 文件路径
    };

    /** @type {UnifiedFSM} 统一状态机（与旧 state 双写同步） */
    this.fsm = new UnifiedFSM();

    /** @type {Object<string,Function[]>} 事件总线 */
    this._listeners = {};

    // 模块实例（初始化后设置）
    this.ws = null;
    this.panels = null;
    this.deviation = null;
    this.input = null;
    this.narrative = null;
    this.characters = null;
    this.worldRules = null;
    this.locations = null;
    this.log = null;
    this.saveUI = null;
  }

  /**
   * 设置游戏阶段（双写同步：App.state + App.fsm）
   * @param {'novel_select'|'narrative'|'error'} phase 主阶段
   * @param {string} state 子状态
   * @returns {boolean} 是否转换成功
   */
  setPhase(phase, state) {
    // 同状态直接返回，避免自转换和重复事件
    if (this.fsm.phase === phase && this.fsm.state === state) {
      return true;
    }
    // 先检查 FSM 是否允许此转换
    if (!this.fsm.canTransition(phase, state)) {
      console.warn(
        `[App] setPhase: 非法转换 ${this.fsm.phase}.${this.fsm.state} → ${phase}.${state}，已忽略`,
      );
      return false;
    }
    // 1. 更新旧 App.state 兼容
    switch (phase) {
      case 'narrative':
        this.state.gamePhase = state;
        this.state.novelSelectPhase = 'idle';
        break;
      case 'novel_select':
        this.state.novelSelectPhase = state;
        this.state.gamePhase = 'awaiting_start';
        break;
      case 'error':
        this.state.novelSelectPhase = 'error';
        this.state.gamePhase = 'awaiting_start';
        break;
    }
    // 2. 更新新 FSM
    this.fsm.transition(phase, state);
    return true;
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
      try { fn(data); } catch (e) { console.error(`[App] 事件 "${event}" 出错:`, e); }
    }
  }
}

/** 全局单例 */
export const App = new AppState();

// ═══════════════════════════════════════════════════════
// 初始化
// ═══════════════════════════════════════════════════════

function init() {
  console.log('[App] Rain Web 初始化...');

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

  // 监听配置信息（预填设置面板）
  App.on('config_info', (payload) => {
    if (payload && payload.providers) {
      for (const [tier, cfg] of Object.entries(payload.providers)) {
        if (cfg.endpoint) {
          const el = document.querySelector(`[data-field="${tier}-endpoint"]`);
          if (el) el.value = cfg.endpoint;
        }
        if (cfg.model) {
          const el = document.querySelector(`[data-field="${tier}-model"]`);
          if (el) el.value = cfg.model;
        }
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
    if (payload.api_key) {
      const el = document.getElementById('cfgApiKey');
      if (el) el.value = payload.api_key;
    }
    // 更新可用模型列表（模型提示已集成在卡片 tag 中）
  });

  // ── 新增：canon_list 事件 → 决策分支 ──
  App.on('canon_list', handleCanonList);

  // ── 新增：canon_generation_status 事件 → 更新加载态 ──
  App.on('canon_generation_status', handleGenerationStatus);

  // ── 新增：canon_generation_failed 事件 → 出错恢复 ──
  App.on('canon_generation_failed', handleGenerationFailed);

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

    // 1. 更新 App.state
    App.state.beatCount = ws.beat_count || 0;
    App.state.gameTime = ws.game_time || '';
    App.state.playerLocation = ws.player_location || '';
    App.state.deviation = ws.divergence || 0;
    App.state.isMidGame = (ws.beat_count || 0) > 0;
    if (ws.session_id) App.state.sessionId = ws.session_id;

    // 更新标题栏
    document.getElementById('beatCount').textContent = App.state.beatCount;
    const titleEl = document.getElementById('titleNovel');
    const novelTitle = ws.novel_title || App.state.novelTitle || '';
    if (titleEl && novelTitle) {
      App.state.novelTitle = novelTitle;
      titleEl.textContent = '《' + novelTitle.replace(/【.*?】/g, '') + '》';
    }

    // 2. 恢复叙事区：仅渲染最后一条 event_log（全文）
    const eventLog = ws.event_log || [];
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

    // 5. 显示初始选择（让玩家可以继续）
    const defaultChoices = [
      { id: 'continue', text: '继续冒险', hint: '推进剧情发展' },
      { id: 'look_around', text: '观察周围', hint: '环顾当前场景' },
      { id: 'talk', text: '与在场角色交谈', hint: '寻找对话机会' },
    ];
    App.emit('choices_ready', defaultChoices);

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
    const titleEl = document.getElementById('titleNovel');
    if (titleEl) {
      if (payload.novel_title) {
        titleEl.textContent = '《' + payload.novel_title.replace(/【.*?】/g, '') + '》';
      } else {
        titleEl.textContent = '请选择小说';
      }
    }
    // 自动隐藏欢迎界面
    hideWelcome();
    // 激活叙事面板（确保 #choicePanel 可见）
    if (App.panels) {
      App.panels.switchPanel('narrative');
    }
    // 清除加载态
    clearGenerationLoading();
    // 设置游戏阶段为等待开始
    App.setPhase('narrative', 'awaiting_start');
    // 显示"开始冒险"按钮
    showStartButton();
    // 更新标题按钮
    updateTitleButton();
  });

  // ── T04/T05: 叙事模式更新 → 通知 deviation 和 narrative ──
  App.on('narrative_mode_update', (payload) => {
    if (payload && payload.mode) {
      App.deviation.setNarrativeMode(payload.mode);
    }
  });

  // ── Choice System: narrative_complete → 转发 choices ──
  App.on('narrative_complete', (payload) => {
    // 无论有无 choices，生成结束后都隐藏中止按钮
    hideAbortButton();
    showStartButton();

    if (payload && payload.choices && Array.isArray(payload.choices) && payload.choices.length > 0) {
      App.state.isChoosing = true;
      App.emit('choices_ready', payload.choices);
    } else {
      // 没有 choices 时也清除选择状态
      App.state.isChoosing = false;
    }
  });

  // ── 生成中止确认 ──
  App.on('generation_aborted', (payload) => {
    // 使用 transition() 进行状态转换（确保触发 fsm:change 事件）
    App.fsm.transition('novel_select', 'ready');
    App.state.gamePhase = 'awaiting_start';
    App.state.novelSelectPhase = 'ready';
    App.state.isMidGame = false;
    App.state.beatCount = 0;
    // 保留 session_id（不删除）以支持 WebSocket 重连时恢复会话
    // 恢复 UI（不回到欢迎界面，保持叙事面板 + 开始按钮）
    hideAbortButton();
    showStartButton();
    if (App.pipelineStatus) {
      App.pipelineStatus.hide();
    }
    console.log('[App] 生成已中止:', (payload && payload.message) || '');
  });

  // ── Choice System: choice_selected → 清除选择状态 ──
  App.on('choice_selected', () => {
    App.state.isChoosing = false;
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
      if (page === 'api') showPage('settingsApiPage');
      if (page === 'ui') showPage('settingsUiPage');
      if (page === 'pipeline') {
        showPage('settingsPipelinePage');
        document.dispatchEvent(new CustomEvent('settings_page_shown', { detail: { page: 'pipeline' } }));
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
    const tier = slider.dataset.field ? slider.dataset.field.split('-')[0] : '';
    const valEl = document.getElementById(tier + '-temp-val');
    if (valEl) {
      slider.addEventListener('input', () => {
        valEl.textContent = parseFloat(slider.value).toFixed(1);
      });
    }
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

  // ── 读取字段值 ──
  function getTierConfig(tier) {
    const val = (field) => {
      const el = document.querySelector(`[data-field="${tier}-${field}"]`);
      if (!el) return '';
      if (field === 'endpoint') return normalizeEndpoint(el.value.trim(), 'ollama');
      return el.value.trim();
    };
    const config = {
      type: 'ollama',
      endpoint: val('endpoint'),
      model: val('model'),
      temperature: parseFloat(val('temperature')) || 0.7,
      max_tokens: parseInt(val('max_tokens')) || 2048,
      timeout: tier === 'strong' ? 180 : tier === 'medium' ? 120 : 60,
    };
    // 读取 API 密钥（每个模型独立）
    const apiKey = val('api_key');
    if (apiKey) {
      config.api_key = apiKey;
    }
    return config;
  }

  // ── 模型卡片独立应用/重置按钮 ──
  document.querySelectorAll('.settings-tier-card__actions .settings-btn--apply').forEach(btn => {
    btn.addEventListener('click', () => {
      const tier = btn.dataset.tier;
      if (!tier) return;

      const config = getTierConfig(tier);
      if (!config.endpoint) {
        showSettingsStatus(`请填写 ${tier} 模型的 API 端点`, 'error');
        return;
      }

      if (App.ws && App.ws.isConnected()) {
        showSettingsStatus(`正在应用 ${tier} 模型配置...`, 'loading');
        // 发送单个模型的配置
        App.ws.send('update_config', { providers: { [tier]: config } });
      } else {
        showSettingsStatus('未连接到服务器，无法应用配置', 'error');
      }
    });
  });

  document.querySelectorAll('.settings-tier-card__actions .settings-btn--reset').forEach(btn => {
    btn.addEventListener('click', () => {
      const tier = btn.dataset.tier;
      if (!tier) return;

      // 重置该模型卡片的字段
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

      showSettingsStatus(`已重置 ${tier} 模型为默认值`, 'success');
    });
  });

  // ── 端点输入自动补全（blur 时触发）──
  document.querySelectorAll('[data-field$="-endpoint"]').forEach(input => {
    input.addEventListener('blur', () => {
      const raw = input.value.trim();
      if (!raw) return;
      // Ollama 类型：自动加 http:// + 默认端口 11434
      input.value = normalizeEndpoint(raw, 'ollama');
    });
  });

  // ── 读取字段值（发送前再次归一化端点）──
  function getEndpoint(tier) {
    const el = document.querySelector(`[data-field="${tier}-endpoint"]`);
    return el ? normalizeEndpoint(el.value.trim(), 'ollama') : '';
  }

  // ── 应用按钮：发送三模型配置 ──
  if (btnApply) {
    btnApply.addEventListener('click', () => {
      const apiKey = document.getElementById('cfgApiKey').value.trim();
      const configs = {
        strong: getTierConfig('strong'),
        medium: getTierConfig('medium'),
        light: getTierConfig('light'),
      };
      // 统一注入 api_key
      if (apiKey) {
        configs.strong.api_key = apiKey;
        configs.medium.api_key = apiKey;
        configs.light.api_key = apiKey;
      }

      const hasEndpoint = configs.strong.endpoint || configs.medium.endpoint || configs.light.endpoint;
      if (!hasEndpoint) {
        showSettingsStatus('请至少填写一个 API 端点', 'error');
        return;
      }

      if (App.ws && App.ws.isConnected()) {
        showSettingsStatus('正在应用配置...', 'loading');
        App.ws.send('update_config', { providers: configs, api_key: apiKey });
      } else {
        showSettingsStatus('未连接到服务器，无法应用配置', 'error');
      }
    });
  }

  // ── 重置按钮 ──
  if (btnReset) {
    btnReset.addEventListener('click', () => {
      // 新卡片字段
      document.querySelectorAll('.settings-field-input, .settings-form__input').forEach(el => {
        if (el.type === 'number') el.value = '';
        else el.value = '';
      });
      // 滑块
      document.querySelectorAll('.settings-field-slider, .settings-form__slider').forEach(s => {
        s.value = s.dataset.field && s.dataset.field.includes('light') ? '0.5' : '0.7';
        const tier = s.dataset.field ? s.dataset.field.split('-')[0] : '';
        const valEl = document.getElementById(tier + '-temp-val');
        if (valEl) valEl.textContent = parseFloat(s.value).toFixed(1);
      });
      document.getElementById('cfgApiKey').value = '';
      showSettingsStatus('已重置为默认值', 'success');
    });
  }

  // ── 配置应用成功 ──
  App.on('config_updated', (payload) => {
    showSettingsStatus('✅ 配置已应用' + (payload && payload.note ? ' · ' + payload.note : ''), 'success');
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

    // Pipeline 未初始化 → 引导用户检查 API 配置
    if (code === 'PIPELINE_FAILED') {
      console.error('[App] Pipeline 初始化失败:', message);
      alert('❌ Pipeline 初始化失败\n\n' + message + '\n\n请检查 F7 设置面板中的 API 配置是否正确。');
      // 显示设置面板
      const settingsPanel = document.getElementById('panel-settings');
      if (settingsPanel && App.panels) {
        App.panels.switchPanel('settings');
        // 直接打开 API 设置页（跳过子菜单）
        document.querySelectorAll('#panel-settings .settings-page').forEach(p => p.classList.remove('settings-page--active'));
        const apiPage = document.getElementById('settingsApiPage');
        if (apiPage) apiPage.classList.add('settings-page--active');
      }
      return;
    }

    // 生成相关错误 → 清除加载态
    if (code === 'CANON_FAILED' || code === 'INTERNAL_ERROR') {
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

  // ── 文件上传 ──
  const fileInput = document.getElementById('welcomeFileInput');
  const uploadBtn = document.querySelector('.welcome-upload-btn');
  if (uploadBtn && fileInput) {
    uploadBtn.addEventListener('click', () => fileInput.click());
    fileInput.addEventListener('change', async () => {
      const file = fileInput.files[0];
      if (!file) return;
      const text = await file.text();
      showSettingsStatus('正在导入小说...', 'loading');
      if (App.ws && App.ws.isConnected()) {
        startGenerationLoading();
        App.ws.send('upload_novel', { filename: file.name, content: text });
      }
    });
  }

  // ── 保留已有按钮 ──
  const btnKeep = document.getElementById('btnKeepCanon');
  if (btnKeep) {
    btnKeep.addEventListener('click', () => {
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

  // ── 重新生成按钮 ──
  const btnRegenerate = document.getElementById('btnRegenerateCanon');
  if (btnRegenerate) {
    btnRegenerate.addEventListener('click', () => {
      startGenerationLoading();
      // 如果有 .txt 文件，使用第一个；否则发送空，后端处理
      const txtPath = App.state.availableTxtFiles.length > 0
        ? App.state.availableTxtFiles[0].path
        : '';
      App.ws.send('regenerate_canon', { txt_path: txtPath });
    });
  }

  // ── 跳过小说选择按钮（确认弹窗中） ──
  const btnSkip = document.getElementById('btnSkipNovel');
  if (btnSkip) {
    btnSkip.addEventListener('click', enterEmptyState);
  }

  // ── 跳过小说选择按钮（选择界面中） ──
  const btnSkip2 = document.getElementById('btnSkipNovel2');
  if (btnSkip2) {
    btnSkip2.addEventListener('click', enterEmptyState);
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

  // ── 初始状态：显示欢迎界面、扫描中 ──
  App.setPhase('novel_select', 'scanning');
  const overlay = document.getElementById('welcomeOverlay');
  if (overlay) {
    overlay.style.display = 'flex';
    overlay.classList.remove('welcome-overlay--hidden');
  }
  hideAllWelcomeSections();
  const scanning = document.getElementById('initialScanning');
  if (scanning) scanning.style.display = 'flex';

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

  // ── "开始冒险"按钮 ──
  const startBtn = document.getElementById('startGameBtn');
  if (startBtn) {
    startBtn.addEventListener('click', () => {
      startBtn.disabled = true;
      hideStartButton();
      // 发送空 player_action 启动叙事
      App.setPhase('narrative', 'generating');
      App.emit('llm_busy', {});
      if (App.ws && App.ws.isConnected()) {
        App.ws.send('player_action', { text: '' });
        App.emit('player_action_sent', { text: '' });
      }
    });
  }

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
  if (App.state._scanTimeout) {
    clearTimeout(App.state._scanTimeout);
    App.state._scanTimeout = null;
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
    // 无 canon → 选择界面
    showNovelSelector(App.state.availableTxtFiles);
  }

  // 如果扫描结果为空，显示重新扫描按钮
  const hasAny = (payload.txt_files && payload.txt_files.length > 0) ||
                  (payload.canons && payload.canons.length > 0);
  if (!hasAny && btnRescan) {
    btnRescan.style.display = 'inline-block';
  }
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

  // 清空并重建列表
  list.innerHTML = '';

  if (canons.length === 0) {
    list.innerHTML = '<p style="color:#8b949e;font-size:13px;">无世界观数据</p>';
    return;
  }

  canons.forEach((canon, index) => {
    const item = document.createElement('div');
    item.className = 'confirm-canon-item';
    if (index === 0) {
      item.classList.add('confirm-canon-item--selected');
      App.state.selectedCanonFile = canon.source_file;
    }

    const metaParts = [];
    if (canon.char_count !== undefined) metaParts.push(canon.char_count + ' 角色');
    if (canon.loc_count !== undefined) metaParts.push(canon.loc_count + ' 地点');
    if (canon.generated_at) {
      try {
        const d = new Date(canon.generated_at);
        metaParts.push(d.toLocaleString('zh-CN'));
      } catch (e) {
        metaParts.push(canon.generated_at);
      }
    }

    item.innerHTML = `
      <div class="confirm-canon-item__info">
        <div class="confirm-canon-item__title">${escapeHtml(canon.title || '未命名')}</div>
        <div class="confirm-canon-item__meta">${metaParts.join(' · ') || canon.source_file}</div>
      </div>
      <div class="confirm-canon-item__radio"></div>
    `;

    item.addEventListener('click', () => {
      // 单选逻辑
      list.querySelectorAll('.confirm-canon-item').forEach(el => el.classList.remove('confirm-canon-item--selected'));
      item.classList.add('confirm-canon-item--selected');
      App.state.selectedCanonFile = canon.source_file;
    });

    list.appendChild(item);
  });
}

/**
 * 显示小说选择界面（无 canon 时）
 * @param {Array} txtFiles - .txt 文件列表
 */
function showNovelSelector(txtFiles) {
  App.setPhase('novel_select', 'selecting');

  const selector = document.getElementById('novelSelector');
  if (!selector) return;
  selector.style.display = 'block';

  // 填充 .txt 文件列表
  const list = document.getElementById('welcomeNovelList');
  if (!list) return;
  list.innerHTML = '';

  if (txtFiles.length === 0) {
    list.innerHTML = '<p style="color:#8b949e;font-size:13px;padding:8px 0;">暂无本地小说文件，请上传或导入</p>';
  } else {
    txtFiles.forEach((file) => {
      const item = document.createElement('button');
      item.className = 'welcome-novel-item';
      const sizeStr = file.size
        ? (file.size > 1024 * 1024 ? (file.size / 1024 / 1024).toFixed(1) + ' MB' : (file.size / 1024).toFixed(0) + ' KB')
        : '';
      item.innerHTML = `
        <span class="welcome-novel-item__name">📖 ${escapeHtml(file.name)}</span>
        ${sizeStr ? `<span class="welcome-novel-item__meta">${sizeStr}</span>` : ''}
      `;
      item.addEventListener('click', () => {
        startGenerationLoading();
        App.ws.send('regenerate_canon', { txt_path: file.path });
      });
      list.appendChild(item);
    });
  }
}

/**
 * 开始生成加载态
 */
function startGenerationLoading() {
  App.setPhase('novel_select', 'generating');
  App.state.generationStartTime = Date.now();

  const loading = document.getElementById('generationLoading');
  if (!loading) return;
  loading.style.display = 'flex';

  // 隐藏欢迎卡片内的其他区域
  const confirmDialog = document.getElementById('confirmDialog');
  const novelSelector = document.getElementById('novelSelector');
  const initialScanning = document.getElementById('initialScanning');
  if (confirmDialog) confirmDialog.style.display = 'none';
  if (novelSelector) novelSelector.style.display = 'none';
  if (initialScanning) initialScanning.style.display = 'none';

  // 重置文字
  const statusText = document.getElementById('generationStatusText');
  const timerText = document.getElementById('generationTimer');
  const elapsed = document.getElementById('generationElapsed');
  if (statusText) statusText.textContent = '正在分析小说角色...';
  if (timerText) timerText.style.display = 'none';
  if (elapsed) elapsed.textContent = '0';

  // 清除旧的定时器
  clearGenerationTimers();

  // 120s 超时提示
  App.state.generationTimerId = setTimeout(() => {
    const timer = document.getElementById('generationTimer');
    if (timer) timer.style.display = 'block';
  }, 120000);

  // 每秒更新已用时间
  App.state.generationElapsedInterval = setInterval(() => {
    const el = document.getElementById('generationElapsed');
    if (el && App.state.generationStartTime) {
      const secs = Math.floor((Date.now() - App.state.generationStartTime) / 1000);
      el.textContent = String(secs);
    }
  }, 1000);
}

/**
 * 清除生成加载态
 */
function clearGenerationLoading() {
  App.setPhase('novel_select', App.state.canonReady ? 'ready' : 'idle');

  const loading = document.getElementById('generationLoading');
  if (loading) loading.style.display = 'none';

  clearGenerationTimers();
}

/**
 * 清除生成相关的定时器
 */
function clearGenerationTimers() {
  if (App.state.generationTimerId) {
    clearTimeout(App.state.generationTimerId);
    App.state.generationTimerId = null;
  }
  if (App.state.generationElapsedInterval) {
    clearInterval(App.state.generationElapsedInterval);
    App.state.generationElapsedInterval = null;
  }
  App.state.generationStartTime = null;
}

/**
 * 处理 canon_generation_failed 消息 — 恢复选择界面让用户重试
 * @param {Object} payload
 */
function handleGenerationFailed(payload) {
  const message = (payload && payload.message) || '世界观数据生成失败';
  console.warn('[App] Canon 生成失败:', message);

  // 清除加载态
  clearGenerationLoading();

  // 显示小说选择界面（包含 .txt 列表 + 上传入口 + 跳过按钮）
  const overlay = document.getElementById('welcomeOverlay');
  if (overlay) {
    overlay.style.display = 'flex';
  }

  // 显示错误提示在状态文本中
  const statusText = document.getElementById('generationStatusText');
  if (statusText) {
    statusText.textContent = '';
    statusText.style.display = 'none';
  }

  // 恢复选择界面
  hideAllWelcomeSections();
  const selector = document.getElementById('novelSelector');
  if (selector) {
    selector.style.display = 'block';
    // 如果已有 canon 或 txt 文件，也显示确认弹窗
    if (App.state.hasExistingCanon && App.state.availableCanons.length > 0) {
      showConfirmDialog(App.state.availableCanons);
    } else {
      showNovelSelector(App.state.availableTxtFiles);
    }
  }

  // 显示简短的 toast 提示
  const toast = document.createElement('div');
  toast.className = 'welcome-toast';
  toast.textContent = '❌ ' + message;
  const card = document.querySelector('.welcome-card');
  if (card) {
    card.prepend(toast);
    setTimeout(() => {
      if (toast.parentNode) toast.parentNode.removeChild(toast);
    }, 5000);
  }
}
function handleGenerationStatus(payload) {
  const status = payload.status || '';
  const message = payload.message || '';

  // 更新加载态文字
  const statusText = document.getElementById('generationStatusText');
  if (statusText && message) {
    statusText.textContent = message;
  }

  // 完成或回退
  if (status === 'completed') {
    if (statusText) statusText.textContent = '✅ 世界观数据生成完成';
  } else if (status === 'fallback') {
    if (statusText) statusText.textContent = '⚠️ ' + message;
  }
  // status === 'error' 由 canon_generation_failed 事件处理完整恢复
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
  const ids = ['confirmDialog', 'novelSelector', 'initialScanning', 'generationLoading'];
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
  overlay.style.display = 'flex';
  overlay.classList.remove('welcome-overlay--hidden');

  // 如果已连接，重新请求 canon_list
  if (App.ws && App.ws.isConnected()) {
    App.setPhase('novel_select', 'scanning');
    hideAllWelcomeSections();
    const scanning = document.getElementById('initialScanning');
    if (scanning) scanning.style.display = 'flex';
    App.ws.send('request_canon_list', {});
  }
}

function hideWelcome() {
  const overlay = document.getElementById('welcomeOverlay');
  if (!overlay) return;
  overlay.classList.add('welcome-overlay--hidden');
  setTimeout(() => { overlay.style.display = 'none'; }, 350);
}

/**
 * 进入空状态：不加载任何小说，直接进入主界面
 * 角色面板和地点面板为空，标题显示「请选择小说」
 */
function enterEmptyState() {
  clearGenerationLoading();
  App.setPhase('novel_select', 'idle');
  App.state.canonReady = false;
  App.state.novelTitle = '';
  // 直接隐藏欢迎界面，不加载任何 canon
  hideWelcome();
  // 标题设为请选择小说
  const titleEl = document.getElementById('titleNovel');
  if (titleEl) {
    titleEl.textContent = '请选择小说';
  }
  // 更新标题按钮状态
  updateTitleButton();
}

/**
 * 显示"开始冒险"按钮（替代旧的 Enter 触发）
 */
function showStartButton() {
  const btn = document.getElementById('startGameBtn');
  if (btn) {
    btn.style.display = 'flex';
    btn.disabled = false;
  }
}

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
// beforeunload 清理
// ═══════════════════════════════════════════════════════

window.addEventListener('beforeunload', () => {
  clearGenerationTimers();
});

// ═══════════════════════════════════════════════════════
// 启动
// ═══════════════════════════════════════════════════════

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', init);
} else {
  init();
}
