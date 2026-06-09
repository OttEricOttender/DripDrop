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

export default function CoordInput({ pendingPoint, onSubmit, loading }: Props) {
  const { t } = useT()
  const [lat, setLat] = useState('')
  const [lon, setLon] = useState('')

  useEffect(() => {
    if (pendingPoint) {
      setLat(pendingPoint.lat.toFixed(6))
      setLon(pendingPoint.lon.toFixed(6))
    }
  }, [pendingPoint])

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    const latN = parseFloat(lat)
    const lonN = parseFloat(lon)
    if (isNaN(latN) || isNaN(lonN)) return
    onSubmit({ point_wgs84: { lat: latN, lon: lonN } })
  }

  return (
    <Card>
      <CardHeader>
        <span className="text-sm font-semibold text-slate-700">{t('coordInput')}</span>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit} className="space-y-3">
          <div className="grid grid-cols-2 gap-2">
            <Field label={t('latLabel')} value={lat} onChange={setLat} placeholder="59.3765" />
            <Field label={t('lonLabel')} value={lon} onChange={setLon} placeholder="24.7536" />
          </div>
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
