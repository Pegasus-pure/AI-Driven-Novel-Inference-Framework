# Rain 项目编码规范

> 最后更新：2026-06-17 | 版本：v1.0
>
> **用途**：为 AI 协作者提供明确的命名和编码约束，防止随意更改变量名或代码风格。

---

## 一、命名规范（铁律）

### 1.1 变量命名

| 作用域 | 风格 | 示例 |
|--------|------|------|
| 局部变量 | `snake_case` | `var player_name: String` |
| 成员变量 | `snake_case` | `var _provider: BaseLLMProvider` |
| 私有成员 | `_snake_case` | `var _pending_requests: Dictionary` |
| 常量 | `UPPER_CASE` | `const MAX_RETRIES: int = 3` |

### 1.2 函数命名

| 类型 | 风格 | 示例 |
|------|------|------|
| 公共函数 | `snake_case` | `func run_beat(user_input: String) -> void` |
| 私有函数 | `_snake_case` | `func _init_providers() -> void` |
| 信号回调 | `_on_信号名` | `func _on_beat_completed(data: Dictionary) -> void` |

### 1.3 类/类型命名

| 类型 | 风格 | 示例 |
|------|------|------|
| 类名 | `PascalCase` | `class_name MananaPipeline` |
| 脚本名 | `snake_case` | `manana_pipeline.gd` |
| 场景名 | `snake_case` | `settings_panel.tscn` |

### 1.4 信号命名

- `snake_case`，描述事件：`beat_started`、`narrative_ready`
- 使用过去/进行时：`pipeline_degraded`、`connection_tested`

### 1.5 函数参数

- 所有函数参数必须有显式类型标注：
```gdscript
# ✅ 正确
func some_method(name: String, count: int = 0) -> void:
# ❌ 错误
func some_method(name, count=0):
```

---

## 二、类型标注规则

1. **禁止类型推断**：禁止 `var :=` 语法，必须显式标注类型
2. **`.get()` 返回值**：必须加 `as Type` 转换
3. **Array/Dict 下标**：从 Dictionary/Array 取值时需显式转换
4. **函数返回值**：所有函数必须有显式返回类型标注（`-> void` / `-> String` 等）

```gdscript
# ✅ 正确
var name: String = data.get("name", "") as String
var items: Array = data["items"] as Array

# ❌ 错误
var name = data.get("name", "")
var items = data["items"]
```

---

## 三、变量名禁用/保护规则

### 3.1 禁止随意替换已有变量名

**这是最高优先级的规则。** 修 Bug 或加功能时，绝不顺带改已有变量名。
如果确实需要重命名，必须：
1. 告知用户原因和范围
2. 获得确认后方可执行

### 3.2 避免变量遮蔽（SHADOWED_VARIABLE）

不要在嵌套作用域中声明与外部同名的变量：

```gdscript
# ❌ 错误 — 内层 name 遮蔽外层
var name: String = "Alice"
for c: Character in characters:
    var name: String = c.name  # 遮蔽！

# ✅ 正确 — 内层使用不同名称
var name: String = "Alice"
for c: Character in characters:
    var char_name: String = c.name
```

### 3.3 常用变量名约定（已统一）

以下变量名在全项目中含义一致，**禁止用于其他用途**：

| 变量名 | 含义 | 出现位置 |
|--------|------|---------|
| `data` | 解析后的 JSON/响应数据 Dictionary | LLM 响应处理 |
| `result` | 原始 API 响应 Dictionary | Provider/Agent |
| `content` | LLM 返回的文本内容 String | Agent.run() |
| `err` | Error 码 int | 网络/文件操作 |
| `validation` | Schema 校验结果 Dictionary | MananaSchema |
| `config` | 配置 Dictionary | 全局配置读取 |

### 3.4 增量编辑时的变量命名

在已有函数中添加代码时：
- 检查函数顶部已有的变量声明
- 新变量名不与已有变量名冲突
- 如果名称冲突，使用更具体的名称（如 `char_name` 而非 `name`）

---

## 四、Autoload 间通信

- 只能用 `EventBus` 信号通信
- 禁止循环 preload
- 禁止 autoload 间直接调用函数

---

## 五、文件组织

```
src/
  autoload/    — 全局单例（WorldState, EventBus, CanonLoader 等）
  llm/
    manana/    — MaNA 五层叙事管线
    providers/ — LLM Provider 抽象层（Ollama/DeepSeek/OpenAI）
  ui/          — UI 脚本（main.gd）
  narrative/   — 叙事相关（narrative_state.gd）
```

---

## 六、修改代码前的检查清单

- [ ] 只改指定代码，不借机重构
- [ ] 新增变量不与已有变量重名
- [ ] `.get()` 返回值已加 `as Type`
- [ ] 新函数有返回类型标注
- [ ] 未改动旧变量名
