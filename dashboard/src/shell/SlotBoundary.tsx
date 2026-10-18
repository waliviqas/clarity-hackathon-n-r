import { Component } from 'react';
import type { ErrorInfo, ReactNode } from 'react';

interface Props {
  /** Panel name for the console message, e.g. "map" or "incident cards". */
  name: string;
  children: ReactNode;
}

interface State {
  failed: boolean;
}

/**
 * Keeps one panel's crash inside its slot: if the map, graph, cards or receipts throw while rendering,
 * that slot shows a quiet note and the rest of the dashboard keeps running. The error goes to the
 * console (the operator never sees technical text). Reloading the page is the retry.
 */
export class SlotBoundary extends Component<Props, State> {
  state: State = { failed: false };

  static getDerivedStateFromError(): State {
    return { failed: true };
  }

  componentDidCatch(error: unknown, info: ErrorInfo): void {
    console.error(`[clarity] the ${this.props.name} panel hit an error`, error, info.componentStack);
  }

  render(): ReactNode {
    if (!this.state.failed) return this.props.children;
    return (
      <div className="slot-error" role="status">
        <p>This panel hit an error. Reload to retry.</p>
        <button type="button" onClick={() => window.location.reload()}>Reload</button>
      </div>
    );
  }
}
