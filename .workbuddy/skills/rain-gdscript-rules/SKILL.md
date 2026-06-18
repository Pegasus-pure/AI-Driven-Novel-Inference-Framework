---
name: rain-gdscript-rules
description: Rain 项目 GDScript 开发铁律。基于 MaNA v3 实战总结的 20+ 错误经验。当在 Rain 项目中新增/修改任何 GDScript 文件时自动触发。涵盖类型安全、Agent 字段对齐、Autoload 规范、Godot 引擎陷阱、LLM Provider 注意事项。
---

# Rain GDScript 开发铁律

本技能基于 MaNA v3 LLM 架构优化项目全程实战积累，记录所有踩过的坑及其规避方案。当在 `E:\Godot-Project\Rain` 项目中编写任何 GDScript 代码时遵守以下规则。

---

## 规则 1: 禁止对 LLM 输出使用 `as` 强转

**问题**: Pipeline 中 Agent 的 `build_user_prompt()` 方法通常将 LLM 输出字段用 `as String` / `as Array` / `as Dictionary` 强转。但 9b 级别小模型 JSON 输出不可靠，字段类型会飘移（String 变 Dictionary、Array 变 String 等）。

**正确做法**:
```gdscript
# 错误 — LLM 输出不可信
var dialogue: Array = co.get("dialogue", []) as Array
var stance: String = co.get("stance_change", "") as String

# 正确 — 类型安全包装
var raw = co.get("dialogue", [])
var dialogue: Array = raw if raw is Array else [raw]
var stance = co.get("stance_change", null)
if stance is Dictionary:
    # use stance.get("new_attitude")
elif stance is String:
    # use stance directly
```

**适用范围**: 所有 Agent 的 `build_user_prompt()` 和 `build_system_prompt()` 中处理 LLM 输出字段的地方。

---

## 规则 2: Agent 输入字段名必须与 build_user_prompt 对齐

**问题**: Pipeline 在 `_build_xxx_input()` 中构建的 input_data 字典的 key，与 Agent 的 `build_user_prompt()` 中 `input_data.get("xxx")` 的 key 不一致。当前没有编译期检查，只能靠运行时 crash 或静默失败发现。

**正确做法**: 新增或修改 Agent 后，必须手动逐条核对 Pipeline ↔ Agent 的 key 映射：

| 调用点 (Pipeline) | 读取点 (Agent) |
|---|---|
| `input_data["character_personas"]` | `input_data.get("character_personas", {})` |
| `input_data["recent_beats_summary"]` | `input_data.get("recent_beats_summary", [])` |

**关键检查项**:
- `_run_oracle()` ↔ `ReflectionOracle.build_user_prompt()` : 5 fields
- `_build_auditor_input()` ↔ `ConsistencyAuditor.build_user_prompt()` : 4 fields
- `_apply_thread_updates()` ↔ `ThreadManager.run()` output fields

---

## 规则 3: Autoload 脚本禁止声明 class_name

**问题**: Godot 中声明为 Autoload 的脚本如果带有 `class_name`，会报 `Class "Xxx" hides an autoload singleton` 并导致脚本无法加载。

**正确做法**:
```gdscript
# 错误
class_name MananaPipeline
extends Node

# 正确
extends Node
## MaNA 编排器 (Autoload 单例)
```

**适用范围**: `ProviderRegistry`, `MananaPipeline` 以及所有将来新增的 Autoload 脚本。

---

## 规则 4: 外部修改代码后必须清除 Godot 缓存

**问题**: 在 Godot 编辑器外部（如通过 AI 工具）修改 `.gd` 文件后，Godot 的 `.uid` 文件和 `.godot/` 缓存可能导致编辑器仍使用旧编译结果。

**正确做法**: 外部修改任何 `.gd` 文件后执行：
```bash
rm -rf "E:/Godot-Project/Rain/.godot/"
```

---

## 规则 5: 移除 Autoload 前必须全项目 grep

**问题**: 从 `project.godot` 移除 Autoload（如 `LLMClient`）后，代码中仍有对该类名的引用导致 Parse Error。

**正确做法**:
```bash
# 移除前
grep -rn "LLMClient" src/ scenes/  # 确认影响范围
# 移除后
grep -rn "LLMClient" src/ scenes/  # 确认归零（注释除外）
```

同样适用于任何类被废弃时的场景。

---

## 规则 6: Coroutine 调用强制加 await

**问题**: GDScript 中所有 coroutine 方法调用必须有 `await`，否则 Parse Error。漏掉 `await` 会导致整个脚本无法加载，且 Godot 直到运行时才报错。

**正确做法**:
```gdscript
# 错误
var result = agent.run(input_data)
var text = agent._call_llm(sys, usr)

# 正确
var result = await agent.run(input_data)
var text = await agent._call_llm(sys, usr)
```

**自动检查清单**: 新增代码后 grep 所有 `_call_llm(` 和 `.run(` 调用，确认前面都有 `await`。

---

## 规则 7: Ollama Provider 配置规范

**问题**: 默认 endpoint 写了外部 IP、`think` 参数用错了位置、端点格式混淆（原生 vs OpenAI 兼容）。

**正确配置**:
```ini
[ollama]
endpoint="http://localhost:11434/api/chat"    # 原生端点（不是 /v1/chat/completions）
```

**请求体**:
```gdscript
var body = {
    "model": "...",
    "messages": [...],
    "stream": false,
    "think": false        # 顶层参数 — 关闭 qwen3 思考模式
}
```

**禁止项**:
- 不使用 `/v1/chat/completions` 作为 Ollama 端点（除非确认支持 OpenAI 兼容模式）
- 不把 `think` 放在 `options` 子对象中
- 不写死外部 IP

---

## 规则 8: MananaConfig 存储路径

**问题**: 配置文件最初放在 `user://`（系统 AppData 目录），脱离项目不可见。

**正确**: `res://manana_config.cfg` — 与项目同目录，版本可控。

**禁止**: 在代码中使用 `user://` 作为配置文件的默认路径。

---

## 规则 9: 新增文本文件格式

**问题**: 创建 `res://prompts/*.md` 文件时未在 `project.godot` 中正确注册导致扫描失败。

**正确做法**: 所有 `res://` 下的 `.md` / `.cfg` / `.tres` 文件创建后，Godot 会在编辑器下次 reload 时自动检测。如果检测失败，手动触发 `Project > Reload Current Project`。

---

## 检查清单 (Checklist)

在 Rain 项目中新增或修改任何代码后，执行以下检查：

- [ ] 所有 LLM 输出字段取值使用了类型安全包装（规则 1）
- [ ] Pipeline ↔ Agent 的 input_data 字段名逐条对齐（规则 2）
- [ ] Autoload 脚本无 `class_name` 声明（规则 3）
- [ ] 外部修改后删除了 `.godot/` 缓存（规则 4）
- [ ] 移除的类名全项目 grep 确认归零（规则 5）
- [ ] 所有 `_call_llm()` / `.run()` 调用前有 `await`（规则 6）
- [ ] Ollama endpoint 使用 `localhost` + `/api/chat`（规则 7）
- [ ] 配置文件路径使用 `res://` 而非 `user://`（规则 8）
