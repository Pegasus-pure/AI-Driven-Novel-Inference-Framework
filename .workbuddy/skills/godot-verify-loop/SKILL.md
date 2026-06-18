# Godot 修改验证闭环

## 触发条件
在 Rain 项目中修改任何 `.gd` / `.tscn` 文件后自动执行。

## 工具依赖
- `godot` MCP — 日志读取、脚本验证、错误搜索
- `desktop-automation` MCP — 截图、热键（F5 触发运行）

## 流程

### Step 0: 预检（Pre-flight）
修改代码后、运行前，先调用 `godot.godot_validate_all` 检查编译问题。
- 有显式 ERROR → 直接修复 → 重新 Step 0
- 仅有 WARNING（如变量重复声明、类型推断提示）→ 可继续 Step 1

### Step 1: 记录修改
列出本次修改的所有文件路径和改动概要。

### Step 2: 触发运行
**首选（自动）**：如果 Godot 编辑器窗口有焦点，直接调用：
```
desktop-automation.hotkey("f5")
```
等待 8 秒让 Godot 编译+启动项目。

**备选（手动）**：Godot 窗口可能未获得焦点时，提示用户：
「请在 Godot 编辑器中按 F5 运行项目，然后告诉我『已运行』」

### Step 3: 日志验证
项目运行后立即调用：
1. `godot.godot_search_log_errors` — 搜索所有 Parse Error / ERROR 行
2. `godot.godot_read_log` (lines=50) — 检查启动日志是否正常

### Step 4: 修复循环
- 日志有 ERROR → 定位文件 + 修复 → 回到 Step 1
- 日志无 ERROR 但输出异常 → 截图辅助分析
- 无报错 → 报告「验证通过 ✅」

## 已知限制
- desktop-automation 截图无法被 AI 直接分析（需用户肉眼确认）
- godot-bridge MCP 需 Godot 编辑器插件启用后才能使用场景构建工具
- Alt+Tab 切换窗口不稳定，建议用户手动将 Godot 置前
