import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'
import { enUS } from './locales/en-US'
import { zhCN } from './locales/zh-CN'

export const supportedLocales = ['zh-CN', 'en-US'] as const
export type Locale = (typeof supportedLocales)[number]

const storageKey = 'telerelay.locale'
const savedLocale = window.localStorage.getItem(storageKey)
const initialLocale: Locale = supportedLocales.includes(savedLocale as Locale)
  ? (savedLocale as Locale)
  : 'zh-CN'

void i18n.use(initReactI18next).init({
  resources: {
    'zh-CN': { translation: zhCN },
    'en-US': { translation: enUS },
  },
  lng: initialLocale,
  fallbackLng: 'zh-CN',
  supportedLngs: supportedLocales,
  interpolation: { escapeValue: false },
  returnNull: false,
})

function syncDocumentLanguage(locale: string) {
  const normalized = locale === 'en-US' ? 'en-US' : 'zh-CN'
  window.localStorage.setItem(storageKey, normalized)
  document.documentElement.lang = normalized
}

syncDocumentLanguage(initialLocale)
i18n.on('languageChanged', syncDocumentLanguage)

export default i18n
