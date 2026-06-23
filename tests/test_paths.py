# -*- coding: utf-8 -*-
"""paths.py 单元测试

测试覆盖:
1. 路径常量定义
2. 辅助函数（get_novel_path, get_save_path, get_static_path）
3. 跨平台兼容性（pathlib.Path）
"""
import pytest
from pathlib import Path
from server.config.paths import (
    NOVEL_DIR, SAVES_DIR, STATIC_DIR, DOCS_DIR,
    CONFIG_PATH, CONFIG_BACKUP_PATH,
    get_novel_path, get_save_path, get_static_path,
)


class TestPathsConstants:
    """测试路径常量"""
    
    def test_novel_dir(self):
        """测试 NOVEL_DIR 常量"""
        assert isinstance(NOVEL_DIR, Path)
        assert NOVEL_DIR.name == "novel"
    
    def test_saves_dir(self):
        """测试 SAVES_DIR 常量"""
        assert isinstance(SAVES_DIR, Path)
        assert SAVES_DIR.name == "saves"
    
    def test_static_dir(self):
        """测试 STATIC_DIR 常量"""
        assert isinstance(STATIC_DIR, Path)
        assert STATIC_DIR.name == "static"
    
    def test_docs_dir(self):
        """测试 DOCS_DIR 常量"""
        assert isinstance(DOCS_DIR, Path)
        assert DOCS_DIR.name == "docs"
    
    def test_config_path(self):
        """测试 CONFIG_PATH 常量"""
        assert isinstance(CONFIG_PATH, Path)
        assert CONFIG_PATH.name == "config.yaml"
    
    def test_config_backup_path(self):
        """测试 CONFIG_BACKUP_PATH 常量"""
        assert isinstance(CONFIG_BACKUP_PATH, Path)
        assert CONFIG_BACKUP_PATH.name == "config.yaml.bak"


class TestPathsHelperFunctions:
    """测试辅助函数"""
    
    def test_get_novel_path_no_subpath(self):
        """测试 get_novel_path 无子路径"""
        result = get_novel_path()
        assert result == NOVEL_DIR
    
    def test_get_novel_path_with_subpath(self):
        """测试 get_novel_path 有子路径"""
        result = get_novel_path("test.json")
        assert result == NOVEL_DIR / "test.json"
    
    def test_get_save_path_no_subpath(self):
        """测试 get_save_path 无子路径"""
        result = get_save_path()
        assert result == SAVES_DIR
    
    def test_get_save_path_with_subpath(self):
        """测试 get_save_path 有子路径"""
        result = get_save_path("slot_0.json")
        assert result == SAVES_DIR / "slot_0.json"
    
    def test_get_static_path_no_subpath(self):
        """测试 get_static_path 无子路径"""
        result = get_static_path()
        assert result == STATIC_DIR
    
    def test_get_static_path_with_subpath(self):
        """测试 get_static_path 有子路径"""
        result = get_static_path("index.html")
        assert result == STATIC_DIR / "index.html"


class TestPathsCrossPlatform:
    """测试跨平台兼容性"""
    
    def test_path_is_absolute(self):
        """测试路径是绝对路径"""
        assert NOVEL_DIR.is_absolute()
        assert SAVES_DIR.is_absolute()
        assert STATIC_DIR.is_absolute()
    
    def test_path_uses_pathlib(self):
        """测试路径使用 pathlib.Path"""
        assert isinstance(NOVEL_DIR, Path)
        assert isinstance(CONFIG_PATH, Path)


class TestPathsIntegration:
    """测试路径集成"""
    
    def test_project_root_inference(self):
        """测试项目根目录推断"""
        from server.config.paths import _PROJECT_ROOT
        
        # 验证 _PROJECT_ROOT 是有效的目录
        assert isinstance(_PROJECT_ROOT, Path)
        assert _PROJECT_ROOT.name == "Rain-web" or _PROJECT_ROOT.name == ""
    
    def test_all_paths_under_project_root(self):
        """测试所有路径都在项目根目录下"""
        from server.config.paths import _PROJECT_ROOT
        
        # 验证关键路径都在项目根目录下
        assert NOVEL_DIR.is_relative_to(_PROJECT_ROOT)
        assert SAVES_DIR.is_relative_to(_PROJECT_ROOT)
        assert STATIC_DIR.is_relative_to(_PROJECT_ROOT)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
