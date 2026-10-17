// The shared dashboard API. Graph and panels import from here only: `import { useIncidents } from '../lib';`
// Owner: dashboard-map builder. Ask for changes instead of editing. See README.md in this folder.

export * from './types.ts';
export * from './constants.ts';
export { BUS_URL, BUS_WS_URL } from './config.ts';
export type { CamerasView, Connection, ConnectionState, IncidentView, StoreState } from './state.ts';
export { cameraOf, evidenceOf, isScripted } from './state.ts';
export { chaseVar, colorFor, getEvent, getState, select, subjectOf, subscribe } from './store.ts';
export { refreshCameras, sendOperatorAction, startBus } from './bus.ts';
export type { SendResult } from './bus.ts';
export * from './hooks.ts';
