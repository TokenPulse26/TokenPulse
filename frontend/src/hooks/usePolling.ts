import { useEffect, useRef, useState } from 'react'

interface PollState<T> {
  data: T | null
  error: string | null
  loading: boolean
}

/**
 * Fetch on mount and re-fetch every `intervalMs`, keeping the last good
 * data visible while a refresh is in flight or failing. Pass the values the
 * fetcher closes over (e.g. the selected range) as `deps` to restart the
 * cycle when they change — the fetcher itself may be an inline arrow.
 */
export function usePolling<T>(
  fetcher: () => Promise<T>,
  intervalMs: number,
  deps: unknown[] = [],
): PollState<T> {
  const [state, setState] = useState<PollState<T>>({ data: null, error: null, loading: true })
  const fetcherRef = useRef(fetcher)
  fetcherRef.current = fetcher

  useEffect(() => {
    let cancelled = false
    const tick = async () => {
      try {
        const data = await fetcherRef.current()
        if (!cancelled) setState({ data, error: null, loading: false })
      } catch (e) {
        if (!cancelled)
          setState((prev) => ({
            ...prev,
            error: e instanceof Error ? e.message : String(e),
            loading: false,
          }))
      }
    }
    setState((prev) => ({ ...prev, loading: true }))
    void tick()
    const id = setInterval(() => void tick(), intervalMs)
    return () => {
      cancelled = true
      clearInterval(id)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [intervalMs, ...deps])

  return state
}
