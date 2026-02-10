"""
Internationalization (i18n) module
Provides multi-language support, including translation functions and language switching
"""
from .translator import t, set_language, get_language, get_available_languages

__all__ = ['t', 'set_language', 'get_language', 'get_available_languages']
