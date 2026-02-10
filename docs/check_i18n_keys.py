#!/usr/bin/env python3
"""
检查语言文件中未使用的键
遍历所有的键，并在项目的 Python 文件中搜索是否使用
"""

import os
import re
from pathlib import Path
from typing import Dict, List, Set


def extract_keys(data: Dict, prefix: str = "") -> List[str]:
    """
    递归提取字典中的所有键路径

    Args:
        data: 字典数据
        prefix: 键前缀

    Returns:
        所有键路径的列表
    """
    keys = []

    for key, value in data.items():
        current_key = f"{prefix}.{key}" if prefix else key

        if isinstance(value, dict):
            # 递归处理嵌套字典
            keys.extend(extract_keys(value, current_key))
        else:
            # 叶子节点，添加完整路径
            keys.append(current_key)

    return keys


def search_key_in_files(key: str, search_dir: str) -> List[str]:
    """
    在指定目录的所有 Python 文件中搜索键

    Args:
        key: 要搜索的键
        search_dir: 搜索目录

    Returns:
        包含该键的文件路径列表
    """
    found_files = []

    # 遍历所有 Python 文件
    for py_file in Path(search_dir).rglob("*.py"):
        try:
            with open(py_file, 'r', encoding='utf-8') as f:
                content = f.read()

                # 搜索键（可能以字符串形式出现）
                # 匹配 "key" 或 'key' 或 f"...{key}..." 等形式
                if key in content:
                    found_files.append(str(py_file))
        except Exception as e:
            print(f"读取文件 {py_file} 时出错: {e}")

    return found_files


def main():
    # 获取项目根目录
    project_root = Path(__file__).parent

    # 导入语言文件
    import sys
    sys.path.insert(0, str(project_root / "../src"))

    from i18n.locales import en_US, zh_CN

    print("=" * 80)
    print("检查语言文件中未使用的键")
    print("=" * 80)
    print()

    # 提取所有键
    print("📋 提取所有键...")
    en_keys = extract_keys(en_US.TRANSLATIONS)
    zh_keys = extract_keys(zh_CN.TRANSLATIONS)

    print(f"   英文键数量: {len(en_keys)}")
    print(f"   中文键数量: {len(zh_keys)}")
    print()

    # 检查两个语言文件的键是否一致
    en_set = set(en_keys)
    zh_set = set(zh_keys)

    if en_set != zh_set:
        print("⚠️  警告: 英文和中文的键不一致!")
        print()

        only_en = en_set - zh_set
        if only_en:
            print(f"   仅在英文中存在的键 ({len(only_en)}):")
            for key in sorted(only_en):
                print(f"      - {key}")
            print()

        only_zh = zh_set - en_set
        if only_zh:
            print(f"   仅在中文中存在的键 ({len(only_zh)}):")
            for key in sorted(only_zh):
                print(f"      - {key}")
            print()

    # 使用英文键作为基准
    all_keys = sorted(en_set)

    # 搜索每个键的使用情况
    print("🔍 搜索键的使用情况...")
    print()

    unused_keys = []
    used_keys = []

    for i, key in enumerate(all_keys, 1):
        print(f"   [{i}/{len(all_keys)}] 检查: {key}", end="\r")

        # 在 src 目录中搜索
        found_files = search_key_in_files(key, str(project_root / "../src"))

        # 排除语言文件本身
        found_files = [
            f for f in found_files
            if not f.endswith(("en_US.py", "zh_CN.py"))
        ]

        if found_files:
            used_keys.append((key, found_files))
        else:
            unused_keys.append(key)

    print()
    print()

    # 输出结果
    print("=" * 80)
    print("📊 检查结果")
    print("=" * 80)
    print()

    print(f"✅ 已使用的键: {len(used_keys)}")
    print(f"❌ 未使用的键: {len(unused_keys)}")
    print()

    if unused_keys:
        print("=" * 80)
        print("❌ 未使用的键列表:")
        print("=" * 80)
        for key in unused_keys:
            print(f"   - {key}")
        print()

    # 可选：显示使用情况详情
    show_details = input("是否显示已使用键的详细信息? (y/N): ").strip().lower()
    if show_details == 'y':
        print()
        print("=" * 80)
        print("✅ 已使用键的详细信息:")
        print("=" * 80)
        for key, files in used_keys:
            print(f"\n   {key}")
            for file in files:
                # 显示相对路径
                rel_path = str(Path(file).relative_to(project_root)).replace("../", "")
                print(f"      - {rel_path}")


if __name__ == "__main__":
    main()
