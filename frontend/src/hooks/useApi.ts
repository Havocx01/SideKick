import { useCallback, useEffect, useState } from "react";

import { ApiError } from "../api/client";

export interface AsyncState<T> {
  data: T | null;
  loading: boolean;
  error: ApiError | Error | null;
  reload: () => void;
}

export function useApi<T>(fetcher: () => Promise<T>, deps: unknown[] = []): AsyncState<T> {
  const [nonce, setNonce] = useState(0);
  const run = useCallback(fetcher, deps);
  const [state, setState] = useState<{ run: typeof run; nonce: number; data: T | null; loading: boolean; error: Error | null } | null>(null);

  useEffect(() => {
    let cancelled = false;
    setState({ run, nonce, data: null, loading: true, error: null });
    async function load() {
      try {
        const data = await run();
        if (!cancelled) setState({ run, nonce, data, loading: false, error: null });
      } catch (error) {
        if (!cancelled) setState({ run, nonce, data: null, loading: false, error: error as Error });
      }
    }
    void load();
    return () => { cancelled = true; };
  }, [run, nonce]);

  const current = state?.run === run && state.nonce === nonce ? state : null;
  return { data: current?.data ?? null, loading: current?.loading ?? true, error: current?.error ?? null,
    reload: () => setNonce(value => value + 1) };
}
