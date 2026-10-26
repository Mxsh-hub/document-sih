import React, { useEffect, useMemo, useRef, useState } from 'react';
import { AlertTriangle, FileText, ImageIcon, Loader2, RefreshCw } from 'lucide-react';
import { API_BASE, api } from '../../lib/api';

let pdfjsPromise = null;
function loadPdfjs() {
  if (!pdfjsPromise) {
    pdfjsPromise = Promise.all([
      import('pdfjs-dist'),
      import('pdfjs-dist/build/pdf.worker.min.mjs?url'),
    ]).then(([lib, worker]) => {
      lib.GlobalWorkerOptions.workerSrc = worker.default;
      return lib;
    });
  }
  return pdfjsPromise;
}

function evidenceFraction(item) {
  if (!item?.bbox || item.bbox.length !== 4) return null;
  const [x0, y0, x1, y1] = item.bbox;
  if (!item.pageWidth || !item.pageHeight) return null;
  const w = item.pageWidth;
  const h = item.pageHeight;
  const left = Math.min(x0, x1) / w;
  const top = Math.min(y0, y1) / h;
  const right = Math.max(x0, x1) / w;
  const bottom = Math.max(y0, y1) / h;
  if (![left, top, right, bottom].every(Number.isFinite)) return null;
  if (right <= left || bottom <= top) return null;
  return {
    left: Math.max(0, Math.min(1, left)),
    top: Math.max(0, Math.min(1, top)),
    width: Math.min(1, right) - Math.max(0, left),
    height: Math.min(1, bottom) - Math.max(0, top),
  };
}

function Highlight({ item, active, onClick }) {
  const fraction = evidenceFraction(item);
  if (!fraction) return null;
  return (
    <button
      type="button"
      onClick={onClick}
      title={`${item.label}${item.field ? ` · ${item.field}` : ''}`}
      className={`absolute cursor-pointer border-2 transition-colors ${
        active
          ? 'border-red-600 bg-red-500/25 ring-2 ring-red-500/40 z-20'
          : 'border-amber-500 bg-amber-300/20 hover:bg-amber-300/35 z-10'
      }`}
      style={{
        left: `${fraction.left * 100}%`,
        top: `${fraction.top * 100}%`,
        width: `${fraction.width * 100}%`,
        height: `${fraction.height * 100}%`,
      }}
    />
  );
}

function PdfPage({ pdf, pageNumber, width, highlights, activeEvidenceId, onSelectEvidence }) {
  const canvasRef = useRef(null);
  const [size, setSize] = useState({ width: 0, height: 0 });
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    let renderTask = null;
    setFailed(false);
    (async () => {
      const page = await pdf.getPage(pageNumber);
      if (cancelled) return;
      const base = page.getViewport({ scale: 1 });
      const scale = Math.max(0.25, Math.min(3, width / base.width));
      const viewport = page.getViewport({ scale });
      const canvas = canvasRef.current;
      if (!canvas) return;
      canvas.width = Math.floor(viewport.width);
      canvas.height = Math.floor(viewport.height);
      canvas.style.width = `${Math.floor(viewport.width)}px`;
      canvas.style.height = `${Math.floor(viewport.height)}px`;
      renderTask = page.render({ canvasContext: canvas.getContext('2d'), viewport });
      await renderTask.promise;
      if (!cancelled) setSize({ width: viewport.width, height: viewport.height });
    })().catch((error) => {
      if (error?.name !== 'RenderingCancelledException' && !cancelled) {
        console.error('PDF page render failed', error);
        setFailed(true);
      }
    });
    return () => {
      cancelled = true;
      try { renderTask?.cancel(); } catch { /* already finished */ }
    };
  }, [pdf, pageNumber, width]);

  return (
    <figure className="mb-6">
      <figcaption className="mb-1 font-mono text-[11px] uppercase tracking-wide text-muted-foreground">
        Page {pageNumber}
      </figcaption>
      <div
        className="relative mx-auto border-2 border-border bg-white shadow-neo-sm"
        style={{ width: size.width || '100%', height: size.height || 240 }}
      >
        <canvas ref={canvasRef} className="block" />
        {size.width > 0 && highlights.map((item) => (
          <Highlight
            key={item.id}
            item={item}
            active={item.id === activeEvidenceId}
            onClick={() => onSelectEvidence(item.id)}
          />
        ))}
        {failed && (
          <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 bg-muted/80 p-6 text-center">
            <AlertTriangle size={28} />
            <p className="font-mono text-xs">Page {pageNumber} could not be rendered in this browser.</p>
            <p className="font-mono text-xs">The evidence record is still available in the list.</p>
          </div>
        )}
      </div>
    </figure>
  );
}

