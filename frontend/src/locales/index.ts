import { createI18n } from 'vue-i18n'
import ru from './ru.json'

/**
 * Pluralization rule for Russian.
 *
 * Russian has 4 forms: zero | one | few | many.
 * Example for «анализ»: «ни одного анализа» | «1 анализ» |
 *   «2 анализа» (2–4) | «5 анализов» (5–20), и т.д.
 *
 * Index mapping для шаблона `"0 | 1 | few | many"`:
 *   0 → форма «zero»
 *   1 → форма «one»
 *   2 → форма «few»
 *   3 → форма «many»
 */
function russianPluralRule(choice: number, choicesLength: number): number {
  if (choice === 0) return 0
  const teen = choice > 10 && choice < 20
  const endsWithOne = choice % 10 === 1
  const endsWithFew = choice % 10 >= 2 && choice % 10 <= 4
  if (!teen && endsWithOne) return choicesLength < 4 ? 1 : 1
  if (!teen && endsWithFew) return choicesLength < 4 ? 1 : 2
  return choicesLength < 4 ? 2 : 3
}

export const i18n = createI18n({
  legacy: false,
  locale: 'ru',
  fallbackLocale: 'ru',
  messages: { ru },
  pluralRules: {
    ru: russianPluralRule,
  },
})
