# -*- coding: utf-8 -*-
"""Provider 测试 - LLM提供商（使用Mock）"""

import pytest
from unittest.mock import Mock, AsyncMock, patch
import sys
import os
from typing import Any, Optional

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from server.manana.providers import (
    BaseProvider,
    OllamaProvider,
    OpenAIProvider,
    DeepSeekProvider,
    ProviderFactory,
    _parse_openai_response,
)


class TestParseOpenAIResponse:
    """测试OpenAI响应解析（纯函数）"""

    def test_parse_valid_response(self):
        """测试解析有效的OpenAI响应"""
        body_text = '''{
            "choices": [
                {
                    "message": {
                        "content": "Hello, world!",
                        "role": "assistant"
                    }
                }
            ],
            "usage": {
                "total_tokens": 100
            }
        }'''
        
        result = _parse_openai_response(body_text)
        
        assert result["ok"] is True
        assert result["content"] == "Hello, world!"
        assert result["tokens"] == 100

    def test_parse_response_no_choices(self):
        """测试解析无choices的响应"""
        body_text = '{"id": "test"}'
        
        result = _parse_openai_response(body_text)
        
        assert result["ok"] is False
        assert "No choices" in result["error"]

    def test_parse_response_with_error(self):
        """测试解析含错误的响应"""
        body_text = '{"error": {"message": "Invalid API key"}}'
        
        result = _parse_openai_response(body_text)
        
        assert result["ok"] is False
        assert "Invalid API key" in result["error"]

    def test_parse_response_invalid_json(self):
        """测试解析无效的JSON"""
        body_text = "{invalid json}"
        
        result = _parse_openai_response(body_text)
        
        assert result["ok"] is False
        assert "JSON parse error" in result["error"]


class TestOllamaProvider:
    """测试Ollama提供商"""

    def test_get_provider_name(self):
        """测试获取提供商名称"""
        provider = OllamaProvider()
        assert provider.get_provider_name() == "ollama"

    def test_configure(self):
        """测试配置"""
        provider = OllamaProvider()
        provider.configure({
            "model": "qwen3:latest",
            "endpoint": "http://localhost:11434/api/chat"
        })
        
        assert provider.get_model_name() == "qwen3:latest"
        assert provider._config["endpoint"] == "http://localhost:11434/api/chat"

    def test_build_request_body(self):
        """测试构建请求体"""
        provider = OllamaProvider()
        provider.configure({"model": "test_model"})
        
        body = provider._build_request_body(
            system_prompt="You are a helper",
            user_message="Hello",
            options={"temperature": 0.7, "max_tokens": 1024}
        )
        
        assert body["model"] == "test_model"
        assert len(body["messages"]) == 2
        assert body["messages"][0]["role"] == "system"
        assert body["messages"][1]["role"] == "user"
        assert body["temperature"] == 0.7
        assert body["max_tokens"] == 1024
        assert body["think"] is False  # Ollama特定字段

    def test_parse_response_valid(self):
        """测试解析有效的Ollama响应"""
        provider = OllamaProvider()
        
        body_text = '''{
            "model": "qwen3",
            "message": {
                "role": "assistant",
                "content": "Hello from Ollama!"
            },
            "eval_count": 50
        }'''
        
        result = provider._parse_response(body_text)
        
        assert result["ok"] is True
        assert result["content"] == "Hello from Ollama!"
        assert result["tokens"] == 50

    def test_parse_response_error(self):
        """测试解析含错误的Ollama响应"""
        provider = OllamaProvider()
        
        body_text = '{"error": "model not found"}'
        
        result = provider._parse_response(body_text)
        
        assert result["ok"] is False
        assert "model not found" in result["error"]

    @pytest.mark.asyncio
    async def test_chat_mock(self):
        """测试chat方法（Mock HTTP请求）"""
        provider = OllamaProvider()
        provider.configure({"endpoint": "http://localhost:11434/api/chat"})
        
        # Mock _do_request方法
        with patch.object(provider, '_do_request', new_callable=AsyncMock) as mock_request:
            mock_request.return_value = {
                "ok": True,
                "content": "Mocked response",
                "raw": "{}",
                "tokens": 10
            }
            
            result = await provider.chat(
                system_prompt="Test",
                user_message="Hello"
            )
            
            assert result["ok"] is True
            assert result["content"] == "Mocked response"


