from __future__ import annotations
from mcp.server.fastmcp import FastMCP
import re


def register(mcp: FastMCP) -> None:
    @mcp.tool()
    def rain_task_route(task: str, context: str = "") -> dict:
        """Analyze a task and recommend which team agents to assign and which workflow to use.
        
        Use this BEFORE dispatching engineers to determine the right team composition.

        Args:
            task: Task description (e.g. "Fix the 404 error on root URL")
            context: Optional context - affected files, error messages, etc.
        """
        task_lower = task.lower()

        # ── Workflow routing ──
        # Small: single page, tool script, <= 10 source files
        small_keywords = [
            "小游戏", "游戏", "脚本", "工具", "单页面", "single page",
            "修复", "fix", "bug", "修改", "改一下", "清理", "clean",
            "重命名", "rename", "加个按钮", "改个颜色"
        ]
        is_small = any(kw in task_lower for kw in small_keywords)

        # Bug fix: explicit bug report
        bug_keywords = ["bug", "报错", "错误", "崩溃", "crash", "失败", "不工作", "没反应", "404", "500"]
        is_bug = any(kw in task_lower for kw in bug_keywords)

        # Large: multi-page, microservices, needs architecture
        large_keywords = [
            "架构", "重构", "多模块", "微服务", "数据库", "新功能",
            "设计", "管线", "pipeline", "agent", "mcp", "持久化"
        ]
        is_large = any(kw in task_lower for kw in large_keywords)

        # Analysis only
        analysis_keywords = ["分析", "评审", "review", "调研", "research", "研究", "文档", "doc"]
        is_analysis = any(kw in task_lower for kw in analysis_keywords) and not is_large

        # ── File impact estimation ──
        file_count = 0
        if context:
            file_count = len(re.findall(r"server/[\w/]+\.py|static/[\w/]+\.js", context))
        elif "server" in task_lower or "后端" in task_lower:
            if is_large:
                file_count = 10
            elif is_bug:
                file_count = 3
            else:
                file_count = 5
        elif "static" in task_lower or "前端" in task_lower or "js" in task_lower or "html" in task_lower:
            file_count = 3

        # ── Agent selection ──
        agents = []
        
        # Always need engineer for implementation
        if not is_analysis:
            agents.append("engineer")
        
        # PM for new features, research, large projects
        if is_large or "产品" in task_lower or "prd" in task_lower or "需求" in task_lower:
            agents.append("pm")
        
        # Architect for architecture changes, large projects, new systems
        if is_large or "架构" in task_lower or "设计" in task_lower or "结构" in task_lower:
            agents.append("architect")
        
        # QA for everything that has code changes
        if not is_analysis and agents:
            agents.append("qa")

        # ── Determine workflow type ──
        if is_analysis and not is_large:
            workflow = "partial"  # Just analysis/review
        elif is_small and file_count <= 10 and not is_large:
            workflow = "fast"  # Skip PM + Architect
        elif is_bug and not is_large:
            workflow = "bugfix"  # Engineer + QA only
        else:
            workflow = "sop"  # Full PM → Architect → Engineer → QA

        # ── Recommended skills ──
        skills = []
        if "server" in task_lower or "后端" in task_lower or "python" in task_lower:
            skills.append("rain-web-backend")
        if "前端" in task_lower or "js" in task_lower or "html" in task_lower or "css" in task_lower:
            skills.append("rain-web-frontend")
        if "websocket" in task_lower or "ws" in task_lower:
            skills.append("rain-web-websocket")
        if "session" in task_lower or "会话" in task_lower:
            skills.append("rain-web-session")
        if "pipeline" in task_lower or "管线" in task_lower or "agent" in task_lower:
            skills.append("rain-web-pipeline")
        if "canon" in task_lower or "角色" in task_lower or "character" in task_lower:
            skills.append("rain-web-canon")
        if "审查" in task_lower or "review" in task_lower or "规范" in task_lower:
            skills.append("rain-web-code-review")
        if not skills:
            skills.append("rain-web-backend")  # default

        # ── File targeting ──
        targets = []
        if "game_session" in task_lower:
            targets.append("server/app/game_session.py")
        elif "world_state" in task_lower:
            targets.append("server/app/world_state.py")
        elif "main" in task_lower or "api" in task_lower or "路由" in task_lower:
            targets.append("server/main.py")
        elif "websocket" in task_lower:
            targets.append("server/network/websocket_manager.py")
        elif "canon" in task_lower:
            targets.append("server/data/canon_manager.py")
        elif "pipeline" in task_lower or "manana" in task_lower:
            targets.append("server/manana/pipeline.py")
        elif "前端" in task_lower or "js" in task_lower:
            targets.append("static/js/app.js")
        elif "config" in task_lower or "配置" in task_lower:
            targets.append("config.yaml")

        return {
            "task": task,
            "context": context,
            "recommendation": {
                "workflow": workflow,
                "agents": agents,
                "skills": skills,
                "file_count_estimate": file_count,
                "target_files": targets,
            },
            "workflow_desc": {
                "fast": "Engineer + QA only (skip PM/Architect)",
                "bugfix": "Engineer locates + fixes, QA verifies",
                "sop": "Full: PM → Architect → Engineer → QA",
                "partial": "Analysis/review only (no code changes)",
            }.get(workflow, ""),
            "agent_desc": {
                "pm": "许清楚 — Product design, PRD, market research",
                "architect": "高见远 — System design, task decomposition",
                "engineer": "寇豆码 — Code implementation",
                "qa": "严过关 — Testing and verification",
            },
            "next_step": f"TeamCreate('software-{_slugify(task)}') → Agent(spawn {', '.join(agents)})",
        }


def _slugify(text: str) -> str:
    """Convert task text to a short team name."""
    # Take first 20 chars, replace non-alphanumeric with hyphens
    slug = re.sub(r"[^a-zA-Z0-9\u4e00-\u9fff]", "-", text)[:20]
    return slug.strip("-").lower() or "task"
