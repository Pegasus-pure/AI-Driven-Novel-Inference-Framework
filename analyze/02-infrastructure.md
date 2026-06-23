# Agentopia 深度分析 — 基础设施层

---

## 一、`src/config.py` — 配置系统

**文件位置**：`E:\Agentopia\src\config.py`（82 行）

**核心作用**：集中化的配置加载与访问

### 关键代码

```python
_CONFIG: Dict[str, Any] | None = None    # 全局单例配置
_SENSITIVE_KEYS = {"api_key", ...}        # 敏感键值列表

def load_config(config_path) -> Dict      # 应用启动时调用一次
def get_config() -> Dict                  # 全局访问点（惰性加载兜底）
def get_world_config() -> Dict            # 快速获取 world 子配置
def _redact_secrets(obj) -> Any           # 递归脱敏，用于安全打印
```

### 设计亮点

1. **单例模式**：全局 `_CONFIG` 变量确保配置只加载一次
2. **安全打印**：`_redact_secrets` 递归遍历配置对象，将敏感字段替换为 `***REDACTED***`
3. **惰性兜底**：`get_config()` 如果发现 `_CONFIG is None`，自动从默认路径加载 `config.json`
4. **无外部依赖**：仅使用标准库 `json` 和 `pathlib`

---

## 二、`src/utils.py` — 工具函数库

**文件位置**：`E:\Agentopia\src\utils.py`（1820 行，全项目最大文件）

**核心作用**：LLM 多后端调用、缓存系统、日志系统、字符串处理

### 2.1 LLM 调用引擎 (`generate_with_fc`)

**这是全系统最关键的函数**，支持四种后端：

| 后端类型 | 识别方式 | 调用方式 |
|---------|---------|---------|
| OpenAI 兼容 (vLLM) | 有 `url` 字段 | `chat.completions.create()` |
| Anthropic Claude | 模型名以 `claude` 开头 | `client.messages.create()` |
| Google Gemini | 模型名以 `gemini` 开头 | `client.models.generate_content()` |
| 封闭源模型 | 在 `_CLOSED_SOURCE_PROVIDERS` 中 | 分派到专用函数 |

**关键特性**：

1. **自动重试机制**：最多 5 次（`_MAX_GENERATION=5`），瞬态错误指数退避（max 5min/attempt, 1h 总上限）
2. **Fallback 切换**：主模型失败后自动切换到 `fallback_model`
3. **工具调用 (Function Calling)**：支持 OpenAI 格式的 tool_calls
4. **推理内容处理**：支持 `<think>` 标签提取与规范化
5. **思维模型 (Thinking)**：通过 `chat_template_kwargs` 启用 vLLM reasoning 模型
6. **自动 token 预算调整**：检测 `max_tokens too large` 错误，自动计算可用的输出 token 数

**代码骨架**：

```python
@cached
def generate_with_fc(model, messages, functions, ...) -> List[Dict]:
    # 1. Qwen 适配：确保有 user 消息
    # 2. 判断后端类型并分派
    # 3. 异常处理 + 重试逻辑
    # 4. 结果规范化（strip、think 标签处理）
    # 5. 重复生成检测（对 role model 截断检测）
```

### 2.2 三层缓存系统

**设计思想**：LLM 调用是模拟中最昂贵的操作，缓存复用可减少 80%+ 的 API 调用

**结构**：

```
┌─────────────────┐
│  Worker Delta   │  ← 线程本地，最新写入
├─────────────────┤
│ Main Thread Δ   │  ← 主线程的增量
├─────────────────┤
│  Shared Cache   │  ← 从磁盘加载，只读
└─────────────────┘
```

- **线程安全**：`threading.local()` 实现 TLS，`_delta_registry` 全局注册
- **确定性哈希**：`_canonical_key()` 对 messages 规范化（去除 ID、标准化空白），确保语义等价请求命中相同缓存
- **即时落盘**：`_FLUSH_EVERY_N = 1`，每次 miss 都写入，防止崩溃丢失
- **分片隔离**：每个 worker 线程使用独立 shard 文件避免竞争

### 2.3 日志系统

**多级日志架构**：

```python
# 1. 普通日志（按模块）
logs/{run_id}/world.log           # 世界引擎
logs/{run_id}/agent_{name}.log    # 每个智能体
logs/{run_id}/error.log           # 错误日志

# 2. 缓存日志
logs/world_{worldname}_{runid}.log

# 3. 验证日志（特征开发用）
logs/verify/{run_id}/
├── solo_activity.log
├── joint_activity.log
├── economy.log
├── reward.log
├── public_activity.log
├── ...
└── generations/
    ├── solo_activity.jsonl
    ├── solo_activity.md
    └── ...
```

- **`setup_logger()`**：标准日志初始化，支持文件 + 控制台
- **`get_verify_logger()`**：特征验证日志，按 feature 分文件
- **`save_feature_generation()`**：保存完整 LLM 请求/响应到 JSONL + 可读 MD
- **`set_log_run_id()`**：动态切换日志目录（支持从 checkpoint 恢复）

### 2.4 数据封装工具

```python
clip_str(s, max_len=500)           # 字符串截断，末尾加省略计数
clip_function_context(messages)     # 压缩 tool response 内容
num_tokens_from_string(text)        # token 估算（tiktoken，离线回退 4 字符/token）
extract_json(text)                  # 从 LLM 文本中提取 JSON
add_speaker_and_turn(content, speaker, turn)  # 添加发言格式头
remove_inner_thoughts(dialogue)     # 移除 [...] 格式的内心独白
parse_discard_list(response, ...)   # 解析丢物列表
```
