# -*- coding: utf-8 -*-
"""AI-Driven-Novel-Inference-Framework — PyInstaller 构建脚本

运行: python build.py

自动执行:
  1. 检查依赖
  2. 清理旧构建
  3. 运行 PyInstaller
  4. 输出到 dist/AINovelFramework.exe
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


_PROJECT_DIR = Path(__file__).resolve().parent


def check_dependencies() -> bool:
    """检查 PyInstaller 是否已安装"""
    try:
        import PyInstaller
        print(f"✓ PyInstaller {PyInstaller.__version__}")
        return True
    except ImportError:
        print("✗ PyInstaller 未安装。运行: pip install pyinstaller>=6.0")
        return False


def clean_build() -> None:
    """清理旧的构建产物"""
    import shutil
    for name in ('build', 'dist', '__pycache__'):
        path = _PROJECT_DIR / name
        if path.exists():
            print(f"  清理: {path}")
            shutil.rmtree(path, ignore_errors=True)

    # 清理 .spec 的临时产物
    for pycache in _PROJECT_DIR.rglob('__pycache__'):
        shutil.rmtree(pycache, ignore_errors=True)

    print("✓ 清理完成")


def run_build() -> None:
    """运行 PyInstaller 构建"""
    import subprocess

    spec_path = _PROJECT_DIR / 'pyinstaller.spec'
    if not spec_path.is_file():
        print("✗ 未找到 pyinstaller.spec")
        sys.exit(1)

    print("═" * 50)
    print("AI-Driven-Novel-Inference-Framework — PyInstaller 构建开始")
    print("═" * 50)

    cmd = [
        sys.executable, '-m', 'PyInstaller',
        str(spec_path),
        '--noconfirm',
        '--clean',
    ]

    print(f"> {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=str(_PROJECT_DIR))

    if result.returncode == 0:
        output = _PROJECT_DIR / 'dist' / 'AINovelFramework.exe'
        if output.exists():
            size_mb = output.stat().st_size / (1024 * 1024)
            print(f"\n✓ 构建成功: {output} ({size_mb:.1f} MB)")
        else:
            print(f"\n⚠ 构建完成但未找到输出文件 (检查 dist/ 目录)")
    else:
        print(f"\n✗ 构建失败 (exit code: {result.returncode})")
        sys.exit(result.returncode)


def main() -> None:
    """主入口"""
    os.chdir(str(_PROJECT_DIR))

    if not check_dependencies():
        sys.exit(1)

    clean_build()
    run_build()


if __name__ == '__main__':
    main()
