"""
WebUI工具函数
"""
from typing import List
from src.constants import SUCCESS_PREFIX, ERROR_PREFIX, INFO_PREFIX


def parse_chat_list(text: str) -> List:
    """
    解析聊天列表

    参数:
        text: 多行文本，每行一个聊天 ID 或用户名

    返回:
        解析后的聊天列表（整数或字符串）
    """
    if not text or not text.strip():
        return []

    result = []
    for line in text.strip().split('\n'):
        line = line.strip()
        if not line:
            continue
        # 判断是数字还是用户名
        if line.lstrip('-').isdigit():
            result.append(int(line))
        else:
            result.append(line)
    return result


def format_message(msg: str, msg_type: str) -> str:
    """
    统一的消息格式化

    参数:
        msg: 消息内容
        msg_type: 消息类型 ('success', 'error', 'info')

    返回:
        格式化后的消息
    """
    prefixes = {
        'success': SUCCESS_PREFIX,
        'error': ERROR_PREFIX,
        'info': INFO_PREFIX
    }
    return f"{prefixes[msg_type]} {msg}"
