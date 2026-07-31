"use client";

import { useEffect, useState, useCallback } from "react";

// ── Types ─────────────────────────────────────────────────────────────────────

interface Status {
  active_events: number;
  last_sync: {
    synced_at: string | null;
    status: string | null;
    added: number;
    updated: number;
    removed: number;
  };
}

interface Event {
  id: number;
  unstop_id: string;
  title: string;
  date: string | null;
  time: string | null;
  deadline: string | null;
  event_url: string | null;
  calendar_event_id: string | null;
  is_active: boolean;
  updated_at: string | null;
}

interface SyncLog {
  id: number;
  synced_at: string;
  status: "success" | "error";
  added: number;
  updated: number;
  removed: number;
  error_message: string | null;
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function formatTime(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function formatDate(dateStr: string | null, timeStr?: string | null): string {
  if (!dateStr) return "Date TBD";
  try {
    const d = new Date(`${dateStr} ${timeStr ?? ""}`.trim());
    if (isNaN(d.getTime())) return dateStr;
    return d.toLocaleDateString(undefined, {
      weekday: "short",
      month: "short",
      day: "numeric",
      year: "numeric",
    });
  } catch {
    return dateStr;
  }
}

const API = "/api";

// ── Component ─────────────────────────────────────────────────────────────────

export default function Dashboard() {
  const [status, setStatus] = useState<Status | null>(null);
  const [events, setEvents] = useState<Event[]>([]);
  const [logs, setLogs] = useState<SyncLog[]>([]);
  const [syncing, setSyncing] = useState(false);
  const [toast, setToast] = useState<string | null>(null);

  const showToast = (msg: string) => {
    setToast(msg);
    setTimeout(() => setToast(null), 4000);
  };

  const fetchAll = useCallback(async () => {
    try {
      const [s, e, l] = await Promise.all([
        fetch(`${API}/status`).then((r) => r.json()),
        fetch(`${API}/events`).then((r) => r.json()),
        fetch(`${API}/logs?limit=5`).then((r) => r.json()),
      ]);
      setStatus(s);
      setEvents(e);
      setLogs(l);
    } catch {
      showToast("Failed to load data. Is the backend running?");
    }
  }, []);

  useEffect(() => {
    fetchAll();
    // Auto-refresh every 2 minutes
    const id = setInterval(fetchAll, 120_000);
    return () => clearInterval(id);
  }, [fetchAll]);

  const handleSync = async () => {
    setSyncing(true);
    try {
      const res = await fetch(`${API}/sync`, { method: "POST" });
      const data = await res.json();
      if (data.status === "success") {
        showToast(
          `Sync done — ${data.added} added, ${data.updated} updated, ${data.removed} removed.`
        );
      } else {
        showToast(`Sync failed: ${data.error ?? "Unknown error"}`);
      }
      fetchAll();
    } catch {
      showToast("Network error during sync.");
    } finally {
      setSyncing(false);
    }
  };

  const syncStatus = status?.last_sync.status;
  const syncColor =
    syncStatus === "success"
      ? "#34d399"
      : syncStatus === "error"
      ? "#f87171"
      : "#6b7280";

  return (
    <main className="container">
      {/* ── Header ─────────────────────────────────────────────── */}
      <header>
        <div className="logo">
          <div className="logo-dot" />
          Unstop Calendar Sync
        </div>

        <button className="btn-sync" onClick={handleSync} disabled={syncing}>
          {syncing ? <span className="spinner" /> : "↻"}
          {syncing ? "Syncing…" : "Sync now"}
        </button>
      </header>

      {/* ── Stats ─────────────────────────────────────────────── */}
      <div className="stats-grid">
        <div className="stat-card">
          <div className="stat-label">Synced events</div>
          <div className="stat-value">{status?.active_events ?? "—"}</div>
        </div>

        <div className="stat-card">
          <div className="stat-label">Last sync</div>
          <div className="stat-value" style={{ fontSize: "1rem", paddingTop: "0.35rem" }}>
            {formatTime(status?.last_sync.synced_at ?? null)}
          </div>
        </div>

        <div className="stat-card">
          <div className="stat-label">Last status</div>
          <div
            className="stat-value"
            style={{ fontSize: "1.1rem", color: syncColor, paddingTop: "0.3rem" }}
          >
            {syncStatus ?? "—"}
          </div>
        </div>
      </div>

      {/* ── Events ────────────────────────────────────────────── */}
      <div className="section-title">Upcoming events</div>

      {events.length === 0 ? (
        <div className="empty">
          No events yet. Hit <strong>Sync now</strong> to import your Unstop registrations.
        </div>
      ) : (
        <div className="events-list">
          {events.map((ev) => (
            <div className="event-card" key={ev.id}>
              <div>
                <div className="event-title">
                  {ev.event_url ? (
                    <a href={ev.event_url} target="_blank" rel="noopener noreferrer">
                      {ev.title}
                    </a>
                  ) : (
                    ev.title
                  )}
                </div>
                <div className="event-meta">
                  {formatDate(ev.date, ev.time)}
                  {ev.deadline && ` · Deadline: ${ev.deadline}`}
                </div>
              </div>

              <div className="event-badge">
                {ev.calendar_event_id ? "📅 Synced" : "⏳ Pending"}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* ── Recent sync log ───────────────────────────────────── */}
      {logs.length > 0 && (
        <>
          <div className="section-title" style={{ marginTop: "2rem" }}>
            Recent syncs
          </div>
          <div className="log-list">
            {logs.map((log) => (
              <div className="log-row" key={log.id}>
                <div className={`log-dot ${log.status}`} />
                <span>{formatTime(log.synced_at)}</span>
                <span>
                  +{log.added} updated {log.updated} removed {log.removed}
                </span>
                {log.error_message && (
                  <span style={{ color: "#f87171" }}>— {log.error_message}</span>
                )}
              </div>
            ))}
          </div>
        </>
      )}

      {/* ── Toast ─────────────────────────────────────────────── */}
      {toast && <div className="toast">{toast}</div>}
    </main>
  );
}
