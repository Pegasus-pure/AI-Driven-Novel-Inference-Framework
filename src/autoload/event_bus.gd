extends Node

## 全局信号总线
## autoload 之间只用 signal 通信，不直接调方法

# 游戏流程
signal game_started()
signal game_paused()
signal game_resumed()
signal game_saved(file_path: String)
signal game_loaded(file_path: String)

# 叙事引擎
signal narrative_ready(text: String)
signal narrative_requested(player_action: String)
signal narrative_error(error: String)

# 世界状态变化
signal world_time_changed(new_time: String)
signal location_changed(from: String, to: String)
signal character_state_changed(char_id: String)
signal thread_updated(thread_id: String)

# 玩家
signal player_action_submitted(action: String)
signal player_info_updated()

# LLM
signal llm_call_started()
signal llm_call_finished(success: bool)
signal llm_stream_token(token: String)

# MaNA Pipeline — 多 Agent 叙事管线信号
signal beat_started(beat_id: String)
signal beat_completed(beat_id: String, result: Dictionary)
signal agent_error(agent_name: String, error: String)
signal pipeline_degraded(from_tier: String, to_tier: String)

# MaNA Pipeline — Provider 热重连信号
signal provider_reconnected()

# MaNA Pipeline — 配置迁移信号
signal config_migrated(from_version: int, to_version: int)
