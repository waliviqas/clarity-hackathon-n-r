// Where the bus lives. Set VITE_BUS_URL in dashboard/.env; default is the local / port-forwarded bus.
// (`import.meta.env` is undefined under plain Node, which scripts/check-store.ts relies on.)

const raw: string | undefined = import.meta.env?.VITE_BUS_URL;

/** e.g. http://127.0.0.1:8080 (no trailing slash). */
export const BUS_URL: string = (raw && raw.trim() ? raw.trim() : 'http://127.0.0.1:8080').replace(/\/+$/, '');

/** e.g. ws://127.0.0.1:8080/ws (https -> wss). */
export const BUS_WS_URL: string = BUS_URL.replace(/^http/i, 'ws') + '/ws';
