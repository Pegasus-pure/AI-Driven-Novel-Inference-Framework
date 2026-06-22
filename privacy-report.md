# 隐私安全检查报告

> 扫描日期: 2026-06-22

## 扫描结果

### 🔴 已修复 — 内网 IP 泄露（11 处）
- 将 `192.168.71.11` 全部替换为 `localhost`
- 涉及文件: `config.yaml`, `manana_config.cfg`, `manana_config.gd`, `main.gd`, `ollama_provider.gd`

### 🟡 已处理
- `.gitignore` 新增: `__pycache__/`, `*.pyc`, `server/**/metrics/`, `saves/`, `novel/`
- `reward_log.jsonl` 已移出 staging
- 合并冲突已解决（32 个文件保留）

### ✅ 通过
- `api_key` 字段全部为空（无泄漏风险）
- 用户名 `25824` 未硬编码
- SSH 密钥 / `.env` / 数据库文件 未发现
- 云服务密钥 未发现
