// The few Node APIs the check scripts use (the dashboard doesn't depend on @types/node).
declare module 'node:fs' {
  export function readFileSync(path: string | URL, encoding: 'utf8' | 'utf-8'): string;
}
