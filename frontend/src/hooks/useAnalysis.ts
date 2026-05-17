import { useState } from 'react'
import { runAnalysis } from '../api/analyze'
import type { AnalysisRequest, AnalysisResult } from '../api/types'

type AnalysisState =
  | { status: 'idle' }
  | { status: 'loading' }
  | { status: 'success'; result: AnalysisResult }
  | { status: 'error'; message: string }

export function useAnalysis() {
  const [state, setState] = useState<AnalysisState>({ status: 'idle' })

  async function run(req: AnalysisRequest): Promise<void> {
    setState({ status: 'loading' })
    try {
      const result = await runAnalysis(req)
      setState({ status: 'success', result })
    } catch (err) {
      setState({
        status: 'error',
        message: err instanceof Error ? err.message : String(err),
      })
    }
  }

  function reset(): void {
    setState({ status: 'idle' })
  }

  return { state, run, reset }
}
