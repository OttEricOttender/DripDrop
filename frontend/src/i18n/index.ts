import { createContext, useContext } from 'react'
import et from './et'
import en from './en'

export type Lang = 'et' | 'en'

const translations: Record<Lang, Record<string, string>> = { et, en }

export interface I18nContextValue {
  lang: Lang
  setLang: (l: Lang) => void
  t: (key: string) => string
}

export const LanguageContext = createContext<I18nContextValue>({
  lang: 'et',
  setLang: () => {},
  t: (k: string) => k,
})

export function useT(): I18nContextValue {
  return useContext(LanguageContext)
}

export function makeT(lang: Lang): (key: string) => string {
  return (key: string) => translations[lang][key] ?? translations['et'][key] ?? key
}
