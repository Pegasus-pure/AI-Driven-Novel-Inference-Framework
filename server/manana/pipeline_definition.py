"""
pipeline_definition.py — 管线结构定义 + 配置说明

本文件是管线配置的唯一数据源（Single Source of Truth）。
前端通过 /api/config/define 和 /api/pipeline/nodes-meta 动态获取。
"""

from typing import List, Dict, Any

# ═══════════════════════════════════════════════════
# 管线树结构（只读，用于前端可视化）
# ═══════════════════════════════════════════════════

PIPELINE_TREE: List[Dict[str, Any]] = [
    {
        "id": "context",
        "icon": "📋",
        "label": "上下文构建",
        "agent": "ContextBuilder",
        "tier": "python",
        "desc": "注入记忆、冲突种子、微观反馈",
        "children": ["director"],
    },
    {
        "id": "director",
        "icon": "🎭",
        "label": "场景导演",
        "agent": "SceneDirector",
        "tier": "strong",
        "desc": "多路径（best_of_3 / multi_view / 标准）",
        "children": ["continuity", "motivation"],
        "conditional": True,
    },
    {
        "id": "continuity",
        "icon": "🔍",
        "label": "连续性审计",
        "agent": "ContinuityChecker",
        "tier": "medium",
        "desc": "逻辑一致性检查，失败重试",
        "children": ["motivation"],
        "optional": True,
    },
    {
        "id": "motivation",
        "icon": "🧠",
        "label": "动机分析",
        "agent": "MotivationEngine",
        "tier": "medium",
        "desc": "N 角色并行，独立 LLM provider",
        "children": ["dialogue"],
        "parallel": True,
    },
    {
        "id": "dialogue",
        "icon": "💬",
        "label": "对话/动作",
        "agent": "DialogueWeaver + ActionDirector",
        "tier": "light",
        "desc": "N×2 并行生成",
        "children": ["reflection"],
        "parallel": True,
    },
    {
        "id": "reflection",
        "icon": "✨",
        "label": "角色反思",
        "agent": "RoleReflector",
        "tier": "light",
        "desc": "状态跳跃检测，NEED_REWRITE 触发重写",
        "children": ["composer"],
        "optional": True,
    },
    {
        "id": "composer",
        "icon": "✏️",
        "label": "场景编剧",
        "agent": "SceneComposer",
        "tier": "strong",
        "desc": "精益循环（refinement 开关）",
        "children": ["auditor"],
    },
    {
        "id": "auditor",
        "icon": "📋",
        "label": "一致性验收",
        "agent": "ConsistencyAuditor",
        "tier": "medium",
        "desc": "verdict + overall_quality",
        "children": ["state"],
        "parallelWith": ["micro_oracle", "character_mgr", "location_mgr"],
    },
    {
        "id": "state",
        "icon": "🔄",
        "label": "状态提取",
        "agent": "StateExtractor",
        "tier": "light",
        "desc": "reputation/mood/location/knowledge",
        "children": ["thread_mgr"],
    },
    {
        "id": "micro_oracle",
        "icon": "🔮",
        "label": "微观神谕",
        "agent": "MicroOracleAgent",
        "tier": "light",
        "desc": "每拍质量反馈（micro_oracle 开关）",
        "children": ["thread_mgr"],
        "optional": True,
    },
    {
        "id": "character_mgr",
        "icon": "👤",
        "label": "角色管理",
        "agent": "CharacterManager",
        "tier": "light",
        "desc": "涌现实体检测（emergence_system 开关）",
        "children": ["thread_mgr"],
        "optional": True,
    },
    {
        "id": "location_mgr",
        "icon": "🗺️",
        "label": "地点管理",
        "agent": "LocationManager",
        "tier": "light",
        "desc": "涌现实体检测（emergence_system 开关）",
        "children": ["thread_mgr"],
        "optional": True,
    },
    {
        "id": "thread_mgr",
        "icon": "🧵",
        "label": "线索管理",
        "agent": "ThreadManager",
        "tier": "medium",
        "desc": "线索生命周期管理",
        "children": ["apply_state"],
    },
    {
        "id": "apply_state",
        "icon": "💾",
        "label": "状态应用",
        "agent": "Python",
        "tier": "python",
        "desc": "写入 world_state",
        "children": ["oracle"],
    },
    {
        "id": "oracle",
        "icon": "🔮",
        "label": "宏观神谕",
        "agent": "ReflectionOracle",
        "tier": "strong",
        "desc": "每 N 拍评估（oracle_interval）",
        "children": [],
        "optional": True,
    },
]



