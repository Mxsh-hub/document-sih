import React, { useCallback, useEffect, useState } from 'react';
import { AlertTriangle, CheckCircle2, Info, ListChecks, Loader2, ShieldAlert } from 'lucide-react';
import { api } from '../../lib/api';

const LEVEL_ORDER = ['BLOCKING', 'WARNING', 'INFO', 'OK'];

const LEVEL_META = {
  BLOCKING: {
    icon: ShieldAlert,
    tone: 'border-red-400 bg-red-50 text-red-900',
    label: 'Blocking',
  },
  WARNING: {
    icon: AlertTriangle,
    tone: 'border-amber-400 bg-amber-50 text-amber-900',
    label: 'Warning',
  },
  INFO: {
    icon: Info,
    tone: 'border-sky-300 bg-sky-50 text-sky-900',
    label: 'Info',
  },
  OK: {
    icon: CheckCircle2,
    tone: 'border-emerald-300 bg-emerald-50 text-emerald-900',
    label: 'Ready',
  },
};

/**
 * Applicant-facing pre-submission self-check (M5).
 *
 * Read-only preview of whether submission would be accepted. Blocking checks
 * are the same rule the submit endpoint enforces; everything else is advisory
 * guidance. A clean result means "submission is possible", never "approval is
 * likely" and never "the declaration is true".
 */
export default function SelfCheckPanel({ applicationId, token, refreshKey = 0 }) {
  const [data, setData] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    if (!applicationId) return;
    setBusy(true);
    setError('');
    try {
      setData(await api(`/api/v1/applications/${applicationId}/self-check`, { token }));
    } catch (err) {
      setData(null);
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }, [applicationId, token]);

  useEffect(() => {
    load();
  }, [load, refreshKey]);

  const checks = data?.checks || [];
  const grouped = LEVEL_ORDER.map((level) => ({
    level,
    items: checks.filter((check) => check.level === level),
  })).filter((group) => group.items.length > 0);

  return (
    <section className="neo-box bg-card p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="flex items-center gap-2 text-xl font-bold">
            <ListChecks size={20} /> Pre-submission self-check
          </h3>
          <p className="mt-1 max-w-3xl font-mono text-[11px] text-muted-foreground">
            Read-only preview. It does not run the validation rules and does not reserve or submit anything.
          </p>
        </div>
        <button
          type="button"
          onClick={load}
          disabled={busy}
          className="neo-button border-2 border-border px-3 py-1.5 font-bold disabled:opacity-50"
        >
          {busy ? (
            <span className="flex items-center gap-2"><Loader2 size={14} className="animate-spin" /> Checking…</span>
          ) : (
            'Re-run check'
          )}
        </button>
      </div>

      {error && <p className="mt-3 border-2 border-red-400 bg-red-50 p-2 font-mono text-xs text-red-800">{error}</p>}

      {data && (
        <>
          <div
            className={`mt-3 border-2 p-3 font-mono text-xs font-bold ${
              data.can_submit
                ? 'border-emerald-400 bg-emerald-50 text-emerald-900'
                : 'border-red-400 bg-red-50 text-red-900'
            }`}
          >
            {data.can_submit
              ? 'Submission would be accepted now.'
              : `${data.counts?.BLOCKING || 0} blocking item(s) must be fixed before submission.`}
            <span className="ml-2 font-normal">
              · {data.counts?.WARNING || 0} warning · {data.counts?.INFO || 0} info · check {data.check_version}
            </span>
          </div>

          <div className="mt-3 space-y-3">
            {grouped.map(({ level, items }) => {
              const meta = LEVEL_META[level];
              const Icon = meta.icon;
              return (
                <div key={level}>
                  <div className="flex items-center gap-2 font-mono text-[10px] font-bold uppercase">
                    <Icon size={13} /> {meta.label} ({items.length})
                  </div>
                  <div className="mt-1 space-y-1">
                    {items.map((check) => (
                      <div key={check.code} className={`border-2 p-2 ${meta.tone}`}>
                        <div className="text-sm font-bold">{check.title}</div>
                        <p className="mt-0.5 text-xs">{check.message}</p>
                        {check.remediation && (
                          <p className="mt-1 font-mono text-[10px]">Next step: {check.remediation}</p>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              );
            })}
          </div>

          <p className="mt-3 border-t-2 border-border pt-2 font-mono text-[10px] text-muted-foreground">
            {data.advisory_note}
          </p>
        </>
      )}
    </section>
  );
}
