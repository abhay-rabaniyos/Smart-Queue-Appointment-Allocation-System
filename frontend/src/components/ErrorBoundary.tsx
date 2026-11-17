import { Component, type ErrorInfo, type ReactNode } from "react";

export default class ErrorBoundary extends Component<
  { children: ReactNode },
  { failed: boolean }
> {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  componentDidCatch(_error: Error, _info: ErrorInfo) {
    /* Add a redacted error-monitoring adapter here. */
  }
  render() {
    return this.state.failed ? (
      <main style={{ margin: 0, padding: 40, width: "100%" }}>
        <h1>Let’s reconnect your visit.</h1>
        <p>
          Your token is saved in this browser session. Reload to recover the
          current queue state.
        </p>
        <button className="primary" onClick={() => location.reload()}>
          Reload QueuePilot
        </button>
      </main>
    ) : (
      this.props.children
    );
  }
}
