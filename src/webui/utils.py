"""
WebUI utility functions
"""
from typing import List
from src.constants import SUCCESS_PREFIX, ERROR_PREFIX, INFO_PREFIX


def parse_chat_list(text: str) -> List:
    """
    Parse chat list

    Args:
        text: Multi-line text, one chat ID or username per line

    Returns:
        Parsed chat list (integers or strings)
    """
    if not text or not text.strip():
        return []

    result = []
    for line in text.strip().split('\n'):
        line = line.strip()
        if not line:
            continue
        # Determine if it's a number or username
        if line.lstrip('-').isdigit():
            result.append(int(line))
        else:
            result.append(line)
    return result


def format_message(msg: str, msg_type: str) -> str:
    """
    Unified message formatting

    Args:
        msg: Message content
        msg_type: Message type ('success', 'error', 'info')

    Returns:
        Formatted message
    """
    prefixes = {
        'success': SUCCESS_PREFIX,
        'error': ERROR_PREFIX,
        'info': INFO_PREFIX
    }
    return f"{prefixes[msg_type]} {msg}"
