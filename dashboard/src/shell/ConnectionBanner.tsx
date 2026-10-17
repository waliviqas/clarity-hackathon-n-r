import { useEffect, useState } from 'react';
import { useConnection } from '../lib';

/**
 * Shown while the bus WebSocket is down. The rest of the screen keeps the last state.
 * Operator words only; the technical reason (close code, URL) goes to the browser console (lib/bus.ts).
 */
export function ConnectionBanner() {
  const connection = useConnection();
  const down = connection.state === 'closed' || (connection.state === 'connecting' && connection.retries > 0);
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    if (!down) return;
    setNow(Date.now());
    const timer = setInterval(() => setNow(Date.now()), 250);
    return () => clearInterval(timer);
  }, [down]);

  if (!down) return null;
  const secs = connection.nextRetryAt ? Math.ceil((connection.nextRetryAt - now) / 1000) : 0;
  const retry = connection.state === 'closed' && secs > 0 ? `Retrying in ${secs} s.` : 'Retrying now.';

  return (
    <div className="banner" role="status" aria-live="polite">
      <span>Lost connection to the event bus. {retry}</span>
    </div>
  );
}
