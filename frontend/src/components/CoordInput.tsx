import { useState, useEffect } from 'react'
import { useT } from '../i18n'
import { Card, CardHeader, CardContent } from './ui/card'
import { Input } from './ui/input'
import { Button } from './ui/button'
import type { AnalysisRequest } from '../api/types'

interface Props {
  pendingPoint: { lat: number; lon: number } | null
  onSubmit: (req: AnalysisRequest) => void
  loading: boolean
}

type Tab = 'wgs84' | 'lest97'

export default function CoordInput({ pendingPoint, onSubmit, loading }: Props) {
  const { t } = useT()
  const [tab, setTab] = useState<Tab>('wgs84')
  const [lat, setLat] = useState('')
  const [lon, setLon] = useState('')
  const [x, setX] = useState('')
  const [y, setY] = useState('')

  useEffect(() => {
    if (pendingPoint) {
      setLat(pendingPoint.lat.toFixed(6))
      setLon(pendingPoint.lon.toFixed(6))
      setTab('wgs84')
    }
  }, [pendingPoint])

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (tab === 'wgs84') {
      const latN = parseFloat(lat)
      const lonN = parseFloat(lon)
      if (isNaN(latN) || isNaN(lonN)) return
      onSubmit({ point_wgs84: { lat: latN, lon: lonN } })
    } else {
      const xN = parseFloat(x)
      const yN = parseFloat(y)
      if (isNaN(xN) || isNaN(yN)) return
      onSubmit({ point_lest97: { x: xN, y: yN } })
    }
  }

  return (
    <Card>
      <CardHeader>
        <span className="text-sm font-semibold text-slate-700">{t('coordInput')}</span>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit} className="space-y-3">
          {/* Tab strip */}
          <div className="flex gap-0.5 bg-slate-100 rounded-lg p-1">
            {(['wgs84', 'lest97'] as Tab[]).map(tid => (
              <button
                key={tid}
                type="button"
                onClick={() => setTab(tid)}
                className={`flex-1 py-1.5 text-xs font-semibold rounded-md transition-all ${
                  tab === tid
                    ? 'bg-white text-blue-700 shadow-sm'
                    : 'text-slate-500 hover:text-slate-700'
                }`}
              >
                {t(tid === 'wgs84' ? 'tabWgs84' : 'tabLest97')}
              </button>
            ))}
          </div>

          {tab === 'wgs84' ? (
            <div className="grid grid-cols-2 gap-2">
              <Field label={t('latLabel')} value={lat} onChange={setLat} placeholder="59.3765" />
              <Field label={t('lonLabel')} value={lon} onChange={setLon} placeholder="24.7536" />
            </div>
          ) : (
            <div className="grid grid-cols-2 gap-2">
              <Field label={t('eastingLabel')} value={x} onChange={setX} placeholder="541234" />
              <Field label={t('northingLabel')} value={y} onChange={setY} placeholder="6588765" />
            </div>
          )}

          <Button type="submit" size="full" disabled={loading}>
            {loading ? t('loading') : t('calcButton')}
          </Button>
        </form>
      </CardContent>
    </Card>
  )
}

interface FieldProps {
  label: string
  value: string
  onChange: (v: string) => void
  placeholder: string
}

function Field({ label, value, onChange, placeholder }: FieldProps) {
  return (
    <div>
      <label className="block text-xs font-medium text-slate-500 mb-1">{label}</label>
      <Input
        type="text"
        inputMode="decimal"
        value={value}
        onChange={e => onChange(e.target.value)}
        placeholder={placeholder}
      />
    </div>
  )
}
