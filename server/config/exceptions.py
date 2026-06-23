"""Rain Web 自定义异常类体系。

所有项目内部异常继承自 RainWebError，支持按类型区分捕获。
逐步替代现有的 dict {"success": False, "message": ...} 字符串级错误传递模式。

用法:
    from server.config.exceptions import (
        PipelineError, DirectorError, ProviderError,
        ConfigError, CanonError, SessionError,
    )

    raise PipelineError("管线执行失败")
    try:
        ...
    except ProviderError as e:
        # 只捕获 Provider 层错误
        ...
    except PipelineError as e:
        # 捕获所有管线错误
        ...
"""


# ═══════════════════════════════════════════════════════════
# 基类
# ═══════════════════════════════════════════════════════════

class RainWebError(Exception):
    """所有 Rain Web 自定义异常的基类。"""


# ═══════════════════════════════════════════════════════════
# 配置
# ═══════════════════════════════════════════════════════════

class ConfigError(RainWebError):
    """配置相关错误 — YAML 加载/解析、热重连等。"""


# ═══════════════════════════════════════════════════════════
# 管线
# ═══════════════════════════════════════════════════════════

class PipelineError(RainWebError):
    """管线执行相关错误的基类。"""


class DirectorError(PipelineError):
    """导演层 Agent 执行错误。"""


class ProviderError(PipelineError):
    """LLM Provider 通信/响应错误。"""


class MemoryError(PipelineError):
    """记忆系统操作错误。"""


# ═══════════════════════════════════════════════════════════
# Canon 数据
# ═══════════════════════════════════════════════════════════

class CanonError(RainWebError):
    """Canon 数据管理错误 — ID 冲突、数据不完整等。"""


# ═══════════════════════════════════════════════════════════
# 游戏会话
# ═══════════════════════════════════════════════════════════

class SessionError(RainWebError):
    """游戏会话相关错误 — 创建/保存/恢复失败等。"""
