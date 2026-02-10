"""
Utility functions module
"""
from telethon.tl.types import Message
from telethon.tl import types
from src.i18n import t


def get_media_description(message: Message) -> str:
    """
    Get media message description

    Args:
        message: Telegram message object

    Returns:
        Media description string
    """
    if not message.media:
        return ""

    media = message.media

    if isinstance(media, types.MessageMediaPhoto):
        return t("misc.media.photo")
    elif isinstance(media, types.MessageMediaDocument):
        # Check document type
        if message.gif:
            return t("misc.media.gif")
        elif message.video:
            return t("misc.media.video")
        elif message.audio:
            return t("misc.media.audio")
        elif message.voice:
            return t("misc.media.voice")
        elif message.sticker:
            return t("misc.media.sticker")
        elif message.video_note:
            return t("misc.media.video_note")
        else:
            return t("misc.media.file")
    elif isinstance(media, types.MessageMediaContact):
        return t("misc.media.contact")
    elif isinstance(media, types.MessageMediaPoll):
        return t("misc.media.poll")
    elif isinstance(media, (types.MessageMediaGeo, types.MessageMediaGeoLive)):
        return t("misc.media.location")
    elif isinstance(media, types.MessageMediaDice):
        return t("misc.media.dice")
    else:
        return t("misc.media.media")
