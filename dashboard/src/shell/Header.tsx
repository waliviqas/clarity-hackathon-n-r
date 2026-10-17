import { isScripted, LABELS, useCameras, useConnection, useRunId, useStore } from '../lib';

const CONNECTION_WORDS = { open: 'Connected', connecting: 'Connecting', closed: 'Disconnected' } as const;

export function Header() {
  const { site } = useCameras();
  const runId = useRunId();
  const connection = useConnection();
  const scripted = useStore((s) => s.events.some(isScripted));

  return (
    <header className="header">
      <span className="header-brand">Clarity</span>
      {site && <span className="header-site">{site.site_name ?? site.site_id}</span>}
      <span className="header-spacer" />
      {scripted && <span className="tag">{LABELS.scripted}</span>}
      {runId && <span className="header-run">Run {runId}</span>}
      <span className={`conn conn-${connection.state}`} title="Event bus connection">
        <span className="conn-dot" aria-hidden="true" />
        {CONNECTION_WORDS[connection.state]}
      </span>
    </header>
  );
}
