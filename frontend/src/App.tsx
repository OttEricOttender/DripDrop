import { useState } from 'react'
import { Droplets } from 'lucide-react'
import { LanguageContext, makeT, type Lang } from './i18n'
import MapView from './components/MapView'
import CoordInput from './components/CoordInput'
import ProbabilitySelect from './components/ProbabilitySelect'
import ResultPanel from './components/ResultPanel'
import WarningBanner from './components/WarningBanner'
import { useAnalysis } from './hooks/useAnalysis'
import type { AnalysisRequest } from './api/types'

export default function App() {
  const [lang, setLang] = useState<Lang>('et')
  const t = makeT(lang)
  const { state, run } = useAnalysis()
  const [pendingPoint, setPendingPoint] = useState<{ lat: number; lon: number } | null>(null)
  const [p, setP] = useState(10)

  const result = state.status === 'success' ? state.result : null

  async function handleRun(req: AnalysisRequest) {
    if (req.point_wgs84) {
      setPendingPoint({ lat: req.point_wgs84.lat, lon: req.point_wgs84.lon })
    }
    await run({ ...req, p_percent: p })
  }

  async function handleMapClick(lat: number, lon: number) {
    const point = { lat, lon }
    setPendingPoint(point)
    await handleRun({ point_wgs84: point })
  }

  return (
    <LanguageContext.Provider value={{ lang, setLang, t }}>
      <div className="flex" style={{ height: '100vh' }}>

        {/* ── Sidebar (owns the header) ───────────────────────────── */}
        <aside className="w-80 xl:w-96 bg-slate-50 border-r border-slate-200 flex flex-col shrink-0 z-10">

          {/* Header — sidebar-width only */}
          <header className="bg-gradient-to-r from-blue-950 to-blue-800 text-white px-5 py-3 flex items-center justify-between shrink-0 shadow-md">
            <div className="flex items-center gap-3">
              <Droplets className="w-8 h-8 text-blue-300" strokeWidth={1.75} />
              <span className="font-bold text-2xl tracking-tight">{t('appTitle')}</span>
            </div>
            <button
              onClick={() => setLang(lang === 'et' ? 'en' : 'et')}
              className="text-xs font-semibold border border-blue-500/60 px-3 py-1.5 rounded-lg hover:bg-blue-700/50 hover:border-blue-400 transition-all"
              title="Toggle language / Vaheta keel"
            >
              {lang === 'et' ? 'EN' : 'ET'}
            </button>
          </header>

          <div className="flex-1 overflow-y-auto p-4 space-y-3">
              <CoordInput
                pendingPoint={pendingPoint}
                onSubmit={handleRun}
                loading={state.status === 'loading'}
              />
              <ProbabilitySelect value={p} onChange={setP} />

              {state.status === 'error' && (
                <div className="bg-red-50 border border-red-200 text-red-800 rounded-xl p-3 text-sm">
                  {state.message}
                </div>
              )}

              {result && (
                <div className="space-y-2">
                  {result.warnings.map((w, i) => (
                    <WarningBanner
                      key={i}
                      message={w}
                      isPlaceholder={result.q_bar_k_is_placeholder}
                    />
                  ))}
                  <ResultPanel result={result} />
                </div>
              )}
          </div>
        </aside>

        {/* ── Map ────────────────────────────────────────────────── */}
        <div className="flex-1 relative min-w-0">
            <MapView
              onMapClick={handleMapClick}
              clickedPoint={pendingPoint}
              result={result}
            />
            {!result && state.status !== 'loading' && (
              <div className="absolute bottom-8 left-1/2 -translate-x-1/2 bg-white/95 backdrop-blur px-4 py-2 rounded-full shadow-lg text-sm text-slate-500 pointer-events-none border border-slate-200 z-[500]">
                {t('clickMapHint')}
              </div>
            )}
            {state.status === 'loading' && (
              <div className="absolute inset-0 bg-slate-900/20 backdrop-blur-sm flex items-center justify-center pointer-events-none z-[1000]">
                <div className="bg-white rounded-2xl shadow-2xl px-8 py-5 text-blue-800 font-semibold flex flex-col items-center gap-3">
                  {/* Water-drop falling animation */}
                  <div className="flex items-end gap-2 h-8">
                    {[0, 1, 2, 3].map(i => (
                      <Droplets
                        key={i}
                        className="w-5 h-5 text-blue-500 animate-water-drop"
                        style={{ animationDelay: `${i * 0.28}s` }}
                      />
                    ))}
                  </div>
                  {/* Flowing wave bar */}
                  <div className="flex gap-0.5">
                    {[0,1,2,3,4,5,6,7].map(i => (
                      <div
                        key={i}
                        className="w-1.5 bg-blue-400 rounded-full animate-wave-flow"
                        style={{
                          height: `${8 + Math.sin(i * 0.9) * 6}px`,
                          animationDelay: `${i * 0.12}s`,
                        }}
                      />
                    ))}
                  </div>
                  <span className="text-sm tracking-wide">{t('loading')}</span>
                </div>
              </div>
            )}
        </div>

      </div>
    </LanguageContext.Provider>
  )
}