class TestOpenAIProvider:
    """测试OpenAI提供商"""

    def test_get_provider_name(self):
        """测试获取提供商名称"""
        provider = OpenAIProvider()
        assert provider.get_provider_name() == "openai"

    def test_configure_default_endpoint(self):
        """测试默认endpoint"""
        provider = OpenAIProvider()
        provider.configure({})
        
        assert "openai.com" in provider._config["endpoint"]

    def test_parse_response(self):
        """测试解析OpenAI响应"""
        provider = OpenAIProvider()
        
        body_text = '''{
            "choices": [{"message": {"content": "Hello from OpenAI!"}}],
            "usage": {"total_tokens": 200}
        }'''
        
        result = provider._parse_response(body_text)
        
        assert result["ok"] is True
        assert result["content"] == "Hello from OpenAI!"
        assert result["tokens"] == 200


class TestDeepSeekProvider:
    """测试DeepSeek提供商"""

    def test_get_provider_name(self):
        """测试获取提供商名称"""
        provider = DeepSeekProvider()
        assert provider.get_provider_name() == "deepseek"

    def test_configure_default_endpoint(self):
        """测试默认endpoint"""
        provider = DeepSeekProvider()
        provider.configure({})
        
        assert "deepseek.com" in provider._config["endpoint"]


class TestProviderFactory:
    """测试Provider工厂"""

    def test_create_ollama(self):
        """测试创建Ollama provider"""
        config = {
            "type": "ollama",
            "model": "qwen3:latest",
            "endpoint": "http://localhost:11434/api/chat"
        }
        
        provider = ProviderFactory.create("ollama", config)
        
        assert provider is not None
        assert provider.get_provider_name() == "ollama"
        assert provider.get_model_name() == "qwen3:latest"

    def test_create_openai(self):
        """测试创建OpenAI provider"""
        config = {
            "type": "openai",
            "model": "gpt-4",
            "api_key": "test_key"
        }
        
        provider = ProviderFactory.create("openai", config)
        
        assert provider is not None
        assert provider.get_provider_name() == "openai"

    def test_create_deepseek(self):
        """测试创建DeepSeek provider"""
        config = {
            "type": "deepseek",
            "model": "deepseek-chat",
            "api_key": "test_key"
        }
        
        provider = ProviderFactory.create("deepseek", config)
        
        assert provider is not None
        assert provider.get_provider_name() == "deepseek"

    def test_create_unknown_type(self):
        """测试创建未知类型的provider"""
        config = {"type": "unknown"}
        
        provider = ProviderFactory.create("unknown", config)
        
        # 应该返回None或抛出异常
        assert provider is None


class TestBaseProviderUtils:
    """测试BaseProvider工具方法"""

    def test_normalize_options(self):
        """测试标准化选项"""
        provider = OllamaProvider()
        provider.configure({"model": "test", "temperature": 0.5})
        
        options = provider._normalize_options({"max_tokens": 2048})
        
        assert options["model"] == "test"
        assert options["temperature"] == 0.5
        assert options["max_tokens"] == 2048

    def test_build_headers_no_api_key(self):
        """测试构建无API key的请求头"""
        provider = OllamaProvider()
        
        headers = provider._build_headers()
        
        assert "Authorization" not in headers
        assert headers["Content-Type"] == "application/json"

    def test_build_headers_with_api_key(self):
        """测试构建有API key的请求头"""
        provider = OpenAIProvider()
        provider.configure({"api_key": "test_key_123"})
        
        headers = provider._build_headers()
        
        assert headers["Authorization"] == "Bearer test_key_123"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
