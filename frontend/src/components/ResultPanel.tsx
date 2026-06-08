import { useState } from 'react'
import { ChevronDown, ChevronUp, Download } from 'lucide-react'
import type { AnalysisResult } from '../api/types'
import { useT } from '../i18n'
import LandCoverBar from './LandCoverBar'
import { Card, CardContent } from './ui/card'
import { Button } from './ui/button'
import { Badge } from './ui/badge'

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

function Section({ title, children, defaultOpen = true }: {
  title: string
  children: React.ReactNode
  defaultOpen?: boolean
}) {
  const [open, setOpen] = useState(defaultOpen)
  return (
    <Card>
      <button
        onClick={() => setOpen(o => !o)}
        className="w-full flex justify-between items-center px-4 py-3 text-sm font-semibold text-slate-700 hover:bg-slate-50 rounded-xl transition-colors"
      >
        {title}
        {open
          ? <ChevronUp className="w-4 h-4 text-slate-400" />
          : <ChevronDown className="w-4 h-4 text-slate-400" />
        }
      </button>
      {open && (
        <CardContent className="pt-0 border-t border-slate-100">
          {children}
        </CardContent>
      )}
    </Card>
  )
}

function Row({ label, value, accent }: { label: string; value: React.ReactNode; accent?: boolean }) {
  return (
    <div className="flex justify-between items-center py-1 text-sm">
      <span className="text-slate-500">{label}</span>
      <span className={accent ? 'font-semibold text-blue-700' : 'font-medium text-slate-800'}>
        {value}
      </span>
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
    <div className="space-y-3">

      {/* ── Headline Q values ──────────────────────────────────── */}
      <div className="grid grid-cols-2 gap-2">
        <StatCard
          label={t('Q_kev_max')}
          value={h.Q_kev_max_m3_per_s.toFixed(3)}
          unit={t('unitM3s')}
          accent="blue"
        />
        <StatCard
          label={t('Q_veg_max')}
          value={h.Q_veg_max_m3_per_s.toFixed(3)}
          unit={t('unitM3s')}
          accent="teal"
        />
      </div>

      {h.area_floored_to_100km2 && (
        <div className="bg-amber-50 border border-amber-200 text-amber-800 rounded-xl px-3 py-2 text-xs">
          {t('areaFloored')}
        </div>
      )}

      {/* ── PDF download ───────────────────────────────────────── */}
      <Button
        variant="default"
        size="full"
        onClick={handleDownloadPdf}
        disabled={pdfLoading}
        className="gap-2"
      >
        <Download className="w-4 h-4" />
        {pdfLoading ? t('downloadPdfLoading') : t('downloadPdf')}
      </Button>
      {pdfError && (
        <p className="text-xs text-red-700 bg-red-50 border border-red-200 rounded-lg px-3 py-2">{pdfError}</p>
      )}

      {/* ── River ──────────────────────────────────────────────── */}
      <Section title={t('riverSection')}>
        <Row label={t('riverName')} value={result.river.name} />
        <Row
          label={t('riverCode')}
          value={<Badge variant="outline">{result.river.code}</Badge>}
        />
        {result.river.river_type && (
          <Row label={t('riverType')} value={result.river.river_type} />
        )}
        {result.river.length_m != null && (
          <Row
            label={t('riverLength')}
            value={`${(result.river.length_m / 1000).toFixed(1)} km`}
          />
        )}
        <Row
          label=""
          value={
            <Badge variant={result.river.is_main ? 'default' : 'secondary'}>
              {result.river.is_main ? t('riverIsMain') : t('riverIsTributary')}
            </Badge>
          }
        />
      </Section>

      {/* ── Catchment ──────────────────────────────────────────── */}
      <Section title={t('catchmentSection')}>
        <Row
          label={t('catchmentArea')}
          value={`${result.catchment.area_km2.toFixed(2)} ${t('unitKm2')}`}
          accent
        />
        {result.catchment.code && (
          <Row
            label={t('catchmentCode')}
            value={<Badge variant="outline">{result.catchment.code}</Badge>}
          />
        )}
        <Row label={t('snapDistance')} value={`${result.snap_distance_m.toFixed(0)} ${t('unitM')}`} />
        {result.catchment.dem_resolution_m !== 5 && (
          <Row
            label="DEM"
            value={<Badge variant="secondary">{result.catchment.dem_resolution_m} m (fallback)</Badge>}
          />
        )}
      </Section>

      {/* ── Land cover ─────────────────────────────────────────── */}
      <Section title={t('landcoverSection')}>
        <LandCoverBar lc={result.landcover} />
      </Section>

      {/* ── Hommik results ─────────────────────────────────────── */}
      <Section title={t('resultsSection')}>
        <Row label={t('q_bar')} value={`${h.q_bar_l_per_s_km2.toFixed(2)} ${t('unitLsKm2')}`} />
        <Row label={t('delta_q')} value={`${h.delta_q_l_per_s_km2.toFixed(2)} ${t('unitLsKm2')}`} />
        <Row label={t('k95')} value={h.k95.toFixed(3)} />
        <Row label={t('r_s')} value={h.r_s.toFixed(3)} />
        <Row label={t('r')} value={h.r.toFixed(3)} />
        <Row label={t('q_kev_max_mod')} value={`${h.q_kev_max_l_per_s_km2.toFixed(2)} ${t('unitLsKm2')}`} />
        <Row label={t('q_veg_max_mod')} value={`${h.q_veg_max_l_per_s_km2.toFixed(2)} ${t('unitLsKm2')}`} />
        <Row
          label={t('formulaRevision')}
          value={<Badge variant="secondary">{h.formula_revision}</Badge>}
        />
      </Section>

      {/* ── Datasets ───────────────────────────────────────────── */}
      {result.dataset_versions.length > 0 && (
        <Section title={t('datasetsSection')} defaultOpen={false}>
          {result.dataset_versions.map(d => (
            <div key={d.name} className="py-1">
              <div className="flex items-center justify-between text-xs">
                <span className="font-medium text-slate-700">{d.name}</span>
                <span className="text-slate-400">{new Date(d.retrieved_at).toLocaleDateString()}</span>
              </div>
              <div className="font-mono text-slate-400 text-xs truncate mt-0.5">{d.sha256.slice(0, 16)}…</div>
            </div>
          ))}
        </Section>
      )}
    </div>
  )
}

function StatCard({
  label,
  value,
  unit,
  accent,
}: {
  label: string
  value: string
  unit: string
  accent: 'blue' | 'teal'
}) {
  const border = accent === 'blue' ? 'border-l-blue-500' : 'border-l-teal-500'
  const text = accent === 'blue' ? 'text-blue-700' : 'text-teal-700'
  return (
    <div className={`bg-white rounded-xl border border-slate-200 shadow-sm border-l-4 ${border} px-3 py-3`}>
      <div className="text-xs text-slate-500 leading-snug mb-1">{label}</div>
      <div className={`text-2xl font-bold tabular-nums ${text}`}>{value}</div>
      <div className="text-xs text-slate-400 mt-0.5">{unit}</div>
    </div>
  )
}
