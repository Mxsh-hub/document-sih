import React, { useMemo, useState } from 'react';
import { BellRing, CheckCheck, Loader2 } from 'lucide-react';
import { api } from '../../lib/api';

/**
 * Dispositions a human reviewer may record.
 *
 * `SUPERSEDED` is deliberately absent: it is written by the system when a
 * finding or anomaly disappears from the latest validation output, so a person
 * should not be able to claim it.
 */
const MANUAL_DISPOSITIONS = [
  'ADDRESSED',
  'DUPLICATE',
  'ESCALATED',
  'FALSE_POSITIVE',
  'ACCEPTED_RISK',
];

const NOTE_REQUIRED = new Set(['FALSE_POSITIVE', 'ACCEPTED_RISK']);

const STATUS_TONE = {
  OPEN: 'bg-amber-100 text-amber-900 border-amber-400',
  ACKNOWLEDGED: 'bg-sky-100 text-sky-900 border-sky-400',
  RESOLVED: 'bg-slate-200 text-slate-800 border-slate-400',
};

const DISPOSITION_TONE = {
  FALSE_POSITIVE: 'bg-red-100 text-red-900 border-red-400',
  ACCEPTED_RISK: 'bg-red-100 text-red-900 border-red-400',
  DUPLICATE: 'bg-slate-200 text-slate-800 border-slate-400',
  SUPERSEDED: 'bg-slate-200 text-slate-800 border-slate-400',
  ESCALATED: 'bg-sky-100 text-sky-900 border-sky-400',
};

function Pill({ value, tone }) {
  return (
    <span className={`border px-2 py-0.5 font-mono text-[10px] font-bold ${tone || 'bg-muted border-border'}`}>
      {value}
    </span>
  );
}

/**
 * Staff-only alert queue with explicit human dispositions.
 *
 * Alerts are advisory prompts derived from findings, anomalies, rectification
 * requests, and escalations. Resolving one records who decided, what they
 * decided, and why. Dismissing an alert never changes a finding outcome and
 * never rejects an application.
 */
