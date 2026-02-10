"""
Internationalization translator core module
Provides thread-safe singleton translator with multi-language switching and parameter interpolation
"""
import os
import threading
from typing import Dict, Any, Optional


class Translator:
    """Thread-safe singleton translator"""

    _instance: Optional['Translator'] = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if not hasattr(self, '_initialized'):
            self._current_language = 'zh_CN'
            self._translations: Dict[str, Dict[str, Any]] = {}
            self._lang_lock = threading.Lock()
            self._load_translations()
            self._initialized = True

    def _load_translations(self):
        """Load all language translation files"""
        try:
            from .locales import zh_CN, en_US
            self._translations = {
                'zh_CN': zh_CN.TRANSLATIONS,
                'en_US': en_US.TRANSLATIONS,
            }
        except ImportError as e:
            print(f"Warning: Failed to load translation files: {e}")
            self._translations = {}

    def _get_nested_value(self, data: Dict[str, Any], key_path: str) -> Optional[str]:
        """
        Get value from nested dictionary

        Args:
            data: Nested dictionary
            key_path: Dot-separated key path, e.g. "ui.button.start"

        Returns:
            Translation text, or None if not found
        """
        keys = key_path.split('.')
        current = data

        for key in keys:
            if isinstance(current, dict) and key in current:
                current = current[key]
            else:
                return None

        return current if isinstance(current, str) else None

    def t(self, key: str, **kwargs) -> str:
        """
        Translation function with parameter interpolation support

        Args:
            key: Translation key, using dot-separated hierarchy, e.g. "ui.button.start"
            **kwargs: Keyword arguments for parameter interpolation

        Returns:
            Translated text, or the key itself if not found

        Examples:
            t("ui.button.start")  # → "▶️ 启动"
            t("log.bot.started", count=5)  # → "✓ Bot 已启动，共 5 个规则"
        """
        with self._lang_lock:
            current_lang = self._current_language

        # Get translation for current language
        lang_data = self._translations.get(current_lang, {})
        translation = self._get_nested_value(lang_data, key)

        # If current language has no translation, fallback to English
        if translation is None and current_lang != 'en_US':
            en_data = self._translations.get('en_US', {})
            translation = self._get_nested_value(en_data, key)

        # If English also not found, fallback to Chinese
        if translation is None and current_lang != 'zh_CN':
            zh_data = self._translations.get('zh_CN', {})
            translation = self._get_nested_value(zh_data, key)

        # If none found, return the key itself (for debugging)
        if translation is None:
            print(f"Warning: Missing translation key: {key}")
            return key

        # Parameter interpolation
        if kwargs:
            try:
                return translation.format(**kwargs)
            except KeyError as e:
                print(f"Warning: Missing parameter in translation: {e}")
                return translation

        return translation

    def set_language(self, lang: str):
        """
        Thread-safe language switching

        Args:
            lang: Language code, e.g. "zh_CN" or "en_US"
        """
        with self._lang_lock:
            if lang in self._translations:
                self._current_language = lang
            else:
                print(f"Warning: Language '{lang}' not supported, keeping current language")

    def get_language(self) -> str:
        """
        Get current language

        Returns:
            Current language code
        """
        with self._lang_lock:
            return self._current_language

    def get_available_languages(self) -> list:
        """
        Get all available languages

        Returns:
            List of language codes
        """
        return list(self._translations.keys())


# Global translator instance
_translator = Translator()


def t(key: str, **kwargs) -> str:
    """
    Global translation function

    Args:
        key: Translation key
        **kwargs: Parameter interpolation

    Returns:
        Translated text
    """
    return _translator.t(key, **kwargs)


def set_language(lang: str):
    """
    Global language switching function

    Args:
        lang: Language code
    """
    _translator.set_language(lang)


def get_language() -> str:
    """
    Get current language

    Returns:
        Current language code
    """
    return _translator.get_language()


def get_available_languages() -> list:
    """
    Get all available languages

    Returns:
        List of language codes
    """
    return _translator.get_available_languages()
