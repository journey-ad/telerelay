import unittest
from types import SimpleNamespace

from telethon.tl.types import (
    Document,
    DocumentAttributeAudio,
    DocumentAttributeSticker,
    DocumentAttributeVideo,
    MessageMediaDocument,
    MessageMediaPhoto,
    MessageMediaWebPage,
    Photo,
    PhotoSize,
    WebPage,
)

from backend.filters import MessageFilter, get_media_type, is_media_message


def photo_message(caption: str = "", size: int = 2048) -> SimpleNamespace:
    photo = Photo(
        id=1,
        access_hash=1,
        file_reference=b"",
        date=None,
        sizes=[PhotoSize(type="x", w=100, h=100, size=size)],
        dc_id=1,
    )
    return SimpleNamespace(media=MessageMediaPhoto(photo=photo), text=caption)


def document_message(attributes, text: str = "", size: int = 4096) -> SimpleNamespace:
    document = Document(
        id=2,
        access_hash=2,
        file_reference=b"",
        date=None,
        mime_type="application/octet-stream",
        size=size,
        dc_id=1,
        attributes=list(attributes),
    )
    return SimpleNamespace(media=MessageMediaDocument(document=document), text=text)


def text_message(text: str = "release notes") -> SimpleNamespace:
    return SimpleNamespace(media=None, text=text)


def link_message(text: str = "see https://example.com") -> SimpleNamespace:
    webpage = WebPage(
        id=3,
        url="https://example.com",
        display_url="example.com",
        hash=0,
    )
    return SimpleNamespace(media=MessageMediaWebPage(webpage=webpage), text=text)


class MediaDetectionTests(unittest.TestCase):
    def test_text_and_link_previews_are_not_media(self):
        self.assertEqual(get_media_type(text_message()), "text")
        self.assertEqual(get_media_type(link_message()), "webpage")
        self.assertFalse(is_media_message(text_message()))
        self.assertFalse(is_media_message(link_message()))
        self.assertFalse(is_media_message(None))

    def test_attachments_are_media(self):
        video = document_message([DocumentAttributeVideo(duration=1, w=1, h=1)])
        voice = document_message([DocumentAttributeAudio(duration=1, voice=True)])
        sticker = document_message([DocumentAttributeSticker(alt="", stickerset=None)])

        for message in (photo_message(), video, voice, sticker):
            with self.subTest(type=get_media_type(message)):
                self.assertTrue(is_media_message(message))


class MediaOnlyModeTests(unittest.TestCase):
    def test_media_mode_forwards_media_and_filters_plain_text(self):
        message_filter = MessageFilter(mode="media-only")

        self.assertTrue(message_filter.should_forward(photo_message("caption")))
        self.assertFalse(message_filter.should_forward(text_message()))
        self.assertFalse(message_filter.should_forward(link_message()))

    def test_media_mode_ignores_keywords_and_regex(self):
        message_filter = MessageFilter(
            mode="media-only",
            keywords=["release"],
            regex_patterns=[r"^urgent"],
        )

        # Matching conditions no longer matter: media decides on its own.
        self.assertTrue(message_filter.should_forward(photo_message("unrelated caption")))
        self.assertFalse(message_filter.should_forward(text_message("release")))

    def test_media_mode_still_honours_ignore_and_size_limits(self):
        message_filter = MessageFilter(
            mode="media-only",
            ignored_user_ids=[42],
            ignored_keywords=["spam"],
            max_file_size=1024,
        )

        self.assertFalse(message_filter.should_forward(photo_message(), sender_id=42))
        self.assertFalse(message_filter.should_forward(photo_message("spam")))
        self.assertFalse(message_filter.should_forward(photo_message(size=4096)))
        self.assertTrue(message_filter.should_forward(photo_message(size=1024)))

    def test_media_mode_still_honours_media_type_allow_list(self):
        message_filter = MessageFilter(mode="media-only", media_types=["video"])

        self.assertFalse(message_filter.should_forward(photo_message()))
        self.assertTrue(
            message_filter.should_forward(
                document_message([DocumentAttributeVideo(duration=1, w=1, h=1)])
            )
        )

    def test_media_mode_rejects_raw_text_input(self):
        self.assertFalse(MessageFilter(mode="media-only").should_forward("release notes"))

    def test_allow_and_block_lists_keep_their_meaning(self):
        message_filter = MessageFilter(mode="whitelist", keywords=["release"])

        self.assertTrue(message_filter.should_forward(photo_message("release")))
        self.assertFalse(message_filter.should_forward(photo_message("other")))

        blocklist = MessageFilter(mode="blacklist", keywords=["release"])
        self.assertFalse(blocklist.should_forward(photo_message("release")))
        self.assertTrue(blocklist.should_forward(photo_message("other")))


if __name__ == "__main__":
    unittest.main()
