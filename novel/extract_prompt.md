# Canon 抽取提示词模板

> 将本提示词 + 小说全文一起发给 LLM，即可生成 canon.json。
> 建议逐块处理（每 3-5 章一块），最后合并去重。

---

## 角色抽取 (Pass A)

```
你是一个小说分析引擎。请从以下小说文本中提取所有重要角色。

对每个角色输出以下字段（JSON 格式）：

{
  "id": "char_001",
  "name": "角色名",
  "aliases": ["别名1", "别名2"],
  "role": "主角 / 反派 / 配角 / 关键角色",
  "personality": {
	"traits": ["性格特征1", "特征2"],
	"speech_style": "说话风格（一句话描述）",
	"core_motivation": "核心动机",
	"core_fear": "核心恐惧/弱点",
	"moral_alignment": "善良 / 邪恶 / 中立"
  },
  "appearance": "外貌描述",
  "abilities": ["能力1", "能力2"],
  "relationships": [
	{"target": "char_002", "type": "关系类型", "intensity": 0.0~1.0}
  ],
	"starting_location": "loc_001",
	"key_traits": ["关键特质1", "关键特质2"],
	"anti_rules": ["绝对不会发生的事1", "反套路特征2"],
	"status": "alive"

	// 可选扩展字段（用于灵魂附生模式）
	"memory_of_protagonist": {
		"char_001": {
			"impression": "一句话描述 NPC 记忆中主角是什么样的人",
			"key_memories": ["具体场景事件1", "场景2"],
			"expected_behavior": "NPC 预期中主角的行为方式",
			"trust_level": 0.0~1.0
		}
	},
	"npc_relationships": [
		{"target": "char_008", "type": "挚友/青梅竹马", "bond_strength": 0.85}
	]

要求：
- 只输出角色首次出现或最重要出场的信息
- 角色数控制在 5-15 个（核心角色，长篇可适当增加）
- relationships 只列出与故事主线相关的核心关系
- key_traits 提炼角色最与众不同的 1-3 个特质
- anti_rules 列出角色不会做的事或不会踩的雷点
- memory_of_protagonist 和 npc_relationships 为可选字段
- memory_of_protagonist 只对与主角有直接互动的角色生成
- npc_relationships 只列出与故事相关的 NPC 间关系
```

## 世界观抽取 (Pass B)

```
你是一个世界构建分析引擎。请从以下小说文本中提取世界观规则。

{
  "world_rules": {
	"era": "时代背景（如：维多利亚时代伦敦、中世纪奇幻等）",
	"magic_system": {
	  "name": "力量体系名称（无超自然力量则写"现实世界"）",
	  "rules": ["规则1", "规则2"],
	  "limitations": "限制条件"
	},
	"society": {
	  "structure": "社会结构描述",
	  "factions": ["势力/组织1", "势力/组织2"],
	  "technology_level": "科技水平"
	},
	"species": [
	  {"name": "物种", "traits": ["特征"], "population_share": 0.0~1.0}
	]
  }
}
```

## 地点抽取 (Pass C)

```
你是一个地理分析引擎。请从以下小说文本中提取所有重要地点。

[
  {
	"id": "loc_001",
	"name": "地点名",
	"type": "建筑 / 城市 / 自然 / 其他",
	"parent": "上级地点ID（如该地点属于某个城市）",
	"description": "环境描写（2-3句）",
	"atmosphere": "氛围（如：阴森、庄严、热闹）",
	"sub_locations": [
	  {"id": "loc_001a", "name": "子地点名", "type": "建筑"}
	]
  }
]

要求：
- 提取 3-10 个核心地点
- 每个地点的 description 基于原文具体描写
- sub_locations 可选，仅当该地点内部有重要的子区域时添加
```

## 时间线抽取 (Pass D)

```
你是一个叙事分析引擎。请从以下小说文本中提取关键事件时间线。

[
  {
	"id": "event_001",
	"title": "事件标题",
	"description": "事件简述（1-2句）",
	"involved_characters": ["char_001", "char_003"],
	"involved_locations": ["loc_001"],
	"significance": "故事起点 / 揭示主线冲突 / 高潮对决 / 关键转折",
	"conflicts": [
	  {
		"id": "conflict_001",
		"type": "mystery / character_conflict / moral_dilemma / external_threat",
		"description": "冲突描述",
		"involved_characters": ["char_001"],
		"intensity": 0.0~1.0,
		"variants": ["可能的冲突走向1", "走向2"]
	  }
	]
  }
]

要求：
- 提取 3-8 个关键事件
- 事件应覆盖故事的开端→冲突→高潮结构
- conflicts 可选，仅当事件涉及可展开的剧情冲突时添加
```

## 写作风格

```
{
  "writing_style": {
	"tone": "总体基调（如：热血、悬疑、温情、暗黑）",
	"pace": "节奏（快节奏/慢节奏/对话多/描写多）",
	"dialogue_style": "对话风格（如：自然口语、角色辨识度高）"
  }
}
```

---

## 合并校验规则

1. 同一角色在不同块中可能以不同名字/别名出现 → 合并到同一 id
2. 同一地点可能在不同块中有略微不同的描述 → 取最丰富的一条
3. 关系 intensity 取多块平均值
4. 最终 canon.json 结构参考 `novel/canon.json`
