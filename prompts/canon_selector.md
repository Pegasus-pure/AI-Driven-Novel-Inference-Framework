# Canon 选择器

从候选 canon 信息中，选出与当前场景最相关的 Top 5。

## 选择原则
- 优先选择与出场角色直接相关的 canon
- 优先选择与活跃线索相关的世界规则
- 同一角色的多条 canon 取最核心的 1-2 条
- 无关的信息一律排除

只输出以下 JSON：
```json
{"prioritized_ids": ["id1", "id2", ...], "excluded_reason": "一句话说明为什么排除了低优先级项"}
```
