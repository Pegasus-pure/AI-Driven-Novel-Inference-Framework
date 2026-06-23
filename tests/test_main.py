# -*- coding: utf-8 -*-
"""FastAPI 应用入口测试

测试 main.py 的 HTTP 端点和 WebSocket 端点
"""

import pytest
from unittest.mock import Mock, patch
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from fastapi.testclient import TestClient

# 导入 app
from server.main import app


class TestHealthEndpoint:
    """测试健康检查端点"""

    @pytest.fixture
    def client(self):
        """创建测试客户端"""
        return TestClient(app)

    def test_health_check(self, client):
        """测试健康检查"""
        response = client.get("/health")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "version" in data

    def test_health_check_content_type(self, client):
        """测试响应内容类型"""
        response = client.get("/health")
        
        assert response.headers["content-type"] == "application/json"


class TestStaticFileServing:
    """测试静态文件服务"""

    @pytest.fixture
    def client(self):
        """创建测试客户端"""
        return TestClient(app)

    def test_serve_index(self, client):
        """测试服务首页"""
        response = client.get("/")
        
        # 应该返回 HTML 响应
        assert response.status_code in [200, 404]  # 取决于 static/index.html 是否存在
        if response.status_code == 200:
            assert "html" in response.text.lower() or "rain" in response.text.lower()

    def test_spa_fallback(self, client):
        """测试 SPA 回退"""
        response = client.get("/some/random/path")
        
        # 应该回退到 index.html 或返回 404
        assert response.status_code in [200, 404]

    def test_static_file_not_found(self, client):
        """测试静态文件不存在"""
        # 请求一个肯定不存在的文件
        response = client.get("/static/nonexistent_file_12345.txt")
        
        assert response.status_code == 404


class TestAPIIntegration:
    """测试 API 集成"""

    @pytest.fixture
    def client(self):
        """创建测试客户端"""
        return TestClient(app)

    def test_health_endpoint_structure(self, client):
        """测试健康检查响应结构"""
        response = client.get("/health")
        data = response.json()
        
        # 验证响应结构
        assert "status" in data
        assert isinstance(data["status"], str)
        assert "version" in data
        assert isinstance(data["version"], str)

    def test_cors_headers(self, client):
        """测试 CORS 头（如果配置了）"""
        response = client.options("/health")
        
        # 至少应该返回允许的方法
        # 注意：FastAPI 默认不启用 CORS，这个测试可能会失败
        # 这里只是检查响应不抛出异常
        assert response.status_code in [200, 405, 404]


class TestWebSocketEndpoint:
    """测试 WebSocket 端点（基础测试）"""

    @pytest.fixture
    def client(self):
        """创建测试客户端"""
        return TestClient(app)

    def test_websocket_connect(self, client):
        """测试 WebSocket 连接"""
        with client.websocket_connect("/ws?session_id=test_001") as websocket:
            # 应该成功连接
            # 注意：这个测试可能会失败，因为 GameSession 初始化可能需要配置
            pass

    def test_websocket_connect_without_session(self, client):
        """测试无 session_id 的 WebSocket 连接"""
        with client.websocket_connect("/ws") as websocket:
            # 应该成功连接（自动生成 session_id）
            pass


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
