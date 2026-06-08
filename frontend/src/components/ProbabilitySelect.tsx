import { useT } from '../i18n'
import { Card, CardContent } from './ui/card'

interface Props {
  value: number
  onChange: (v: number) => void
}

const OPTIONS = [1, 2, 5, 10, 20]

export default function ProbabilitySelect({ value, onChange }: Props) {
  const { t } = useT()
  return (
    <Card>
      <CardContent className="py-3">
        <div className="flex items-center gap-3">
          <label className="text-sm font-semibold text-slate-700 whitespace-nowrap shrink-0">
            {t('probLabel')}
          </label>
          <select
            value={value}
            onChange={e => onChange(Number(e.target.value))}
            className="flex-1 rounded-md border border-slate-300 bg-white px-3 py-1.5 text-sm text-slate-900
                       focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent
                       transition-shadow cursor-pointer"
          >
            {OPTIONS.map(p => (
              <option key={p} value={p}>{p} %</option>
            ))}
          </select>
        </div>
      </CardContent>
    </Card>
  )
}
