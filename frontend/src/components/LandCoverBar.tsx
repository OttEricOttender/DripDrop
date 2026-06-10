import type { LandCoverBreakdown } from '../api/types'
import { useT } from '../i18n'

interface Props {
  lc: LandCoverBreakdown
}

const SEGMENTS: { key: keyof LandCoverBreakdown; color: string }[] = [
  { key: 'B',    color: 'bg-green-500' },
  { key: 'A_ms', color: 'bg-teal-500'  },
  { key: 'A_km', color: 'bg-cyan-500'  },
  { key: 'A_r',  color: 'bg-blue-400'  },
  { key: 'C',    color: 'bg-stone-400' },
]

export default function LandCoverBar({ lc }: Props) {
  const { t } = useT()
  const rows = SEGMENTS.filter(s => lc[s.key] > 0)
  const other = Math.max(0, 100 - rows.reduce((sum, s) => sum + lc[s.key], 0))

  return (
    <div className="space-y-3">
      {/* Stacked bar with rounded pill ends */}
      <div className="flex h-5 rounded-full overflow-hidden w-full">
        {rows.map(({ key, color }) => (
          <div
            key={key}
            className={`${color} h-full transition-all`}
            style={{ width: `${lc[key]}%` }}
            title={`${t(key)}: ${lc[key].toFixed(1)} %`}
          />
        ))}
        {other > 0.5 && (
          <div
            className="bg-slate-200 h-full flex-1"
            title={`${t('other')}: ${other.toFixed(1)} %`}
          />
        )}
      </div>

      {/* Legend */}
      <div className="grid grid-cols-2 gap-x-3 gap-y-1 text-xs text-slate-600">
        {SEGMENTS.map(({ key, color }) => (
          <div key={key} className="flex items-center gap-1.5">
            <span className={`inline-block w-2.5 h-2.5 rounded-full ${color} shrink-0`} />
            <span className="truncate">{t(key)}: <span className="font-medium text-slate-800">{lc[key].toFixed(1)} %</span></span>
          </div>
        ))}
        <div className="flex items-center gap-1.5">
          <span className="inline-block w-2.5 h-2.5 rounded-full bg-slate-200 shrink-0" />
          <span className="truncate">{t('maaparandus')}: <span className="font-medium text-slate-800">{lc.maaparandus.toFixed(1)} %</span></span>
        </div>
      </div>
    </div>
  )
}
