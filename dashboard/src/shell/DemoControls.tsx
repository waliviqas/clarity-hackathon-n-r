import { useEffect, useState } from 'react';

// Run / Stop / Restart for the live demo, served by scripts/demo_control.py on the GPU box.
// Hidden in the bottom-right corner until hovered. Set VITE_CONTROL_URL in dashboard/.env.
const raw: string | undefined = import.meta.env?.VITE_CONTROL_URL;
const CONTROL_URL = (raw && raw.trim() ? raw.trim() : 'http://127.0.0.1:8090').replace(/\/+$/, '');

type Action = 'run' | 'stop' | 'restart';

/** True while a demo run is going (polls the control service's /status every 2 s). */
export function useDemoRunning(): boolean {
  const [running, setRunning] = useState(false);
  useEffect(() => {
    let alive = true;
    const poll = async () => {
      try {
        const res = await fetch(`${CONTROL_URL}/status`);
        const body = await res.json();
        if (alive) setRunning(body.running === true);
      } catch {
        if (alive) setRunning(false);
      }
    };
    poll();
    const timer = setInterval(poll, 2000);
    return () => { alive = false; clearInterval(timer); };
  }, []);
  return running;
}

export function DemoControls() {
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState('');

  const send = async (action: Action) => {
    setBusy(true);
    setNote(`${action}…`);
    try {
      const res = await fetch(`${CONTROL_URL}/${action}`, { method: 'POST' });
      const body = await res.json().catch(() => ({}));
      setNote(typeof body.message === 'string' ? body.message : `HTTP ${res.status}`);
    } catch {
      setNote(`can't reach ${CONTROL_URL}`);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="demo-controls">
      {note && <span className="demo-note">{note}</span>}
      <button disabled={busy} onClick={() => send('run')}>Run</button>
      <button disabled={busy} onClick={() => send('stop')}>Stop</button>
      <button disabled={busy} onClick={() => send('restart')}>Restart</button>
    </div>
  );
}
