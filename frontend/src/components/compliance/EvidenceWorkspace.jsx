import React, { useEffect, useMemo, useState } from 'react';
import { ChevronRight, Crosshair, FileSearch, Info } from 'lucide-react';
import DocumentViewer from './DocumentViewer';

const OUTCOME_ORDER = ['FAIL', 'INCONCLUSIVE', 'NOT_AVAILABLE', 'PASS', 'NOT_APPLICABLE'];

function OutcomeBadge({ value }) {
  const tone =
    value === 'PASS'
      ? 'bg-emerald-100 text-emerald-900 border-emerald-400'
      : value === 'FAIL'
        ? 'bg-red-100 text-red-900 border-red-400'
        : value === 'NOT_AVAILABLE'
          ? 'bg-slate-200 text-slate-800 border-slate-400'
          : 'bg-amber-100 text-amber-900 border-amber-400';
  return <span className={`border px-2 py-0.5 font-mono text-[10px] font-bold ${tone}`}>{value}</span>;
}

function SeverityTag({ value }) {
  const tone =
    value === 'BLOCKING' ? 'text-red-800' : value === 'WARNING' ? 'text-amber-800' : 'text-slate-600';
  return <span className={`font-mono text-[10px] font-bold uppercase ${tone}`}>{value}</span>;
}

function Confidence({ value }) {
  if (value === null || value === undefined) return <span className="font-mono text-[10px] text-muted-foreground">no confidence</span>;
  const pct = Math.round(Math.max(0, Math.min(1, value)) * 100);
  const tone = pct >= 75 ? 'bg-emerald-600' : pct >= 50 ? 'bg-amber-500' : 'bg-red-600';
  return (
    <span className="flex items-center gap-2">
      <span className="h-2 w-16 border border-border bg-muted">
        <span className={`block h-full ${tone}`} style={{ width: `${pct}%` }} />
      </span>
      <span className="font-mono text-[10px]">{pct}%</span>
    </span>
  );
}

function detailEntries(details) {
  if (!details || typeof details !== 'object') return [];
  return Object.entries(details)
    .filter(([, value]) => value !== null && value !== undefined)
    .map(([key, value]) => {
      let rendered;
      if (Array.isArray(value)) {
        rendered = value.length
          ? value
              .map((entry) => (entry && typeof entry === 'object' ? JSON.stringify(entry) : String(entry)))
              .join(', ')
          : '—';
      } else if (typeof value === 'object') rendered = JSON.stringify(value);
      else rendered = String(value);
      return [key.replaceAll('_', ' '), rendered];
    });
}

