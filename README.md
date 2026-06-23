# Round — AI 叙事小说模拟器

沉浸式 AI 叙事体验平台。玩家以灵魂附生的方式进入小说世界，通过"本我/贴合"二元选择驱动剧情发展，NPC 会逐步察觉异样行为并产生认知冲突。

## 快速开始

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 配置 API
# 编辑 config.yaml，填入你的 DeepSeek API Key
# providers.strong/medium/light.api_key: YOUR_DEEPSEEK_API_KEY

# 3. 启动
python launcher.py

# 4. 打开浏览器
# http://127.0.0.1:8000
```

## 技术架构

```
浏览器 ←→ WebSocket ←→ FastAPI ←→ MaNA v4 多智能体管线
                                       ↓
                                  15 Agent 分层协作
                                  DeepSeek API / Ollama
```

### MaNA 管线架构

管线分 6 层，每轮叙事节拍（Beat）经过 15 个 Agent 协作产出：

| 层 | Agent | 职责 |
|----|-------|------|
| L0 | ContextBuilder | 构建上下文（角色、记忆、线索） |
| L1 | Director | 场景导演：选角、叙事模式、节拍规划 |
| L1B | ContinuityChecker | 逻辑一致性审计，失败回退 |
| L2R1 | Motivation × N | 各角色动机生成（并行） |
| L2R2 | Dialogue × N + Action × N | 对话 + 动作生成（并行） |
| L3 | Composer + Auditor | 叙事合成 + 质量评分 |
| L3B | MicroOracle + Extractor | 质量反馈 + 状态抽取 |
| L4A | StateExtractor | 世界状态更新 |
| L4B | ThreadManager | 叙事线索管理 |
| L5 | Oracle | 深度反思（每 5 拍） |

**Tier 分级**：
- **strong**：核心创作（Director / Composer / Oracle）
- **medium**：角色引擎、一致性检查
- **light**：质量反馈、状态抽取

## 完整流程

### 1. 选择小说
欢迎界面可以选择已有的 Canon JSON 文件，或导入新的，或 **从头创建**。
从头创建模式下，手动填入角色、地点和世界观。

### 2. 选角色（灵魂附生）
选择一名小说角色作为"宿主"。你的玩家灵魂会附身其上，与 NPC 互动。

### 3. 生成叙事
系统自动生成 10 拍叙事（人格积累期），之后每 3 拍弹出"本我/贴合"选择：

```
本我选择（authentic）  →  以玩家性格行动
                       →  积累认知冲突
                       →  NPC 逐渐察觉异常

贴合选择（conforming） →  模仿原主行为
                       →  维持身份一致性
                       →  不触发认知冲突
```

NPC 认知冲突达到阈值时，会触发"发现异常"的对话事件。

### 4. 继续游戏
每轮选择后管线生成新一拍叙事，世界状态持续演化。

## 设置面板 (F7)

| 分类 | 内容 |
|------|------|
| API 设置 | 三档 LLM 配置（类型/端点/模型/密钥/温度/Token/超时） |
| 功能开关 | 11 个管线特性开关（精益循环、导演多候选、微观神谕等） |
| UI 设置 | 字体大小、背景色主题、状态显示模式 |

所有设置通过后端 WebSocket 消息 `set_provider` 和 REST API `/api/config/features` 持久化到 `config.yaml`。

## 数据与面板

| 快捷键 | 面板 | 功能 |
|:---:|------|------|
| F0 | 仪表盘 | 回合数、游戏时间、当前位置、事件日志 |
| F1 | 叙事 | AI 实时生成的故事文本 + 本我/贴合选项 |
| F2 | 角色 | 角色列表、编辑、在场角色侧栏 |
| F3 | 地点 | 地点列表、编辑 |
| F4 | 世界观 | 世界规则编辑（时代/社会/物种等） |
| F5 | 存档 | 3 槽位存档/读档 |
| F6 | 日志 | 系统运行日志 |
| F7 | 设置 | API 配置、功能开关、UI 设置 |
| F8 | 线索 | 叙事线索追踪（活跃/已演化） |
| F9 | 关系网 | NPC 关系网络可视化 |
| 右侧 | 灵魂面板 | 玩家/角色双魂状态、NPC 认知冲突 |

## 技术栈

| 层 | 技术 |
|----|------|
| 后端 | FastAPI (Python), WebSocket |
| 前端 | 纯 JS ES Module, EventBus 通信 |
| LLM | DeepSeek API, Ollama 本地 |
| 配置 | YAML (config.yaml) |
| Canon | 目录结构（`novel/{title}/`） |

## 项目结构

```
Round/
├── config.yaml          # 全局配置 (API/功能/游戏参数)
├── launcher.py          # 入口
├── server/
│   ├── main.py          # FastAPI + WebSocket 主路由
│   ├── app/             # GameSession, WorldState
│   ├── manana/          # MaNA v4 管线引擎
│   │   ├── agents/      # 15 Agent 实现
│   │   └── soul/        # 灵魂附生系统
│   ├── data/            # Canon 管理、存档
│   ├── storage/         # 存储后端抽象
│   └── mcp/             # MCP 服务
├── static/
│   ├── index.html       # 单页应用入口
│   ├── js/              # 前端模块 (ES Module)
│   │   └── soul/        # 灵魂系统 UI
│   └── css/             # 样式
└── novel/               # 小说 Canon 数据
    ├── canon_*.json     # Canon JSON 文件
    └── {title}/         # 小说目录结构 (运行 Canon)
```

## License

MIT
