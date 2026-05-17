import type { AnalysisRequest, AnalysisResult } from './types'

export async function runAnalysis(req: AnalysisRequest): Promise<AnalysisResult> {
  const resp = await fetch('/api/analyze', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(req),
  })
  if (!resp.ok) {
    let detail = resp.statusText
    try {
      const body = await resp.json() as { detail?: string }
      if (body.detail) detail = body.detail
    } catch { /* ignore parse error */ }
    throw new Error(detail)
  }
  return resp.json() as Promise<AnalysisResult>
}