export default function EvidenceWorkspace({ overview, token, onClose }) {
  const findings = useMemo(
    () => overview?.latest_validation_run?.findings || [],
    [overview],
  );
  const documents = useMemo(() => overview?.documents || [], [overview]);

  const { evidenceByFinding, allEvidence } = useMemo(() => {
    const byId = new Map(documents.map((document) => [document.id, document]));
    const byVersion = new Map(
      documents.filter((document) => document.current_version_id).map((document) => [document.current_version_id, document]),
    );
    const byFinding = new Map();
    const flat = [];
    findings.forEach((finding) => {
      const items = (finding.evidence || []).map((evidence) => {
        const meta = evidence.metadata_json || {};
        const documentId = meta.document_id || (evidence.evidence_type === 'DOCUMENT' ? evidence.entity_id : null);
        const versionId = meta.document_version_id || null;
        const document = byId.get(documentId) || byVersion.get(versionId) || null;
        const item = {
          id: evidence.id,
          findingId: finding.id,
          label: evidence.label,
          evidenceType: evidence.evidence_type,
          documentId: document?.id || documentId,
          versionId: versionId || document?.current_version_id || null,
          documentType: document?.document_type || meta.document_type || null,
          document,
          page: meta.page ?? null,
          bbox: Array.isArray(meta.bbox) ? meta.bbox : null,
          pageWidth: meta.page_width ?? null,
          pageHeight: meta.page_height ?? null,
          field: meta.field || null,
          value: meta.raw_value ?? meta.normalized_value ?? null,
          confidence: typeof meta.confidence === 'number' ? meta.confidence : null,
        };
        flat.push(item);
        return item;
      });
      byFinding.set(finding.id, items);
    });
    return { evidenceByFinding: byFinding, allEvidence: flat };
  }, [findings, documents]);

  const sortedFindings = useMemo(
    () =>
      [...findings].sort((a, b) => {
        const outcome = OUTCOME_ORDER.indexOf(a.outcome) - OUTCOME_ORDER.indexOf(b.outcome);
        if (outcome !== 0) return outcome;
        const rank = { BLOCKING: 0, WARNING: 1, ADVISORY: 2 };
        return (rank[a.severity] ?? 3) - (rank[b.severity] ?? 3);
      }),
    [findings],
  );

  const [filter, setFilter] = useState('ALL');
  const [activeFindingId, setActiveFindingId] = useState('');
  const [activeEvidenceId, setActiveEvidenceId] = useState('');

  useEffect(() => {
    if (!sortedFindings.length) return;
    const firstWithEvidence = sortedFindings.find((finding) => (evidenceByFinding.get(finding.id) || []).length) || sortedFindings[0];
    setActiveFindingId(firstWithEvidence.id);
    const firstEvidence = (evidenceByFinding.get(firstWithEvidence.id) || [])[0];
    setActiveEvidenceId(firstEvidence?.id || '');
  }, [sortedFindings, evidenceByFinding]);

  const visibleFindings = useMemo(
    () => (filter === 'ALL' ? sortedFindings : sortedFindings.filter((finding) => finding.outcome === filter)),
    [sortedFindings, filter],
  );

  const activeFinding = findings.find((finding) => finding.id === activeFindingId) || null;
  const activeFindingEvidence = activeFinding ? evidenceByFinding.get(activeFinding.id) || [] : [];
  const activeEvidence = allEvidence.find((item) => item.id === activeEvidenceId) || null;

  const activeDocument = useMemo(() => {
    if (!activeEvidence?.document) return null;
    return {
      ...activeEvidence.document,
      current_version_id: activeEvidence.versionId || activeEvidence.document.current_version_id,
    };
  }, [activeEvidence]);

  const viewerEvidence = useMemo(() => {
    if (!activeEvidence?.documentId) return [];
    const sameDocument = allEvidence.filter((item) => item.documentId === activeEvidence.documentId && item.page && item.bbox);
    const seen = new Set();
    return sameDocument
      .filter((item) => (seen.has(item.id) ? false : (seen.add(item.id), true)))
      .sort((a, b) => (a.page || 0) - (b.page || 0));
  }, [allEvidence, activeEvidence]);

  const selectFinding = (finding) => {
    setActiveFindingId(finding.id);
    const items = evidenceByFinding.get(finding.id) || [];
    const preferred = items.find((item) => item.versionId && item.page) || items[0];
    setActiveEvidenceId(preferred?.id || '');
  };

  const selectEvidence = (evidenceId) => {
    setActiveEvidenceId(evidenceId);
    const item = allEvidence.find((entry) => entry.id === evidenceId);
    if (item?.findingId && item.findingId !== activeFindingId) setActiveFindingId(item.findingId);
  };

  const counts = useMemo(() => {
    const accumulator = { ALL: findings.length };
    findings.forEach((finding) => { accumulator[finding.outcome] = (accumulator[finding.outcome] || 0) + 1; });
    return accumulator;
  }, [findings]);

  if (!overview) return null;

  if (!overview.latest_validation_run) {
    return (
      <div className="neo-box bg-card p-5">
        <h3 className="text-xl font-bold">Evidence workspace</h3>
        <p className="mt-2 font-mono text-xs">
          No validation run exists for this application yet. Submit the application to generate evidence-linked findings.
        </p>
      </div>
    );
  }

  return (
    <div className="neo-box space-y-4 bg-card p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="flex items-center gap-2 text-xl font-bold">
            <FileSearch size={20} /> Evidence workspace
          </h3>
          <p className="mt-1 font-mono text-[11px] text-muted-foreground">
            Click a finding to open its source page. Boxes are preliminary extraction evidence, not proof of authenticity.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <span className="border-2 border-border px-2 py-1 font-mono text-[10px]">
            run {overview.latest_validation_run.id.slice(0, 8)} · engine {overview.latest_validation_run.engine_version}
          </span>
          {onClose && (
            <button type="button" onClick={onClose} className="border-2 border-border px-2 py-1 font-mono text-[10px] font-bold hover:bg-muted">
              Close
            </button>
          )}
        </div>
      </div>

      <div className="flex flex-wrap gap-2">
        {['ALL', ...OUTCOME_ORDER].filter((outcome) => counts[outcome]).map((outcome) => (
          <button
            type="button"
            key={outcome}
            onClick={() => setFilter(outcome)}
            className={`border-2 border-border px-2 py-1 font-mono text-[10px] font-bold ${
              filter === outcome ? 'bg-primary text-primary-foreground' : 'bg-card hover:bg-muted'
            }`}
          >
            {outcome} ({counts[outcome]})
          </button>
        ))}
      </div>

      <div className="grid gap-4 xl:grid-cols-[minmax(0,420px)_minmax(0,1fr)]">
        <div className="max-h-[70vh] space-y-2 overflow-auto pr-1">
          {visibleFindings.length === 0 && (
            <p className="border-2 border-dashed border-border p-4 font-mono text-xs">No findings match this filter.</p>
          )}
          {visibleFindings.map((finding) => {
            const items = evidenceByFinding.get(finding.id) || [];
            const active = finding.id === activeFindingId;
            return (
              <button
                type="button"
                key={finding.id}
                onClick={() => selectFinding(finding)}
                className={`w-full border-2 border-border p-3 text-left transition-colors ${
                  active ? 'bg-accent/20 ring-2 ring-primary' : 'bg-card hover:bg-muted'
                }`}
              >
                <div className="flex items-center justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <OutcomeBadge value={finding.outcome} />
                    <SeverityTag value={finding.severity} />
                  </div>
                  <ChevronRight size={14} className={active ? 'opacity-100' : 'opacity-30'} />
                </div>
                <div className="mt-1 text-sm font-bold leading-tight">{finding.title}</div>
                <p className="mt-1 text-xs text-muted-foreground">{finding.message}</p>
                <div className="mt-2 flex flex-wrap items-center gap-2 font-mono text-[10px] text-muted-foreground">
                  <span>{finding.code}</span>
                  {items.length > 0 && (
                    <span className="flex items-center gap-1">
                      <Crosshair size={10} /> {items.filter((item) => item.bbox).length}/{items.length} located
                    </span>
                  )}
                </div>
              </button>
            );
          })}
        </div>

        <div className="space-y-3">
          {activeFinding ? (
            <div className="border-2 border-border bg-card p-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="flex items-center gap-2">
                  <OutcomeBadge value={activeFinding.outcome} />
                  <span className="font-bold">{activeFinding.title}</span>
                </div>
                <span className="font-mono text-[10px] text-muted-foreground">{activeFinding.code}</span>
              </div>
              <p className="mt-1 text-sm">{activeFinding.message}</p>
              <div className="mt-3 grid gap-3 md:grid-cols-3">
                <div className="border-2 border-border p-2">
                  <div className="font-mono text-[10px] font-bold uppercase text-muted-foreground">Extracted evidence</div>
                  {activeEvidence ? (
                    <div className="mt-1 space-y-1">
                      <div className="break-words font-mono text-xs">{activeEvidence.value || activeEvidence.label}</div>
                      <div className="font-mono text-[10px] text-muted-foreground">
                        {activeEvidence.documentType || 'document'}
                        {activeEvidence.field ? ` · ${activeEvidence.field}` : ''}
                        {activeEvidence.page ? ` · p.${activeEvidence.page}` : ''}
                      </div>
                      <Confidence value={activeEvidence.confidence} />
                    </div>
                  ) : (
                    <p className="mt-1 font-mono text-[10px] text-muted-foreground">No field-level evidence attached.</p>
                  )}
                </div>
                <div className="border-2 border-border p-2">
                  <div className="font-mono text-[10px] font-bold uppercase text-muted-foreground">Rule detail</div>
                  <dl className="mt-1 space-y-0.5">
                    {detailEntries(activeFinding.details).slice(0, 6).map(([key, value]) => (
                      <div key={key} className="flex gap-2 font-mono text-[10px]">
                        <dt className="shrink-0 text-muted-foreground">{key}</dt>
                        <dd className="break-all">{value}</dd>
                      </div>
                    ))}
                    {detailEntries(activeFinding.details).length === 0 && (
                      <p className="font-mono text-[10px] text-muted-foreground">No structured detail.</p>
                    )}
                  </dl>
                </div>
                <div className="border-2 border-border p-2">
                  <div className="font-mono text-[10px] font-bold uppercase text-muted-foreground">Evidence items</div>
                  <ul className="mt-1 space-y-1">
                    {activeFindingEvidence.map((item) => (
                      <li key={item.id}>
                        <button
                          type="button"
                          onClick={() => selectEvidence(item.id)}
                          className={`w-full border px-1.5 py-1 text-left font-mono text-[10px] ${
                            item.id === activeEvidenceId ? 'border-primary bg-primary/10' : 'border-border hover:bg-muted'
                          }`}
                        >
                          <span className="line-clamp-2">{item.label}</span>
                          <span className="text-muted-foreground">
                            {item.bbox ? `p.${item.page || '?'} · box` : 'no box'}
                          </span>
                        </button>
                      </li>
                    ))}
                    {activeFindingEvidence.length === 0 && (
                      <li className="font-mono text-[10px] text-muted-foreground">No linked evidence.</li>
                    )}
                  </ul>
                </div>
              </div>
            </div>
          ) : (
            <p className="border-2 border-dashed border-border p-4 font-mono text-xs">Select a finding.</p>
          )}

          <DocumentViewer
            token={token}
            document={activeDocument}
            documents={documents}
            evidence={viewerEvidence}
            activeEvidenceId={activeEvidenceId}
            onSelectEvidence={selectEvidence}
          />

          <p className="flex items-start gap-2 border-2 border-border bg-muted/40 p-2 font-mono text-[10px] text-muted-foreground">
            <Info size={12} className="mt-0.5 shrink-0" />
            <span>
              Evidence boxes are produced by OCR/extraction and may be imprecise. A highlighted box or a hash match does not establish
              that a document is genuine. Final verification and decisions remain with authorised officials.
            </span>
          </p>
        </div>
      </div>
    </div>
  );
}
