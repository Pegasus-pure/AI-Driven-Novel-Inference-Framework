# Godot MCP Server — 构建完成

## 做了什么

为 Rain 项目构建了完整的 **Godot MCP 应用**，让 AI Agent 可以控制 Godot 4.6.3 引擎。28 个 MCP 工具涵盖项目文件管理、场景编辑、脚本管理、运行时控制和 Rain 专属正典数据管理。

## 核心架构

```
AI Agent ←→ stdio ←→ MCP Server (TS/Node.js) ←→ WebSocket ←→ Godot Editor Plugin
                           │
                           └→ 文件系统直接读写
```

## 新增文件

### Godot Editor Plugin (`addons/godot_mcp/`)
| 文件 | 说明 |
|------|------|
| `plugin.cfg` | 插件元数据配置 |
| `plugin.gd` | EditorPlugin 入口 (28行) |
| `mcp_bridge.gd` | WebSocket 服务器 + JSON-RPC API (460行) |

### TypeScript MCP Server (`mcp-server/`)
| 文件 | 说明 |
|------|------|
| `src/index.ts` | 主入口，28 个工具注册 + stdio transport |
| `src/godot-client.ts` | WebSocket 客户端，超时/重试/fallback |
| `src/tools/project.ts` | 项目文件读写、搜索 (5 工具) |
| `src/tools/scene.ts` | 场景节点 CRUD (7 工具) |
| `src/tools/script.ts` | GDScript 读写验证 (4 工具) |
| `src/tools/runtime.ts` | 运行时控制 + autoload 调用 (6 工具) |
| `src/tools/canon.ts` | Rain canon.json 管理 (10 工具) |
| `mcp-config.json` | MCP client 配置模板 |
| `README.md` | 完整使用文档 |

## 测试结果

- TypeScript 编译: ✅ 成功 (0 errors)
- MCP tools/list: ✅ 28 工具全部注册
- 文件通道: ✅ project_info / project_read_file 正常
- WebSocket 通道: 需 Godot 编辑器启用插件后验证

## 使用方式

1. 在 Godot 编辑器中启用 "Godot MCP Bridge" 插件
2. 将 `mcp-config.json` 配置添加到你的 MCP client
3. AI Agent 即可通过 28 个工具控制 Godot 项目

## 下一步

- 在 Godot 编辑器中实际启用插件并测试 WebSocket 通道
- 测试 `runtime_call_autoload` 在游戏运行时读取 WorldState
- 按需添加更多工具 (如 godot --headless 脚本校验、资源导入等)