# ═══════════════════════════════════════════════════
# 辅助函数
# ═══════════════════════════════════════════════════

# ═══════════════════════════════════════════════════
# 配置说明定义（前端注释的唯一数据源）
# ═══════════════════════════════════════════════════
#
# 前端所有设置的注释/说明从此处动态读取，不再硬编码。
# 键格式：  "section.key" 或 "section.sub.key"
# 值字段：
#   - label:   前端显示的标签名
#   - desc:     详细说明（支持 \n 换行）
#   - section:  所属配置段（用于前端分组）
#   - type:     值类型（bool/int/float/str/list）
#   - default:   默认值
#   - advanced: 是否高级设置（默认 False，高级设置可折叠）
# ═══════════════════════════════════════════════════

CONFIG_DEFINE: Dict[str, Dict[str, Any]] = {

    # ─────────────────────────────────────────────
    # app 段
    # ─────────────────────────────────────────────
    "app.title": {
        "label": "应用标题",
        "desc": "浏览器标题栏和页面顶部显示的名称",
        "section": "app",
        "type": "str",
        "default": "Rain",
        "advanced": False,
    },
    "app.host": {
        "label": "监听地址",
        "desc": "127.0.0.1 = 仅本机访问\n0.0.0.0 = 允许局域网访问",
        "section": "app",
        "type": "str",
        "default": "127.0.0.1",
        "advanced": False,
    },
    "app.port": {
        "label": "监听端口",
        "desc": "服务启动后访问 http://host:port",
        "section": "app",
        "type": "int",
        "default": 8000,
        "advanced": False,
    },

    # ─────────────────────────────────────────────
    # providers 段（3 个智能层）
    # ─────────────────────────────────────────────
    "providers.导演层.type": {
        "label": "提供商类型",
        "desc": "ollama = 本地 Ollama\nopenai = OpenAI API\nanthropic = Anthropic API",
        "section": "providers",
        "type": "str",
        "default": "ollama",
        "advanced": False,
    },
    "providers.导演层.endpoint": {
        "label": "API 地址",
        "desc": "Ollama 默认 http://127.0.0.1:11434\nOpenAI 默认 https://api.openai.com/v1",
        "section": "providers",
        "type": "str",
        "default": "",
        "advanced": False,
    },
    "providers.导演层.model": {
        "label": "模型名称",
        "desc": "Ollama：qwen3.5:9b / llama3.1:8b 等\nOpenAI：gpt-4o / gpt-4-turbo 等",
        "section": "providers",
        "type": "str",
        "default": "",
        "advanced": False,
    },
    "providers.导演层.api_key": {
        "label": "API 密钥",
        "desc": "Ollama 留空\nOpenAI/Anthropic 填对应密钥",
        "section": "providers",
        "type": "str",
        "default": "",
        "advanced": False,
    },
    "providers.导演层.temperature": {
        "label": "温度系数",
        "desc": "0.0 = 确定性强（适合规划）\n1.0 = 创造性强（适合叙事）",
        "section": "providers",
        "type": "float",
        "default": 0.7,
        "advanced": False,
    },
    "providers.导演层.max_tokens": {
        "label": "最大 Token 数",
        "desc": "单次生成的最大 token 数\n导演层需要较多 token 用于规划",
        "section": "providers",
        "type": "int",
        "default": 4096,
        "advanced": False,
    },
    "providers.导演层.timeout": {
        "label": "请求超时（秒）",
        "desc": "超过此时间未完成则取消请求\n导演层模型较慢，建议 180 秒",
        "section": "providers",
        "type": "int",
        "default": 180,
        "advanced": True,
    },

    # 演员层（复用结构，仅改默认值）
    "providers.演员层.type": {
        "label": "提供商类型",
        "desc": "ollama = 本地 Ollama\nopenai = OpenAI API\nanthropic = Anthropic API",
        "section": "providers",
        "type": "str",
        "default": "ollama",
        "advanced": False,
    },
    "providers.演员层.endpoint": {
        "label": "API 地址",
        "desc": "Ollama 默认 http://127.0.0.1:11434",
        "section": "providers",
        "type": "str",
        "default": "",
        "advanced": False,
    },
    "providers.演员层.model": {
        "label": "模型名称",
        "desc": "演员层负责动机分析和对话生成",
        "section": "providers",
        "type": "str",
        "default": "",
        "advanced": False,
    },
    "providers.演员层.api_key": {
        "label": "API 密钥",
        "desc": "Ollama 留空",
        "section": "providers",
        "type": "str",
        "default": "",
        "advanced": False,
    },
    "providers.演员层.temperature": {
        "label": "温度系数",
        "desc": "0.7 = 平衡创造性与确定性",
        "section": "providers",
        "type": "float",
        "default": 0.7,
        "advanced": False,
    },
    "providers.演员层.max_tokens": {
        "label": "最大 Token 数",
        "desc": "对话生成较短，1024-2048 足够",
        "section": "providers",
        "type": "int",
        "default": 2048,
        "advanced": False,
    },
    "providers.演员层.timeout": {
        "label": "请求超时（秒）",
        "desc": "演员层并行生成，建议 120 秒",
        "section": "providers",
        "type": "int",
        "default": 120,
        "advanced": True,
    },

    # 动作层
    "providers.动作层.type": {
        "label": "提供商类型",
        "desc": "ollama = 本地 Ollama",
        "section": "providers",
        "type": "str",
        "default": "ollama",
        "advanced": False,
    },
    "providers.动作层.endpoint": {
        "label": "API 地址",
        "desc": "Ollama 默认 http://127.0.0.1:11434",
        "section": "providers",
        "type": "str",
        "default": "",
        "advanced": False,
    },
    "providers.动作层.model": {
        "label": "模型名称",
        "desc": "动作层负责状态提取，不需要强模型",
        "section": "providers",
        "type": "str",
        "default": "",
        "advanced": False,
    },
    "providers.动作层.api_key": {
        "label": "API 密钥",
        "desc": "Ollama 留空",
        "section": "providers",
        "type": "str",
        "default": "",
        "advanced": False,
    },
    "providers.动作层.temperature": {
        "label": "温度系数",
        "desc": "0.5 = 低温度，保证状态提取准确性",
        "section": "providers",
        "type": "float",
        "default": 0.5,
        "advanced": False,
    },
    "providers.动作层.max_tokens": {
        "label": "最大 Token 数",
        "desc": "状态提取输出较短，1024 足够",
        "section": "providers",
        "type": "int",
        "default": 1024,
        "advanced": False,
    },
    "providers.动作层.timeout": {
        "label": "请求超时（秒）",
        "desc": "动作层模型较快，60 秒足够",
        "section": "providers",
        "type": "int",
        "default": 60,
        "advanced": True,
    },

    # ─────────────────────────────────────────────
    # features 段（功能开关）
    # ─────────────────────────────────────────────
    "features.refinement": {
        "label": "叙事精益循环",
        "desc": "编剧层根据审计反馈多轮重写\nwarning → 重写 1 次\nFAIL → 重写 2 次\n影响：提升叙事质量，但增加 API 调用",
        "section": "features",
        "type": "bool",
        "default": True,
        "advanced": False,
    },
    "features.best_of_3": {
        "label": "导演多候选",
        "desc": "导演层生成 3 个候选 plan\nPlanScorer 选最优\n影响：提升场景规划质量，但增加 3 倍 API 调用",
        "section": "features",
        "type": "bool",
        "default": True,
        "advanced": False,
    },
    "features.multi_view": {
        "label": "多视角导演",
        "desc": "plot-driven + character-driven 双路径融合\n影响：叙事更丰富，但增加 API 调用和合并逻辑",
        "section": "features",
        "type": "bool",
        "default": False,
        "advanced": True,
    },
    "features.dynamic_tier": {
        "label": "动态智能层",
        "desc": "按场景复杂度自动调整 Agent 层分配\n简单场景 → 降级到轻量模型\n复杂场景 → 升级到强模型\n影响：节省 API 成本，但增加调度复杂度",
        "section": "features",
        "type": "bool",
        "default": False,
        "advanced": True,
    },
    "features.micro_oracle": {
        "label": "微观神谕",
        "desc": "每拍生成质量反馈，注入下一拍上下文\n影响：提升长期叙事一致性，但增加 API 调用",
        "section": "features",
        "type": "bool",
        "default": True,
        "advanced": False,
    },
    "features.semantic_selection": {
        "label": "语义选择",
        "desc": "使用语义相似度而非随机采样选择候选\n影响：提升候选多样性，但需要嵌入模型支持",
        "section": "features",
        "type": "bool",
        "default": False,
        "advanced": True,
    },
    "features.emergence_system": {
        "label": "涌现实体系统",
        "desc": "自动检测并纳入新角色/地点\n影响：世界更动态，但可能增加不可控性",
        "section": "features",
        "type": "bool",
        "default": True,
        "advanced": False,
    },
    "features.continuity_check": {
        "label": "连续性检查",
        "desc": "导演 plan 逻辑一致性审计\n影响：减少剧情矛盾，但增加 API 调用",
        "section": "features",
        "type": "bool",
        "default": True,
        "advanced": False,
    },
    "features.role_reflection": {
        "label": "角色反思",
        "desc": "检测角色状态跳跃，触发自动重写\n影响：提升角色一致性，但增加 API 调用",
        "section": "features",
        "type": "bool",
        "default": True,
        "advanced": False,
    },
    "features.memory_system": {
        "label": "记忆系统",
        "desc": "注入长期记忆 + 结尾写入事件摘要\n影响：提升长期叙事连贯性，但增加存储和检索开销",
        "section": "features",
        "type": "bool",
        "default": True,
        "advanced": False,
    },
    "features.prompt_optimization": {
        "label": "Prompt 自优化",
        "desc": "积累高奖励样本，自动生成优化 Prompt\n影响：长期自我迭代，但需要足够样本（≥50）才生效",
        "section": "features",
        "type": "bool",
        "default": False,
        "advanced": True,
    },

    # ─────────────────────────────────────────────
    # game 段
    # ─────────────────────────────────────────────
    "game.oracle_interval": {
        "label": "神谕间隔",
        "desc": "每 N 拍触发 1 次宏观神谕评估\n建议 5-10 拍，太频繁会打断叙事",
        "section": "game",
        "type": "int",
        "default": 5,
        "advanced": False,
    },
    "game.auto_save_interval": {
        "label": "自动保存间隔",
        "desc": "每 N 拍自动保存 1 次世界状态\n建议 10-20 拍，平衡性能与安全性",
        "section": "game",
        "type": "int",
        "default": 10,
        "advanced": False,
    },
    "game.max_reconnect_attempts": {
        "label": "最大重连次数",
        "desc": "WebSocket 断开后最多重连 N 次\n超过后需要手动刷新页面",
        "section": "game",
        "type": "int",
        "default": 5,
        "advanced": True,
    },

    # ─────────────────────────────────────────────
    # emergence 段
    # ─────────────────────────────────────────────
    "emergence.hit_threshold": {
        "label": "提及阈值",
        "desc": "实体被提及 N 次后触发纳入检测\n建议 3-5 次，避免噪声",
        "section": "emergence",
        "type": "int",
        "default": 3,
        "advanced": False,
    },
    "emergence.similarity_threshold": {
        "label": "相似度阈值",
        "desc": "实体合并的相似度阈值（0.0-1.0）\n越高 = 越严格（减少误合并）\n越低 = 越宽松（可能误合并）",
        "section": "emergence",
        "type": "float",
        "default": 0.75,
        "advanced": True,
    },
    "emergence.feature_extraction": {
        "label": "特征提取方式",
        "desc": "llm = 使用 LLM 提取（更准确）\nregex = 使用正则提取（更快）",
        "section": "emergence",
        "type": "str",
        "default": "llm",
        "advanced": True,
    },
    "emergence.max_pending_entities": {
        "label": "最大待处理实体数",
        "desc": "超过此数量会丢弃最旧的实体\n建议 50-100，避免内存溢出",
        "section": "emergence",
        "type": "int",
        "default": 50,
        "advanced": True,
    },

    # ─────────────────────────────────────────────
    # continuity 段
    # ─────────────────────────────────────────────
    "continuity.max_rewrite": {
        "label": "最大重写次数",
        "desc": "连续性检查失败后最多重写 N 次\n避免无限循环，建议 2-3 次",
        "section": "continuity",
        "type": "int",
        "default": 2,
        "advanced": False,
    },
    "continuity.tier": {
        "label": "使用的智能层",
        "desc": "演员层 = 平衡性能与质量\n导演层 = 更高质量，但增加成本",
        "section": "continuity",
        "type": "str",
        "default": "演员层",
        "advanced": True,
    },

    # ─────────────────────────────────────────────
    # reflection 段
    # ─────────────────────────────────────────────
    "reflection.tier": {
        "label": "使用的智能层",
        "desc": "动作层 = 快速检测\n演员层 = 更精准，但增加成本",
        "section": "reflection",
        "type": "str",
        "default": "动作层",
        "advanced": True,
    },
    "reflection.check_clothing": {
        "label": "检查服装状态",
        "desc": "启用后检测角色服装是否突然变化",
        "section": "reflection",
        "type": "bool",
        "default": True,
        "advanced": False,
    },
    "reflection.check_location": {
        "label": "检查地点状态",
        "desc": "启用后检测角色地点是否突然变化",
        "section": "reflection",
        "type": "bool",
        "default": True,
        "advanced": False,
    },
    "reflection.check_mood": {
        "label": "检查情绪状态",
        "desc": "启用后检测角色情绪是否突然变化",
        "section": "reflection",
        "type": "bool",
        "default": True,
        "advanced": False,
    },
    "reflection.check_relationship": {
        "label": "检查关系状态",
        "desc": "启用后检测角色关系是否突然变化",
        "section": "reflection",
        "type": "bool",
        "default": True,
        "advanced": False,
    },

    # ─────────────────────────────────────────────
    # memory 段
    # ─────────────────────────────────────────────
    "memory.recency_weight": {
        "label": "近期记忆权重",
        "desc": "0.0-1.0，越高越重视近期事件\n建议 0.3-0.5",
        "section": "memory",
        "type": "float",
        "default": 0.4,
        "advanced": True,
    },
    "memory.relevance_weight": {
        "label": "相关性权重",
        "desc": "0.0-1.0，越高越重视与当前场景相关的记忆\n建议 0.2-0.4",
        "section": "memory",
        "type": "float",
        "default": 0.3,
        "advanced": True,
    },
    "memory.importance_weight": {
        "label": "重要性权重",
        "desc": "0.0-1.0，越高越重视高重要性记忆\n建议 0.2-0.4",
        "section": "memory",
        "type": "float",
        "default": 0.3,
        "advanced": True,
    },
    "memory.decay_lambda": {
        "label": "记忆衰减系数",
        "desc": "越大 = 记忆遗忘越快\n建议 0.01-0.1",
        "section": "memory",
        "type": "float",
        "default": 0.05,
        "advanced": True,
    },
    "memory.reflection_threshold": {
        "label": "反思触发阈值",
        "desc": "记忆数达到 N 后触发记忆反思\n建议 20-50",
        "section": "memory",
        "type": "int",
        "default": 30,
        "advanced": True,
    },
    "memory.top_k_director": {
        "label": "导演层检索数量",
        "desc": "导演层每次检索 N 条记忆\n建议 5-10",
        "section": "memory",
        "type": "int",
        "default": 5,
        "advanced": True,
    },
    "memory.top_k_character": {
        "label": "角色层检索数量",
        "desc": "角色层每次检索 N 条记忆\n建议 3-5",
        "section": "memory",
        "type": "int",
        "default": 3,
        "advanced": True,
    },
    "memory.max_entries_per_agent": {
        "label": "每 Agent 最大记忆数",
        "desc": "超过此数量会触发遗忘\n建议 100-200",
        "section": "memory",
        "type": "int",
        "default": 200,
        "advanced": True,
    },
    "memory.retrieve_recency_window": {
        "label": "检索时间窗口",
        "desc": "检索时只考虑最近 N 拍的记忆\n建议 50-100",
        "section": "memory",
        "type": "int",
        "default": 100,
        "advanced": True,
    },
    "memory.retention_window": {
        "label": "记忆保留窗口",
        "desc": "超过此数量的记忆会触发压缩\n建议 50-100",
        "section": "memory",
        "type": "int",
        "default": 50,
        "advanced": True,
    },
    "memory.low_importance_threshold": {
        "label": "低重要性阈值",
        "desc": "重要性低于此值的记忆可能被遗忘\n建议 3.0-5.0",
        "section": "memory",
        "type": "float",
        "default": 4.0,
        "advanced": True,
    },
    "memory.compact_interval": {
        "label": "记忆压缩间隔",
        "desc": "每 N 拍压缩 1 次记忆\n建议 10-20",
        "section": "memory",
        "type": "int",
        "default": 10,
        "advanced": True,
    },

    # ─────────────────────────────────────────────
    # desktop 段（pygame 版使用）
    # ─────────────────────────────────────────────
    "desktop.window_width": {
        "label": "窗口宽度",
        "desc": "pygame 版窗口宽度（像素）",
        "section": "desktop",
        "type": "int",
        "default": 1280,
        "advanced": False,
    },
    "desktop.window_height": {
        "label": "窗口高度",
        "desc": "pygame 版窗口高度（像素）",
        "section": "desktop",
        "type": "int",
        "default": 800,
        "advanced": False,
    },
    "desktop.resizable": {
        "label": "可调整大小",
        "desc": "是否允许拖拽窗口边缘调整大小",
        "section": "desktop",
        "type": "bool",
        "default": True,
        "advanced": False,
    },
    "desktop.fullscreen": {
        "label": "全屏启动",
        "desc": "是否以全屏模式启动（按 F11 可切换）",
        "section": "desktop",
        "type": "bool",
        "default": False,
        "advanced": False,
    },

    # ─────────────────────────────────────────────
    # truncation 段
    # ─────────────────────────────────────────────
    "truncation.thread_context": {
        "label": "线索上下文 Token 数",
        "desc": "每个线索注入的最大 token 数\n建议 2000-4000",
        "section": "truncation",
        "type": "int",
        "default": 3000,
        "advanced": True,
    },
    "truncation.llm_extract": {
        "label": "LLM 提取最大输入 Token 数",
        "desc": "状态提取时传入 LLM 的最大 token 数\n建议 10000-20000",
        "section": "truncation",
        "type": "int",
        "default": 15000,
        "advanced": True,
    },
    "truncation.scene_context": {
        "label": "场景上下文 Token 数",
        "desc": "场景描述注入的最大 token 数\n建议 3000-5000",
        "section": "truncation",
        "type": "int",
        "default": 4000,
        "advanced": True,
    },
    "truncation.narrative_history": {
        "label": "叙事历史 Token 数",
        "desc": "历史叙事注入的最大 token 数\n建议 1000-3000",
        "section": "truncation",
        "type": "int",
        "default": 2000,
        "advanced": True,
    },

    # ─────────────────────────────────────────────
    # reward 段
    # ─────────────────────────────────────────────
    "reward.enabled": {
        "label": "启用奖励跟踪",
        "desc": "关闭后不计算奖励分数（提升性能）",
        "section": "reward",
        "type": "bool",
        "default": True,
        "advanced": False,
    },
    "reward.log_path": {
        "label": "奖励日志路径",
        "desc": "奖励日志保存位置（相对项目根目录）",
        "section": "reward",
        "type": "str",
        "default": "server/manana/metrics/reward_log.jsonl",
        "advanced": True,
    },
    "reward.weights.auditor_score": {
        "label": "审计分数权重",
        "desc": "一致性审计分数的权重（0.0-1.0）\n所有权重总和应为 1.0",
        "section": "reward",
        "type": "float",
        "default": 0.3,
        "advanced": True,
    },
    "reward.weights.micro_oracle_health": {
        "label": "微观神谕健康度权重",
        "desc": "微观神谕健康度分数的权重",
        "section": "reward",
        "type": "float",
        "default": 0.2,
        "advanced": True,
    },
    "reward.weights.narrative_tension": {
        "label": "叙事张力权重",
        "desc": "叙事张力分数的权重",
        "section": "reward",
        "type": "float",
        "default": 0.2,
        "advanced": True,
    },
    "reward.weights.canon_adherence": {
        "label": "设定集遵循度权重",
        "desc": "设定集遵循度分数的权重",
        "section": "reward",
        "type": "float",
        "default": 0.2,
        "advanced": True,
    },
    "reward.weights.issue_penalty": {
        "label": "问题惩罚权重",
        "desc": "问题惩罚的权重（负值）",
        "section": "reward",
        "type": "float",
        "default": 0.1,
        "advanced": True,
    },

    # ─────────────────────────────────────────────
    # prompt_optimization 段
    # ─────────────────────────────────────────────
    "prompt_optimization.enabled": {
        "label": "启用 Prompt 优化",
        "desc": "需要在 features 段也开启 prompt_optimization",
        "section": "prompt_optimization",
        "type": "bool",
        "default": False,
        "advanced": False,
    },
    "prompt_optimization.provider": {
        "label": "使用的智能层",
        "desc": "优化 Prompt 时使用的智能层\n建议用导演层（最强模型）",
        "section": "prompt_optimization",
        "type": "str",
        "default": "导演层",
        "advanced": False,
    },
    "prompt_optimization.high_reward_threshold": {
        "label": "高奖励阈值",
        "desc": "奖励分数 ≥ 此值才纳入优化样本\n建议 0.6-0.8",
        "section": "prompt_optimization",
        "type": "float",
        "default": 0.7,
        "advanced": True,
    },
    "prompt_optimization.min_samples_for_optimization": {
        "label": "最小优化样本数",
        "desc": "积累 N 个高奖励样本后才触发优化\n建议 50-100",
        "section": "prompt_optimization",
        "type": "int",
        "default": 50,
        "advanced": True,
    },
    "prompt_optimization.optimization_interval": {
        "label": "优化间隔",
        "desc": "每 N 拍优化 1 次 Prompt\n建议 50-100",
        "section": "prompt_optimization",
        "type": "int",
        "default": 50,
        "advanced": True,
    },

    # ─────────────────────────────────────────────
    # composer 段
    # ─────────────────────────────────────────────
    "composer.best_of_n.enabled": {
        "label": "启用 Best-of-N",
        "desc": "编剧层生成 N 个候选，选最优\n与 features.best_of_3 不同（那是导演层）",
        "section": "composer",
        "type": "bool",
        "default": False,
        "advanced": True,
    },
    "composer.best_of_n.sample_count": {
        "label": "候选数量",
        "desc": "生成 N 个候选，选最优\n建议 3-5",
        "section": "composer",
        "type": "int",
        "default": 3,
        "advanced": True,
    },
    "composer.best_of_n.temperatures": {
        "label": "温度列表",
        "desc": "不同候选使用不同温度，制造多样性\n建议 [0.5, 0.7, 0.9]",
        "section": "composer",
        "type": "list",
        "default": [0.5, 0.7, 0.9],
        "advanced": True,
    },
}


