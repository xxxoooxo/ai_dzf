import { useEffect, useRef, useState } from "react";

/**
 * Throttle a frequently changing value to at most once per animation frame.
 * Useful for streaming text to avoid blocking the main thread with too many renders.
 */
export function useRafThrottledValue<T>(value: T): T {
  const [throttledValue, setThrottledValue] = useState(value);
  const latestValueRef = useRef(value);
  const rafIdRef = useRef<number | null>(null);

  useEffect(() => {
    latestValueRef.current = value;
    if (rafIdRef.current != null) return;

    rafIdRef.current = requestAnimationFrame(() => {
      rafIdRef.current = null;
      setThrottledValue(latestValueRef.current);
    });
  }, [value]);

  useEffect(() => {
    return () => {
      if (rafIdRef.current != null) {
        cancelAnimationFrame(rafIdRef.current);
        rafIdRef.current = null;
      }
    };
  }, []);

  return throttledValue;
}

