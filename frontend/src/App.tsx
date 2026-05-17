import { useState } from 'react'
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
    await run({ ...req, p_percent: p })
  }

  async function handleMapClick(lat: number, lon: number) {
    const point = { lat, lon }
    setPendingPoint(point)
    await handleRun({ point_wgs84: point })
  }

  return (
    <LanguageContext.Provider value={{ lang, setLang, t }}>
      <div className="flex flex-col" style={{ height: '100vh' }}>
        {/* ── Header ─────────────────────────────────────────────── */}
        <header className="bg-blue-900 text-white px-4 py-2 flex items-center justify-between shrink-0">
          <div className="flex items-baseline gap-2">
            <span className="font-bold text-lg">{t('appTitle')}</span>
            <span className="text-blue-300 text-sm hidden sm:inline">{t('appSubtitle')}</span>
          </div>
          <button
            onClick={() => setLang(lang === 'et' ? 'en' : 'et')}
            className="text-sm border border-blue-500 px-2 py-1 rounded hover:bg-blue-800 transition-colors"
            title="Toggle language / Vaheta keel"
          >
            {lang === 'et' ? 'EN' : 'ET'}
          </button>
        </header>

        {/* ── Body ───────────────────────────────────────────────── */}
        <div className="flex flex-1 min-h-0">
          {/* Sidebar */}
          <aside className="w-80 xl:w-96 bg-white shadow-xl flex flex-col overflow-y-auto shrink-0 z-10">
            <div className="p-4 space-y-4">
              <CoordInput
                pendingPoint={pendingPoint}
                onSubmit={handleRun}
                loading={state.status === 'loading'}
              />
              <ProbabilitySelect value={p} onChange={setP} />

              {state.status === 'error' && (
                <div className="bg-red-50 border border-red-300 text-red-800 rounded p-3 text-sm">
                  {state.message}
                </div>
              )}

              {result && (
                <div className="space-y-2">
                  {result.warnings.map((w, i) => (
                    <WarningBanner
                      key={i}
                      message={w}
                      isPlaceholder={w.includes('placeholder') || w.includes('asendusarvutus')}
                    />
                  ))}
                  <ResultPanel result={result} />
                </div>
              )}
            </div>
          </aside>

          {/* Map */}
          <div className="flex-1 relative min-w-0">
            <MapView
              onMapClick={handleMapClick}
              clickedPoint={pendingPoint}
              result={result}
            />
            {!result && state.status !== 'loading' && (
              <div className="absolute bottom-8 left-1/2 -translate-x-1/2 bg-white/90 backdrop-blur px-4 py-2 rounded shadow text-sm text-gray-600 pointer-events-none">
                {t('clickMapHint')}
              </div>
            )}
            {state.status === 'loading' && (
              <div className="absolute inset-0 bg-white/30 backdrop-blur-sm flex items-center justify-center pointer-events-none">
                <div className="bg-white rounded-lg shadow px-6 py-3 text-blue-700 font-medium animate-pulse">
                  {t('loading')}
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </LanguageContext.Provider>
  )
}
