import type { LandCoverBreakdown } from '../api/types'
import { useT } from '../i18n'

interface Props {
  lc: LandCoverBreakdown
}

const SEGMENTS: { key: keyof LandCoverBreakdown; color: string }[] = [
  { key: 'B',    color: 'bg-green-600' },
  { key: 'A_ms', color: 'bg-teal-500' },
  { key: 'A_km', color: 'bg-cyan-600' },
  { key: 'A_r',  color: 'bg-blue-400' },
  { key: 'C',    color: 'bg-stone-400' },
]

export default function LandCoverBar({ lc }: Props) {
  const { t } = useT()
  const rows = SEGMENTS.filter(s => lc[s.key] > 0)
  const other = Math.max(0, 100 - rows.reduce((sum, s) => sum + lc[s.key], 0))

  return (
    <div className="space-y-2">
      <div className="flex h-5 rounded overflow-hidden w-full">
        {rows.map(({ key, color }) => (
          <div
            key={key}
            className={`${color} h-full`}
            style={{ width: `${lc[key]}%` }}
            title={`${t(key)}: ${lc[key].toFixed(1)} %`}
          />
        ))}
        {other > 0.5 && (
          <div className="bg-gray-200 h-full flex-1" title={`Muu: ${other.toFixed(1)} %`} />
        )}
      </div>
      <div className="grid grid-cols-2 gap-x-4 gap-y-0.5 text-xs text-gray-700">
        {SEGMENTS.map(({ key, color }) => (
          <div key={key} className="flex items-center gap-1">
            <span className={`inline-block w-2.5 h-2.5 rounded-sm ${color}`} />
            <span>{t(key)}: {lc[key].toFixed(1)} %</span>
          </div>
        ))}
        <div className="flex items-center gap-1">
          <span className="inline-block w-2.5 h-2.5 rounded-sm bg-gray-200" />
          <span>{t('maaparandus')}: {lc.maaparandus.toFixed(1)} %</span>
        </div>
      </div>
    </div>
  )
}