export default function AlertPanel({ applicationId, alerts, token, onRefreshed }) {
  const [openAlertId, setOpenAlertId] = useState('');
  const [disposition, setDisposition] = useState('ADDRESSED');
  const [note, setNote] = useState('');
  const [busyId, setBusyId] = useState('');
  const [error, setError] = useState('');

  const rows = useMemo(() => {
    const rank = { OPEN: 0, ACKNOWLEDGED: 1, RESOLVED: 2 };
    return [...(alerts || [])].sort(
      (a, b) => (rank[a.status] ?? 3) - (rank[b.status] ?? 3) || String(b.created_at).localeCompare(String(a.created_at)),
    );
  }, [alerts]);

  const openCount = rows.filter((row) => row.status !== 'RESOLVED').length;

  const call = async (alertId, path, options) => {
    setError('');
    setBusyId(alertId);
    try {
      await api(path, { token, ...options });
      setOpenAlertId('');
      setNote('');
      setDisposition('ADDRESSED');
      await onRefreshed?.();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusyId('');
    }
  };

  const acknowledge = (alertId) =>
    call(alertId, `/api/v1/alerts/${alertId}/acknowledge`, { method: 'POST' });

  const resolve = (alertId) =>
    call(alertId, `/api/v1/alerts/${alertId}/resolve`, {
      method: 'POST',
      body: { disposition, note: note.trim() || null },
    });

  return (
    <section className="neo-box bg-card p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="flex items-center gap-2 text-xl font-bold">
            <BellRing size={20} /> Alerts and dispositions
          </h3>
          <p className="mt-1 max-w-3xl font-mono text-[11px] text-muted-foreground">
            {openCount} open · alerts are advisory prompts. A disposition records human judgement only; it never
            changes a finding outcome, never auto-rejects, and never verifies a document.
          </p>
        </div>
      </div>

      {error && <p className="mt-3 border-2 border-red-400 bg-red-50 p-2 font-mono text-xs text-red-800">{error}</p>}

      <div className="mt-4 space-y-2">
        {rows.length === 0 && (
          <p className="border-2 border-dashed border-border p-3 font-mono text-xs">No alerts for this application.</p>
        )}
        {rows.map((alert) => {
          const resolved = alert.status === 'RESOLVED';
          const expanded = openAlertId === alert.id;
          return (
            <div key={alert.id} className="border-2 border-border p-2">
              <div className="flex flex-wrap items-center gap-2">
                <Pill value={alert.status} tone={STATUS_TONE[alert.status]} />
                <span className="font-mono text-[10px] font-bold uppercase">{alert.alert_type.replaceAll('_', ' ')}</span>
                <span className="text-sm font-bold">{alert.title}</span>
                {alert.disposition && <Pill value={alert.disposition} tone={DISPOSITION_TONE[alert.disposition]} />}
              </div>
              <p className="mt-1 text-xs">{alert.message}</p>
              {alert.payload?.resolution_note && (
                <p className="mt-1 font-mono text-[10px] text-muted-foreground">note: {alert.payload.resolution_note}</p>
              )}
              {resolved && (
                <p className="mt-1 font-mono text-[10px] text-muted-foreground">
                  resolved {String(alert.resolved_at || '').slice(0, 19).replace('T', ' ')} · by{' '}
                  {alert.resolved_by ? alert.resolved_by.slice(0, 8) : 'system'}
                </p>
              )}

              {!resolved && (
                <div className="mt-2 flex flex-wrap gap-2">
                  {alert.status === 'OPEN' && (
                    <button
                      type="button"
                      disabled={busyId === alert.id}
                      onClick={() => acknowledge(alert.id)}
                      className="neo-button border-2 border-border px-3 py-1 font-bold disabled:opacity-50"
                    >
                      {busyId === alert.id ? (
                        <span className="flex items-center gap-2"><Loader2 size={14} className="animate-spin" /> Working…</span>
                      ) : (
                        'Acknowledge'
                      )}
                    </button>
                  )}
                  <button
                    type="button"
                    disabled={busyId === alert.id}
                    onClick={() => {
                      setOpenAlertId(expanded ? '' : alert.id);
                      setDisposition('ADDRESSED');
                      setNote('');
                    }}
                    className="neo-button bg-primary px-3 py-1 font-bold text-primary-foreground disabled:opacity-50"
                  >
                    {expanded ? 'Cancel' : 'Resolve with disposition…'}
                  </button>
                </div>
              )}

              {expanded && !resolved && (
                <div className="mt-2 space-y-2 border-t-2 border-border pt-2">
                  <label className="block font-mono text-[10px] font-bold uppercase">
                    Disposition
                    <select
                      value={disposition}
                      onChange={(event) => setDisposition(event.target.value)}
                      className="mt-1 block w-full border-2 border-border bg-background p-2 font-mono text-xs"
                    >
                      {MANUAL_DISPOSITIONS.map((value) => (
                        <option key={value} value={value}>{value.replaceAll('_', ' ')}</option>
                      ))}
                    </select>
                  </label>
                  <label className="block font-mono text-[10px] font-bold uppercase">
                    Note {NOTE_REQUIRED.has(disposition) ? '(required)' : '(optional)'}
                    <textarea
                      value={note}
                      onChange={(event) => setNote(event.target.value)}
                      rows={2}
                      className="mt-1 w-full border-2 border-border p-2 font-mono text-xs"
                      placeholder={
                        NOTE_REQUIRED.has(disposition)
                          ? 'Explain why this alert is being dismissed. This note is audited.'
                          : 'What was done about this alert?'
                      }
                    />
                  </label>
                  <button
                    type="button"
                    disabled={busyId === alert.id || (NOTE_REQUIRED.has(disposition) && !note.trim())}
                    onClick={() => resolve(alert.id)}
                    className="neo-button bg-primary px-3 py-1 font-bold text-primary-foreground disabled:opacity-50"
                  >
                    {busyId === alert.id ? (
                      <span className="flex items-center gap-2"><Loader2 size={14} className="animate-spin" /> Saving…</span>
                    ) : (
                      <span className="flex items-center gap-2"><CheckCheck size={14} /> Record disposition</span>
                    )}
                  </button>
                </div>
              )}
            </div>
          );
        })}
      </div>

      {applicationId && (
        <p className="mt-3 font-mono text-[10px] text-muted-foreground">
          Acknowledgements and dispositions are audited. Alerts whose source finding or anomaly disappears from the
          latest validation run are closed automatically as SUPERSEDED without a human disposition.
        </p>
      )}
    </section>
  );
}
