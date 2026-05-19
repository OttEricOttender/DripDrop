import { useState } from 'react'
import type { AnalysisResult } from '../api/types'
import { useT } from '../i18n'
import LandCoverBar from './LandCoverBar'

interface Props {
  result: AnalysisResult
}

async function downloadPdfReport(result: AnalysisResult): Promise<void> {
  const resp = await fetch('/api/report', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(result),
  })
  if (!resp.ok) {
    let detail = resp.statusText
    try {
      const body = await resp.json() as { detail?: string }
      if (body.detail) detail = body.detail
    } catch { /* ignore */ }
    throw new Error(detail)
  }
  const blob = await resp.blob()
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  const cd = resp.headers.get('Content-Disposition') ?? ''
  const match = cd.match(/filename="([^"]+)"/)
  a.href = url
  a.download = match ? match[1] : `hydrocalc_${result.run_id.slice(0, 8)}.pdf`
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  const [open, setOpen] = useState(true)
  return (
    <div className="border border-gray-200 rounded">
      <button
        onClick={() => setOpen(o => !o)}
        className="w-full flex justify-between items-center px-3 py-2 text-sm font-semibold text-gray-800 bg-gray-50 hover:bg-gray-100 rounded"
      >
        {title}
        <span className="text-gray-400">{open ? '▲' : '▼'}</span>
      </button>
      {open && <div className="px-3 py-2 space-y-1">{children}</div>}
    </div>
  )
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between text-sm">
      <span className="text-gray-500">{label}</span>
      <span className="font-medium text-gray-800">{value}</span>
    </div>
  )
}

export default function ResultPanel({ result }: Props) {
  const { t } = useT()
  const h = result.hommik
  const [pdfLoading, setPdfLoading] = useState(false)
  const [pdfError, setPdfError] = useState<string | null>(null)

  async function handleDownloadPdf() {
    setPdfLoading(true)
    setPdfError(null)
    try {
      await downloadPdfReport(result)
    } catch (e) {
      setPdfError(e instanceof Error ? e.message : t('downloadPdfError'))
    } finally {
      setPdfLoading(false)
    }
  }

  return (
    <div className="space-y-2">
      {/* Headline numbers */}
      <div className="grid grid-cols-2 gap-2">
        <BigNum
          label={t('Q_kev_max')}
          value={h.Q_kev_max_m3_per_s.toFixed(3)}
          unit={t('unitM3s')}
          color="text-blue-700"
        />
        <BigNum
          label={t('Q_veg_max')}
          value={h.Q_veg_max_m3_per_s.toFixed(3)}
          unit={t('unitM3s')}
          color="text-teal-700"
        />
      </div>

      {h.area_floored_to_100km2 && (
        <p className="text-xs text-amber-700 bg-amber-50 px-2 py-1 rounded">
          {t('areaFloored')}
        </p>
      )}

      <button
        onClick={handleDownloadPdf}
        disabled={pdfLoading}
        className="w-full py-2 text-sm font-semibold rounded bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
      >
        {pdfLoading ? t('downloadPdfLoading') : t('downloadPdf')}
      </button>
      {pdfError && (
        <p className="text-xs text-red-700 bg-red-50 px-2 py-1 rounded">{pdfError}</p>
      )}

      <Section title={t('riverSection')}>
        <Row label={t('riverName')} value={result.river.name} />
        <Row label={t('riverCode')} value={result.river.code} />
        {result.river.river_type && (
          <Row label={t('riverType')} value={result.river.river_type} />
        )}
        {result.river.length_m != null && (
          <Row label={t('riverLength')} value={`${(result.river.length_m / 1000).toFixed(1)} km`} />
        )}
        <Row
          label=""
          value={result.river.is_main ? t('riverIsMain') : t('riverIsTributary')}
        />
      </Section>

      <Section title={t('catchmentSection')}>
        <Row label={t('catchmentArea')} value={`${result.catchment.area_km2.toFixed(2)} ${t('unitKm2')}`} />
        {result.catchment.code && (
          <Row label={t('catchmentCode')} value={result.catchment.code} />
        )}
        <Row label={t('snapDistance')} value={`${result.snap_distance_m.toFixed(0)} ${t('unitM')}`} />
      </Section>

      <Section title={t('landcoverSection')}>
        <LandCoverBar lc={result.landcover} />
      </Section>

      <Section title={t('resultsSection')}>
        <Row label={t('q_bar')} value={`${h.q_bar_l_per_s_km2.toFixed(2)} ${t('unitLsKm2')}`} />
        <Row label={t('delta_q')} value={`${h.delta_q_l_per_s_km2.toFixed(2)} ${t('unitLsKm2')}`} />
        <Row label={t('k95')} value={h.k95.toFixed(3)} />
        <Row label={t('r_s')} value={h.r_s.toFixed(3)} />
        <Row label={t('r')} value={h.r.toFixed(3)} />
        <Row label={t('q_kev_max_mod')} value={`${h.q_kev_max_l_per_s_km2.toFixed(2)} ${t('unitLsKm2')}`} />
        <Row label={t('q_veg_max_mod')} value={`${h.q_veg_max_l_per_s_km2.toFixed(2)} ${t('unitLsKm2')}`} />
        <Row label={t('formulaRevision')} value={h.formula_revision} />
      </Section>

      {result.dataset_versions.length > 0 && (
        <Section title={t('datasetsSection')}>
          {result.dataset_versions.map(d => (
            <div key={d.name} className="text-xs text-gray-600">
              <span className="font-medium">{d.name}</span>
              {' — '}
              {new Date(d.retrieved_at).toLocaleDateString()}
            </div>
          ))}
        </Section>
      )}
    </div>
  )
}

interface BigNumProps {
  label: string
  value: string
  unit: string
  color: string
}

function BigNum({ label, value, unit, color }: BigNumProps) {
  return (
    <div className="bg-gray-50 rounded p-2 text-center">
      <div className="text-xs text-gray-500 leading-tight">{label}</div>
      <div className={`text-2xl font-bold ${color}`}>{value}</div>
      <div className="text-xs text-gray-500">{unit}</div>
    </div>
  )
}
