"""
工具函数模块
"""
from telethon.tl.types import Message
from telethon.tl import types


def get_media_description(message: Message) -> str:
    """
    获取媒体消息的描述

    参数:
        message: Telegram 消息对象

    返回:
        媒体描述字符串
    """
    if not message.media:
        return ""

    media = message.media

    if isinstance(media, types.MessageMediaPhoto):
        return "[图片]"
    elif isinstance(media, types.MessageMediaDocument):
        # 检查文档类型
        if message.gif:
            return "[GIF]"
        elif message.video:
            return "[视频]"
        elif message.audio:
            return "[音频]"
        elif message.voice:
            return "[语音]"
        elif message.sticker:
            return "[贴纸]"
        elif message.video_note:
            return "[视频消息]"
        else:
            return "[文件]"
    elif isinstance(media, types.MessageMediaContact):
        return "[联系人]"
    elif isinstance(media, types.MessageMediaPoll):
        return "[投票]"
    elif isinstance(media, (types.MessageMediaGeo, types.MessageMediaGeoLive)):
        return "[位置]"
    elif isinstance(media, types.MessageMediaDice):
        return "[表情]"
    else:
        return "[媒体]"
