import { Component, type ErrorInfo, type ReactNode } from "react";

interface Props {
  children: ReactNode;
}

interface State {
  error: Error | null;
}

/** Prevents a render crash from leaving a blank white #root. */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error("UI crash:", error, info.componentStack);
  }

  render() {
    if (this.state.error) {
      return (
        <div className="flex min-h-screen flex-col items-center justify-center bg-ink-50 px-6 text-center">
          <h1 className="text-xl font-semibold text-ink-900">Something went wrong</h1>
          <p className="mt-2 max-w-md text-sm text-ink-500">
            {this.state.error.message || "The console failed to render."}
          </p>
          <button
            type="button"
            className="btn-primary mt-6"
            onClick={() => window.location.assign("/dashboard")}
          >
            Reload dashboard
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
