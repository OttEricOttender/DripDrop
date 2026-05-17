import { useT } from '../i18n'

interface Props {
  value: number
  onChange: (v: number) => void
}

const OPTIONS = [1, 2, 5, 10, 20]

export default function ProbabilitySelect({ value, onChange }: Props) {
  const { t } = useT()
  return (
    <div className="flex items-center gap-2">
      <label className="text-sm font-medium text-gray-700 whitespace-nowrap">
        {t('probLabel')}
      </label>
      <select
        value={value}
        onChange={e => onChange(Number(e.target.value))}
        className="border border-gray-300 rounded px-2 py-1 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
      >
        {OPTIONS.map(p => (
          <option key={p} value={p}>{p} %</option>
        ))}
      </select>
    </div>
  )
}