function ImagePage({ url, name, highlights, activeEvidenceId, onSelectEvidence }) {
  const [natural, setNatural] = useState({ width: 0, height: 0 });
  return (
    <figure>
      <figcaption className="mb-1 font-mono text-[11px] uppercase tracking-wide text-muted-foreground">
        {name || 'Image evidence'}
      </figcaption>
      <div className="relative mx-auto w-full border-2 border-border bg-white shadow-neo-sm">
        <img
          src={url}
          alt={name || 'Submitted evidence'}
          className="block w-full"
          onLoad={(event) => setNatural({
            width: event.currentTarget.naturalWidth,
            height: event.currentTarget.naturalHeight,
          })}
        />
        {natural.width > 0 && highlights.map((item) => {
          // Image bbox coordinates are pixels of the natural image.
          const scaled = { ...item, pageWidth: natural.width, pageHeight: natural.height };
          return (
            <Highlight
              key={item.id}
              item={scaled}
              active={item.id === activeEvidenceId}
              onClick={() => onSelectEvidence(item.id)}
            />
          );
        })}
      </div>
    </figure>
  );
}

export default function DocumentViewer({ token, document, documents, evidence, activeEvidenceId, onSelectEvidence }) {
  const [url, setUrl] = useState('');
  const [pdf, setPdf] = useState(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [width, setWidth] = useState(640);
  const [renderAll, setRenderAll] = useState(false);
  const containerRef = useRef(null);
  const scrollerRef = useRef(null);

  const versionId = document?.current_version_id;
  const isPdf = (document?.mime_type || '').toLowerCase().includes('pdf') || (document?.original_filename || '').toLowerCase().endsWith('.pdf');

  useEffect(() => {
    const element = containerRef.current;
    if (!element || typeof ResizeObserver === 'undefined') return;
    const observer = new ResizeObserver((entries) => {
      const next = entries[0]?.contentRect?.width;
      if (next) setWidth(next);
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    if (!token || !versionId) return undefined;
    let cancelled = false;
    setLoading(true);
    setError('');
    setPdf(null);
    setUrl('');
    api(`/api/v1/document-versions/${versionId}/download-url`, { token, method: 'POST' })
      .then((data) => {
        if (cancelled) return;
        // Local storage returns a relative signed path; S3/MinIO may return absolute.
        const signed = /^https?:\/\//i.test(data.url) ? data.url : `${API_BASE}${data.url}`;
        setUrl(signed);
        if (!isPdf) return null;
        return loadPdfjs().then((pdfjs) => pdfjs.getDocument({ url: signed, disableAutoFetch: true }).promise);
      })
      .then((loaded) => { if (!cancelled && loaded) setPdf(loaded); })
      .catch((err) => { if (!cancelled) setError(err.message || 'The document could not be opened.'); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => {
      cancelled = true;
      setPdf((current) => { try { current?.destroy(); } catch { /* noop */ } return null; });
    };
  }, [token, versionId, isPdf]);

  const pages = useMemo(() => {
    if (!pdf) return [];
    const relevant = new Set([1]);
    evidence.forEach((item) => { if (item.page) relevant.add(item.page); });
    if (renderAll) {
      return Array.from({ length: pdf.numPages }, (_, index) => index + 1);
    }
    return Array.from(relevant).sort((a, b) => a - b).filter((page) => page <= pdf.numPages);
  }, [pdf, evidence, renderAll]);

  const activeEvidence = evidence.find((item) => item.id === activeEvidenceId) || null;

  useEffect(() => {
    if (!activeEvidence?.page || !scrollerRef.current) return;
    const target = scrollerRef.current.querySelector(`[data-page="${activeEvidence.page}"]`);
    target?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }, [activeEvidence?.page, activeEvidenceId]);

  if (!document) {
    return (
      <div className="flex h-72 flex-col items-center justify-center gap-2 border-2 border-dashed border-border bg-muted/40 p-6 text-center">
        <FileText size={28} />
        <p className="font-mono text-xs">Select an evidence item to open its source document.</p>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="flex h-72 items-center justify-center gap-2 border-2 border-border bg-muted/40">
        <Loader2 className="animate-spin" size={20} /> <span className="font-mono text-xs">Opening signed document…</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex h-72 flex-col items-center justify-center gap-2 border-2 border-border bg-red-50 p-6 text-center">
        <AlertTriangle size={24} className="text-red-700" />
        <p className="font-mono text-xs text-red-800">{error}</p>
        <p className="font-mono text-[11px]">Signed links expire quickly. Re-select the evidence to retry.</p>
      </div>
    );
  }

  return (
    <div ref={containerRef} className="border-2 border-border bg-muted/30">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b-2 border-border bg-card px-3 py-2">
        <div className="flex items-center gap-2 font-mono text-xs">
          {isPdf ? <FileText size={14} /> : <ImageIcon size={14} />}
          <span className="font-bold">{document.document_type}</span>
          <span className="text-muted-foreground">{document.original_filename || document.current_version_id?.slice(0, 8)}</span>
        </div>
        <div className="flex items-center gap-2">
          {isPdf && pdf && (
            <button
              type="button"
              onClick={() => setRenderAll((value) => !value)}
              className="flex items-center gap-1 border-2 border-border px-2 py-0.5 font-mono text-[11px] font-bold hover:bg-muted"
            >
              <RefreshCw size={12} /> {renderAll ? 'Evidence pages only' : `All ${pdf.numPages} pages`}
            </button>
          )}
          <span className="border-2 border-border px-2 py-0.5 font-mono text-[11px]">
            {evidence.length} evidence mark{evidence.length === 1 ? '' : 's'}
          </span>
        </div>
      </div>
      <div ref={scrollerRef} className="max-h-[70vh] overflow-auto p-3">
        {isPdf && pdf && pages.map((pageNumber) => (
          <div key={pageNumber} data-page={pageNumber}>
            <PdfPage
              pdf={pdf}
              pageNumber={pageNumber}
              width={width - 40}
              highlights={evidence.filter((item) => (item.page || 1) === pageNumber)}
              activeEvidenceId={activeEvidenceId}
              onSelectEvidence={onSelectEvidence}
            />
          </div>
        ))}
        {!isPdf && url && (
          <ImagePage
            url={url}
            name={document.original_filename}
            highlights={evidence.filter((item) => (item.page || 1) === 1)}
            activeEvidenceId={activeEvidenceId}
            onSelectEvidence={onSelectEvidence}
          />
        )}
        {isPdf && !pdf && !error && (
          <div className="flex h-48 items-center justify-center">
            <Loader2 className="animate-spin" size={20} />
          </div>
        )}
      </div>
      {documents.length > 1 && (
        <div className="border-t-2 border-border px-3 py-2 font-mono text-[11px] text-muted-foreground">
          Evidence boxes come from the stored extraction; they are advisory and may be imprecise on scanned pages.
        </div>
      )}
    </div>
  );
}
