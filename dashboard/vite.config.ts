import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// The bus allows CORS only from :5173, so never drift to another port silently.
// Bind IPv4 loopback explicitly: Node's default "localhost" can bind [::1] only, which breaks
// http://127.0.0.1:5173 (browsers still reach http://localhost:5173 via 127.0.0.1).
export default defineConfig({
  plugins: [react()],
  server: { host: '127.0.0.1', port: 5173, strictPort: true },
  preview: { host: '127.0.0.1', port: 5173, strictPort: true },
});