def get_config_define() -> Dict[str, Dict[str, Any]]:
    """返回配置说明定义（供 API 调用）"""
    return CONFIG_DEFINE


# ════════════════════════════════════════════════════════
# 管线节点元数据（供前端管线图、状态条显示）
# ════════════════════════════════════════════════════════

PIPELINE_NODES_META: Dict[str, Dict[str, Any]] = {
    "context": {
        "label": "上下文构建",
        "desc": "注入记忆·冲突·微反馈",
        "icon": "📋",
        "emoji": "📋",
        "tier": "python",
    },
    "director": {
        "label": "场景导演",
        "desc": "多路径策略(best_of_3/multi_view)",
        "icon": "🎭",
        "emoji": "🎭",
        "tier": "strong",
    },
    "continuity": {
        "label": "连续性审计",
        "desc": "逻辑一致+失败重试",
        "icon": "🔍",
        "emoji": "🔍",
        "tier": "medium",
    },
    "motivation": {
        "label": "动机分析",
        "desc": "N角色并行·独立Provider",
        "icon": "🧠",
        "emoji": "🧠",
        "tier": "medium",
    },
    "dialogue": {
        "label": "对话/动作",
        "desc": "Nx2 并行生成",
        "icon": "💬",
        "emoji": "💬",
        "tier": "light",
    },
    "reflection": {
        "label": "角色反思",
        "desc": "状态跳跃·NEED_REWRITE",
        "icon": "✨",
        "emoji": "✨",
        "tier": "light",
    },
    "composer": {
        "label": "场景编剧",
        "desc": "精益循环(重试2次)",
        "icon": "✏️",
        "emoji": "✏️",
        "tier": "strong",
    },
    "auditor": {
        "label": "一致性验收",
        "desc": "verdict+overall_quality",
        "icon": "📋",
        "emoji": "📋",
        "tier": "medium",
    },
    "state": {
        "label": "状态提取",
        "desc": "reputation/mood/loc/knowledge",
        "icon": "🔄",
        "emoji": "🔄",
        "tier": "light",
    },
    "micro_oracle": {
        "label": "微观神谕",
        "desc": "每拍质量反馈注入",
        "icon": "🔮",
        "emoji": "🔮",
        "tier": "light",
    },
    "character_mgr": {
        "label": "角色管理",
        "desc": "涌现实体检测",
        "icon": "👤",
        "emoji": "👤",
        "tier": "light",
    },
    "location_mgr": {
        "label": "地点管理",
        "desc": "涌现实体检测",
        "icon": "🗺️",
        "emoji": "🗺️",
        "tier": "light",
    },
    "thread_mgr": {
        "label": "线索管理",
        "desc": "线索生命周期管理",
        "icon": "🧵",
        "emoji": "🧵",
        "tier": "medium",
    },
    "apply_state": {
        "label": "状态应用",
        "desc": "写入 world_state",
        "icon": "💾",
        "emoji": "💾",
        "tier": "python",
    },
    "oracle": {
        "label": "宏观神谕",
        "desc": "每N拍评估(oracle_interval)",
        "icon": "🔮",
        "emoji": "🔮",
        "tier": "strong",
    },
}


def get_pipeline_nodes_meta() -> Dict[str, Dict[str, Any]]:
    """返回管线节点的元数据（供 API 调用）"""
    return PIPELINE_NODES_META
