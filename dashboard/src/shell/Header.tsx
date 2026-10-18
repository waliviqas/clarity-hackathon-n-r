import { useEffect, useMemo, useState } from 'react';
import { isCrimeActivity, isScripted, LABELS, useConnection, useEvents, useIncidents, useStore } from '../lib';
import { useDemoRunning } from './DemoControls.tsx';

const CONNECTION_WORDS = { open: 'Connected', connecting: 'Connecting', closed: 'Disconnected' } as const;

const CLOCK_FORMAT = new Intl.DateTimeFormat('en-US', {
  timeZone: 'America/New_York', hour: 'numeric', minute: '2-digit', second: '2-digit', hour12: true,
});

/** Live wall clock (Raleigh time), one interval, cleaned up on unmount. */
function WallClock() {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const id = window.setInterval(() => setNow(new Date()), 1000);
    return () => window.clearInterval(id);
  }, []);
  return <span className="header-clock" title="Local time (Eastern)">{CLOCK_FORMAT.format(now)}</span>;
}

/** "3 crimes · 2 awaiting decision"; hidden when no crime has been relayed yet. */
function CrimeSummary() {
  const events = useEvents();
  const incidents = useIncidents();
  const crimes = useMemo(() => {
    const subjects = new Set<string>();
    for (const e of events) {
      if (e.type === 'relay' && isCrimeActivity(e.activity)) subjects.add(e.subject_id);
    }
    return subjects.size;
  }, [events]);
  const awaiting = incidents.filter((i) => i.action === null).length;
  if (crimes === 0) return null;
  return (
    <span className="header-summary">
      {crimes} {crimes === 1 ? 'crime' : 'crimes'}
      {awaiting > 0 && (
        <>
          {' · '}
          <span className="header-awaiting">{awaiting} awaiting decision</span>
        </>
      )}
    </span>
  );
}

export function Header() {
  const connection = useConnection();
  const scripted = useStore((s) => s.events.some(isScripted));
  const running = useDemoRunning();

  return (
    <header className="header">
      <span className={`header-brand${running ? ' header-brand-live' : ''}`} role="img" aria-label="Clarity">
        <svg viewBox="0 0 64 40" width="44" height="28" aria-hidden="true">
          <defs>
            <linearGradient id="eye-grad" x1="0" y1="0" x2="1" y2="1">
              <stop offset="0" stopColor="#A9DDFB" />
              <stop offset="1" stopColor="var(--chase-2)" />
            </linearGradient>
          </defs>
          <g className="eye-lid">
            <path d="M4 20 C14 5, 50 5, 60 20 C50 35, 14 35, 4 20 Z" fill="none" stroke="url(#eye-grad)"
              strokeWidth="3.2" strokeLinejoin="round" />
            <circle cx="32" cy="20" r="6.5" fill="url(#eye-grad)" />
          </g>
        </svg>
        <span className="header-wordmark">CLARITY</span>
      </span>
      <CrimeSummary />
      <span className="header-spacer" />
      {scripted && <span className="tag">{LABELS.scripted}</span>}
      <WallClock />
      <span className={`conn conn-${connection.state}`} title="Event bus connection">
        <span className="conn-dot" aria-hidden="true" />
        {CONNECTION_WORDS[connection.state]}
      </span>
    </header>
  );
}
