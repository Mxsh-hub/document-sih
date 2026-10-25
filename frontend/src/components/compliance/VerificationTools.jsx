import React, { useMemo, useState } from 'react';
import { Loader2, ScanLine, ShieldQuestion } from 'lucide-react';
import { api } from '../../lib/api';

const ADAPTER_LABELS = {
  'qr-payload': 'QR payload',
  'pdf-signature': 'PDF signature',
};

const UNAVAILABLE_STATES = new Set([
  'QR_DECODER_UNAVAILABLE',
  'QR_PAYLOAD_DETECTED_UNVERIFIED',
  'PDF_SIGNATURE_PRESENT_UNVERIFIED',
  'PDF_SIGNATURE_UNSUPPORTED_STRUCTURE',
]);
const PROBLEM_STATES = new Set([
  'PDF_SIGNATURE_COVERAGE_INCOMPLETE',
  'QR_DECODE_FAILED',
  'PDF_PARSE_FAILED',
]);

function StateBadge({ state }) {
  const tone = PROBLEM_STATES.has(state)
    ? 'bg-red-100 text-red-900 border-red-400'
    : UNAVAILABLE_STATES.has(state)
      ? 'bg-amber-100 text-amber-900 border-amber-400'
      : 'bg-slate-200 text-slate-800 border-slate-400';
  return (
    <span className={`border px-2 py-0.5 font-mono text-[10px] font-bold ${tone}`}>
      {state || 'UNKNOWN'}
    </span>
  );
}

function Facts({ evidence }) {
  if (!evidence) return null;
  const facts = [];
  if (evidence.state === 'QR_PAYLOAD_DETECTED_UNVERIFIED') {
    const payload = (evidence.payloads || [])[0];
    if (payload) {
      facts.push(['payload', payload.payload_preview]);
      facts.push(['host', payload.host || '—']);
      facts.push(['fetched', payload.not_fetched ? 'no (never fetched)' : 'unknown']);
      facts.push(['digest', `${payload.payload_sha256?.slice(0, 16)}…`]);
    }
    facts.push(['pages scanned', evidence.pages_scanned]);
  } else if (evidence.state !== 'QR_DECODER_UNAVAILABLE') {
    if (evidence.pages_scanned !== undefined) facts.push(['pages scanned', evidence.pages_scanned]);
  }
  if (evidence.covers_whole_document !== undefined) {
    facts.push(['ranges cover document', evidence.covers_whole_document ? 'yes (structure only)' : 'no']);
  }
  if (evidence.coverage_ratio !== undefined) {
    facts.push(['coverage', `${Math.round((evidence.coverage_ratio || 0) * 100)}%`]);
  }
  if (evidence.signature_fields?.signer_name) {
    facts.push(['signer field', evidence.signature_fields.signer_name]);
  }
  return (
    <dl className="mt-1 grid gap-x-3 gap-y-0.5 sm:grid-cols-2">
      {facts.map(([key, value]) => (
        <div key={key} className="flex gap-2 font-mono text-[10px]">
          <dt className="shrink-0 text-muted-foreground">{key}</dt>
          <dd className="break-all">{String(value)}</dd>
        </div>
      ))}
    </dl>
  );
}

/**
 * Staff-only panel for advisory QR and PDF signature-structure inspection.
 *
 * A detected payload is never fetched and an embedded signature is never
 * treated as verified. The panel exists to put technical observations next to
 * the human review record, not to produce an authenticity verdict.
 */
export default function VerificationTools({ applicationId, overview, token, onRefreshed }) {
  const [busyVersionId, setBusyVersionId] = useState('');
  const [error, setError] = useState('');

  const documents = useMemo(() => overview?.documents || [], [overview]);
  const results = useMemo(() => overview?.technical_verifications || [], [overview]);
  const documentByVersion = useMemo(() => {
    const map = new Map();
    documents.forEach((document) => {
      if (document.current_version_id) map.set(document.current_version_id, document);
    });
    return map;
  }, [documents]);

  const inspect = async (versionId) => {
    setError('');
    setBusyVersionId(versionId);
    try {
      await api(`/api/v1/document-versions/${versionId}/technical-verifications`, {
        token,
        method: 'POST',
      });
      await onRefreshed?.();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusyVersionId('');
    }
  };

  return (
    <section className="neo-box bg-card p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="flex items-center gap-2 text-xl font-bold">
            <ScanLine size={20} /> Technical inspection
          </h3>
          <p className="mt-1 max-w-3xl font-mono text-[11px] text-muted-foreground">
            Reads QR payloads and PDF signature structures. Payloads are recorded but never fetched; signature
            cryptography and trust chains are not verified. These are advisory observations, not authenticity verdicts.
          </p>
        </div>
      </div>

      {error && <p className="mt-3 border-2 border-red-400 bg-red-50 p-2 font-mono text-xs text-red-800">{error}</p>}

      <div className="mt-4 space-y-2">
        {documents.length === 0 && (
          <p className="border-2 border-dashed border-border p-3 font-mono text-xs">No documents are attached yet.</p>
        )}
        {documents.map((document) => (
          <div key={document.id} className="flex flex-wrap items-center justify-between gap-2 border-2 border-border p-2">
            <div>
              <div className="text-sm font-bold">{document.original_filename || document.document_type}</div>
              <div className="font-mono text-[10px] text-muted-foreground">
                {document.document_type} · {document.status}
                {document.mime_type ? ` · ${document.mime_type}` : ''}
              </div>
            </div>
            <button
              type="button"
              disabled={!document.current_version_id || busyVersionId === document.current_version_id}
              onClick={() => inspect(document.current_version_id)}
              className="neo-button border-2 border-border px-3 py-1.5 font-bold disabled:opacity-50"
            >
              {busyVersionId === document.current_version_id ? (
                <span className="flex items-center gap-2"><Loader2 size={14} className="animate-spin" /> Inspecting…</span>
              ) : (
                'Inspect QR & signature'
              )}
            </button>
          </div>
        ))}
      </div>

      <div className="mt-4 space-y-2">
        {results.length === 0 ? (
          <p className="flex items-center gap-2 font-mono text-xs text-muted-foreground">
            <ShieldQuestion size={14} /> No technical inspection has been run for the current document versions.
          </p>
        ) : (
          results.map((item) => {
            const document = documentByVersion.get(item.document_version_id);
            return (
              <div key={item.id} className="border-2 border-border p-2">
                <div className="flex flex-wrap items-center gap-2">
                  <StateBadge state={item.evidence?.state} />
                  <span className="font-mono text-[10px] font-bold uppercase">
                    {ADAPTER_LABELS[item.adapter_code] || item.adapter_code}
                  </span>
                  <span className="font-mono text-[10px] text-muted-foreground">
                    {document?.original_filename || item.document_version_id.slice(0, 8)}
                  </span>
                </div>
                <p className="mt-1 text-xs">{item.message}</p>
                <Facts evidence={item.evidence} />
                <p className="mt-1 font-mono text-[10px] text-muted-foreground">
                  cryptographic verification: not performed · advisory only
                </p>
              </div>
            );
          })
        )}
      </div>

      {applicationId && (
        <p className="mt-3 font-mono text-[10px] text-muted-foreground">
          Application {applicationId.slice(0, 8)} · inspection attempts and their outcomes are written to the audit trail.
        </p>
      )}
    </section>
  );
}
