import { useMemo } from "react";
import { Link } from "react-router-dom";
import {
  Activity,
  Ban,
  FileClock,
  ScanEye,
  Server,
  ShieldAlert,
  ShieldCheck,
} from "lucide-react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { MetricCard } from "@/components/ui/MetricCard";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { PageHeader, ErrorState } from "@/components/ui/States";
import { useDashboardMetrics, useThreats } from "@/hooks/queries";
import { useDashboardWebSocket } from "@/hooks/useDashboardWebSocket";
import { formatRelative, titleCase } from "@/lib/utils";
import type { DailyActivityPoint } from "@/types/api";

function buildChartSeries(
  daily: DailyActivityPoint[],
): { day: string; events: number }[] {
  const buckets = new Map<string, number>();
  const today = new Date();
  for (let i = 6; i >= 0; i--) {
    const d = new Date(today);
    d.setDate(today.getDate() - i);
    buckets.set(d.toISOString().slice(0, 10), 0);
  }
  for (const point of daily) {
    if (buckets.has(point.date)) buckets.set(point.date, point.count);
  }
  return Array.from(buckets, ([date, events]) => ({
    day: new Date(date + "T00:00:00").toLocaleDateString("en-US", {
      weekday: "short",
    }),
    events,
  }));
}

function scoreAccent(score: number): "emerald" | "amber" | "rose" {
  if (score >= 80) return "emerald";
  if (score >= 60) return "amber";
  return "rose";
}

export function DashboardPage() {
  useDashboardWebSocket();
  const metricsQ = useDashboardMetrics();
  const threatsQ = useThreats(6);

  const metrics = metricsQ.data;
  const threats = threatsQ.data ?? [];

  const series = useMemo(
    () => buildChartSeries(metrics?.daily_activity ?? []),
    [metrics?.daily_activity],
  );

  if (metricsQ.isError) {
    return (
      <>
        <PageHeader title="Security Overview" />
        <div className="card">
          <ErrorState
            error={metricsQ.error}
            onRetry={() => metricsQ.refetch()}
          />
        </div>
      </>
    );
  }

  const score = metrics?.security_score ?? 0;
  // Prefer cached metrics while refetching — avoid flashing 0 when data is briefly undefined.
  const showPlaceholders = metricsQ.isLoading && !metrics;

  return (
    <>
      <PageHeader
        title="Security Overview"
        description="Live posture across your AI agent fleet, policies, and audit activity."
        actions={
          <span className="flex items-center gap-1.5 text-xs font-medium text-ink-500">
            <Activity className="h-3.5 w-3.5 text-emerald-500" />
            Live updates
          </span>
        }
      />

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <MetricCard
          label="Security Score"
          value={showPlaceholders ? "—" : score}
          icon={ShieldCheck}
          accent={scoreAccent(score)}
          loading={showPlaceholders}
          hint="0–100 posture index"
        />
        <MetricCard
          label="Active Agents"
          value={showPlaceholders ? "—" : (metrics?.agents_total ?? 0)}
          icon={Server}
          accent="brand"
          loading={showPlaceholders}
          hint={`${metrics?.agents_online ?? 0} online now`}
          trend={{
            value: `${metrics?.agents_online ?? 0}/${metrics?.agents_total ?? 0}`,
            direction: (metrics?.agents_online ?? 0) > 0 ? "up" : "flat",
          }}
        />
        <MetricCard
          label="Prompts (24h)"
          value={showPlaceholders ? "—" : (metrics?.prompts_24h ?? 0)}
          icon={FileClock}
          accent="violet"
          loading={showPlaceholders}
          hint={`${metrics?.blocks_24h ?? 0} blocked`}
        />
        <MetricCard
          label="Threats (24h)"
          value={showPlaceholders ? "—" : (metrics?.threats_24h ?? 0)}
          icon={ShieldAlert}
          accent={(metrics?.threats_24h ?? 0) > 0 ? "rose" : "emerald"}
          loading={showPlaceholders}
          hint={`${metrics?.pii_detections_24h ?? 0} PII detections`}
        />
      </div>

      <div className="mt-4 grid gap-4 sm:grid-cols-2">
        <MetricCard
          label="Blocks (24h)"
          value={showPlaceholders ? "—" : (metrics?.blocks_24h ?? 0)}
          icon={Ban}
          accent="rose"
          loading={showPlaceholders}
          hint="policy & threat blocks"
        />
        <MetricCard
          label="PII Detections (24h)"
          value={showPlaceholders ? "—" : (metrics?.pii_detections_24h ?? 0)}
          icon={ScanEye}
          accent="amber"
          loading={showPlaceholders}
          hint="sensitive data flagged"
        />
      </div>

      <div className="mt-6 grid gap-6 lg:grid-cols-3">
        <section className="card p-5 lg:col-span-2">
          <div className="mb-4 flex items-center justify-between">
            <div>
              <h2 className="text-sm font-semibold text-ink-900">
                Audit Activity
              </h2>
              <p className="text-xs text-ink-500">Events over the last 7 days</p>
            </div>
            <span className="flex items-center gap-1.5 text-xs font-medium text-ink-500">
              <Activity className="h-3.5 w-3.5 text-brand-500" />
              Rolling window
            </span>
          </div>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart
                data={series}
                margin={{ top: 8, right: 8, left: -16, bottom: 0 }}
              >
                <defs>
                  <linearGradient id="fillEvents" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#3466ff" stopOpacity={0.28} />
                    <stop offset="95%" stopColor="#3466ff" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#eceef2" vertical={false} />
                <XAxis
                  dataKey="day"
                  tickLine={false}
                  axisLine={false}
                  tick={{ fontSize: 12, fill: "#66748f" }}
                />
                <YAxis
                  allowDecimals={false}
                  tickLine={false}
                  axisLine={false}
                  tick={{ fontSize: 12, fill: "#66748f" }}
                  width={40}
                />
                <Tooltip
                  contentStyle={{
                    borderRadius: 10,
                    border: "1px solid #d5dae2",
                    fontSize: 12,
                    boxShadow: "0 4px 6px -1px rgb(16 19 32 / 0.08)",
                  }}
                  cursor={{ stroke: "#b0b9c9", strokeWidth: 1 }}
                />
                <Area
                  type="monotone"
                  dataKey="events"
                  stroke="#1d45f5"
                  strokeWidth={2}
                  fill="url(#fillEvents)"
                  name="Events"
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </section>

        <section className="card flex flex-col p-5">
          <div className="mb-4 flex items-center justify-between">
            <h2 className="text-sm font-semibold text-ink-900">
              Recent Threats
            </h2>
            <Link
              to="/threats"
              className="text-xs font-medium text-brand-600 hover:text-brand-700"
            >
              View all
            </Link>
          </div>
          {threats.length === 0 ? (
            <div className="flex flex-1 flex-col items-center justify-center py-8 text-center">
              <ShieldCheck className="h-8 w-8 text-ink-300" />
              <p className="mt-2 text-sm text-ink-500">
                No threats detected recently.
              </p>
            </div>
          ) : (
            <ul className="-my-1 divide-y divide-ink-100">
              {threats.map((t) => (
                <li key={t.id} className="flex items-center gap-3 py-3">
                  <StatusBadge status={t.severity} className="shrink-0" />
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm text-ink-700">
                      {t.masked_content || titleCase(t.event_type)}
                    </p>
                    <p className="text-xs text-ink-400">
                      {formatRelative(t.created_at)}
                    </p>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>
    </>
  );
}
