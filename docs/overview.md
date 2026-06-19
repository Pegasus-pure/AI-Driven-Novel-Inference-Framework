# Pipeline 初始化失败诊断与修复

## 问题表象

```
ws-client.js:257 [WS] 未处理的错误: PIPELINE_FAILED Pipeline 未初始化
app.js:421 [App] Pipeline 初始化失败: Pipeline 未初始化
```

用户怀疑是 F7 设置导致。

## 根因（2 个并发，均 P0 阻塞）

| # | 根因 | 位置 |
|---|------|------|
| 1 | `pipeline.py` 缺少 `_log = get_logger("MaNA.Pipeline")` — P2-A 拆分时丢失 | `_init_providers()` → NameError |
| 2 | `update_config()` 中 pipeline 为 None 时跳过重连 — F7 保存后不生效 | `game_session.py:1160` |

## 根因 1 修复

**文件**: `server/manana/pipeline.py`

在 imports 后添加:
```python
_log = get_logger("MaNA.Pipeline")
```

验证通过: 三级 Provider (qwen3.5:9b × 3) 正确初始化。

## 根因 2 修复

**文件**: `server/game_session.py`

`update_config()` 中 pipeline 为 None 时，用新配置重新创建 MananaPipeline:
```python
if self.pipeline:
    self.pipeline.reload_config(cfg)
else:
    # 新建 pipeline
    self.pipeline = MananaPipeline(yaml_dict=cfg)
    await asyncio.wait_for(self.pipeline.initialize(), timeout=10.0)
```

## 回答原问题

**F7 设置本身没有问题。** 真正的问题是:
1. P2-A 拆分引入的 `_log` 丢失 bug，导致初始化时崩溃
2. 崩溃后 F7 保存无法救回，因为缺少重连重试逻辑

两个 bug 均已修复，重启服务器即可。
