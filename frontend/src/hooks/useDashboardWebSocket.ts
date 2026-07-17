import { useEffect, useRef } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { dashboardWebSocketUrl } from "@/lib/api";
import { queryKeys } from "@/hooks/queries";
import { getAuthToken } from "@/stores/auth";
import type {
  DashboardMetricsResponse,
  DashboardWebSocketMessage,
} from "@/types/api";

const RECONNECT_MS = 5_000;

function isMetricsPayload(value: unknown): value is DashboardMetricsResponse {
  if (!value || typeof value !== "object") return false;
  const m = value as Record<string, unknown>;
  return (
    typeof m.agents_total === "number" &&
    typeof m.agents_online === "number" &&
    typeof m.security_score === "number" &&
    typeof m.prompts_24h === "number"
  );
}

/**
 * Subscribes to live dashboard metrics/threats over WebSocket and
 * updates TanStack Query caches when updates arrive.
 */
export function useDashboardWebSocket(enabled = true) {
  const qc = useQueryClient();
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const enabledRef = useRef(enabled);
  enabledRef.current = enabled;

  useEffect(() => {
    if (!enabled) return;

    let cancelled = false;

    function connect() {
      if (cancelled) return;
      const token = getAuthToken();
      if (!token) return;

      // Avoid duplicate sockets (React Strict Mode remount / fast reconnect).
      if (
        wsRef.current &&
        (wsRef.current.readyState === WebSocket.OPEN ||
          wsRef.current.readyState === WebSocket.CONNECTING)
      ) {
        return;
      }

      const ws = new WebSocket(dashboardWebSocketUrl(token));
      wsRef.current = ws;

      ws.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data as string) as DashboardWebSocketMessage;
          if (msg.type === "dashboard_update") {
            // Ignore malformed/empty frames so we never flash zeros over good REST data.
            if (!isMetricsPayload(msg.metrics)) return;
            qc.setQueryData(queryKeys.dashboardMetrics, msg.metrics);
            if (Array.isArray(msg.threats)) {
              qc.setQueryData(queryKeys.threats(6), msg.threats);
              qc.setQueryData(queryKeys.threats(50), msg.threats);
            }
          } else if (msg.type === "event") {
            void qc.invalidateQueries({ queryKey: queryKeys.dashboardMetrics });
            void qc.invalidateQueries({
              queryKey: ["admin", "dashboard", "threats"],
            });
            void qc.invalidateQueries({ queryKey: queryKeys.audit(50) });
          }
        } catch {
          /* ignore malformed frames */
        }
      };

      ws.onclose = () => {
        if (wsRef.current === ws) wsRef.current = null;
        if (!cancelled && enabledRef.current) {
          reconnectRef.current = setTimeout(connect, RECONNECT_MS);
        }
      };

      ws.onerror = () => {
        ws.close();
      };
    }

    connect();

    return () => {
      cancelled = true;
      if (reconnectRef.current) clearTimeout(reconnectRef.current);
      reconnectRef.current = null;
      wsRef.current?.close();
      wsRef.current = null;
    };
  }, [enabled, qc]);
}
