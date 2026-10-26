import React, { useEffect, useState } from 'react';
import { CheckCircle2, Download, FileUp, Loader2, LockKeyhole, RefreshCw, Send, ShieldCheck, XCircle } from 'lucide-react';
import { api, downloadFile } from '../lib/api';
import AlertPanel from './compliance/AlertPanel';
import DeclarationForm from './compliance/DeclarationForm';
import EvidenceWorkspace from './compliance/EvidenceWorkspace';
import SelfCheckPanel from './compliance/SelfCheckPanel';
import VerificationTools from './compliance/VerificationTools';

const ACCOUNTS = [
  ['applicant@example.test', 'Applicant'],
  ['reviewer@example.test', 'Reviewer'],
  ['approver@example.test', 'Approver'],
  ['admin@example.test', 'Admin'],
  ['auditor@example.test', 'Auditor'],
];

function Badge({ value }) {
  const good = ['PASS', 'VERIFIED', 'APPROVED'].includes(value);
  const bad = ['FAIL', 'REJECTED', 'PROOF_INVALID'].includes(value);
  return <span className={`border px-2 py-0.5 text-xs font-mono font-bold ${good ? 'bg-emerald-100 text-emerald-800 border-emerald-300' : bad ? 'bg-red-100 text-red-800 border-red-300' : 'bg-amber-100 text-amber-800 border-amber-300'}`}>{value}</span>;
}

export default function CompliancePortal() {
  const [auth, setAuth] = useState(() => { try { return JSON.parse(localStorage.getItem('astra-session') || 'null'); } catch { return null; } });
  const [email, setEmail] = useState('applicant@example.test');
  const [password, setPassword] = useState('ChangeMe123!');
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [applications, setApplications] = useState([]);
  const [selectedId, setSelectedId] = useState('');
  const [detail, setDetail] = useState(null);
  const [checklist, setChecklist] = useState([]);
  const [proofs, setProofs] = useState([]);
  const [overview, setOverview] = useState(null);
  const [dashboard, setDashboard] = useState(null);
  const [cycle, setCycle] = useState('2026-27');
  const [cgpa, setCgpa] = useState('8.5');
  const [note, setNote] = useState('Synthetic demo review action.');
  const [rationale, setRationale] = useState('Synthetic demo decision after human review.');
  const [selfCheckKey, setSelfCheckKey] = useState(0);

  const token = auth?.access_token;
  const role = auth?.user?.role || '';

  const persist = (session) => {
    setAuth(session);
    if (session) localStorage.setItem('astra-session', JSON.stringify(session));
    else localStorage.removeItem('astra-session');
  };

  const run = async (label, action) => {
    setBusy(label); setError(''); setNotice('');
    try { await action(); } catch (err) { setError(err.message); } finally { setBusy(''); }
  };

  const loadApplications = async () => {
    const page = await api('/api/v1/applications?page_size=50', { token });
    setApplications(page.items);
    if (!selectedId && page.items[0]) setSelectedId(page.items[0].id);
    return page.items;
  };

  const loadDetail = async (id = selectedId) => {
    if (!id) return;
    const [app, checks, proofList] = await Promise.all([
      api(`/api/v1/applications/${id}`, { token }),
      api(`/api/v1/applications/${id}/checklist`, { token }),
      api(`/api/v1/zkp/applications/${id}/proofs`, { token }).catch(() => ({ items: [] })),
    ]);
    setDetail(app); setChecklist(checks.items); setProofs(proofList.items || []);
  };

  useEffect(() => {
    if (!token) return;
    run('load', async () => {
      await loadApplications();
      setDashboard(await api('/api/v1/dashboard/summary', { token }).catch(() => null));
    });
  }, [token]);

  useEffect(() => {
    if (!token || !selectedId) return;
    run('detail', () => loadDetail(selectedId));
  }, [token, selectedId]);

  const login = (event) => {
    event.preventDefault();
    run('login', async () => {
      const session = await api('/api/v1/auth/login', { method: 'POST', body: { email, password } });
      persist(session);
      setNotice(`Signed in as ${session.user.role}. Demo session only.`);
    });
  };

  const createApplication = () => run('create', async () => {
    const created = await api('/api/v1/applications', { token, method: 'POST', body: { category_code: 'EOA', cycle } });
    await loadApplications(); setSelectedId(created.id);
    setNotice(`Created synthetic EoA application ${created.reference_no}.`);
  });

  const upload = (item, file) => run(`upload-${item.id}`, async () => {
    const form = new FormData();
    form.append('file', file);
    form.append('document_type', item.accepted_document_types[0]);
    form.append('checklist_item_id', item.id);
    await api(`/api/v1/applications/${selectedId}/documents`, { token, method: 'POST', form });
    await loadDetail();
    setSelfCheckKey((key) => key + 1);
    setNotice(`Uploaded evidence for ${item.title}. Server-side extraction and validation completed.`);
  });

  const submit = () => run('submit', async () => {
    const result = await api(`/api/v1/applications/${selectedId}/submit`, { token, method: 'POST' });
    await loadDetail(); await loadApplications();
    setNotice(`Submitted. Validation run ${result.validation_run_id || 'not run'}. Findings are advisory.`);
  });

  const loadReview = () => run('review', async () => {
    const data = await api(`/api/v1/applications/${selectedId}/review-overview`, { token });
    setOverview(data); setNotice('Loaded evidence-linked review overview, anomalies, issuer checks, and audit history.');
  });

  const action = (actionType) => run(actionType, async () => {
    await api(`/api/v1/applications/${selectedId}/review-actions`, { token, method: 'POST', body: { action_type: actionType, note } });
    await loadDetail(); await loadReview();
    setNotice(`${actionType.replaceAll('_', ' ')} recorded with reviewer attribution.`);
  });

  const decide = (decisionType) => run(decisionType, async () => {
    await api(`/api/v1/applications/${selectedId}/decisions`, { token, method: 'POST', body: { decision_type: decisionType, rationale } });
    await loadDetail(); await loadApplications(); await loadReview();
    setNotice(`Final ${decisionType} recorded by an authorized human.`);
  });

  const createProof = () => run('proof', async () => {
    if (!window.snarkjs) throw new Error('snarkjs is not loaded. Check network access to the CDN.');
    const challenge = await api('/api/v1/zkp/challenges', { token, method: 'POST', body: { application_id: selectedId, audience: 'synthetic-demo-reviewer' } });
    const randomField = () => String(Math.floor(Math.random() * 2 ** 120) + 1);
    const { proof, publicSignals } = await window.snarkjs.groth16.fullProve(
      { value: String(Math.round(Number(cgpa) * 100)), blinding: randomField(), secret: randomField(), threshold: challenge.threshold, requestHash: challenge.request_hash },
      '/circuits/faculty_threshold/faculty_threshold.wasm',
      '/circuits/faculty_threshold/faculty_threshold_final.zkey',
    );
    const verified = await api('/api/v1/zkp/proofs', { token, method: 'POST', body: { challenge_id: challenge.id, proof, public_signals: publicSignals.map(String) } });
    await loadDetail();
    setNotice(`Groth16 proof status: ${verified.status}. Only threshold satisfaction, commitment, and nullifier are public.`);
  });

  const verifyAudit = () => run('audit', async () => {
    const chain = await api('/api/v1/admin/audit-events/verify', { token });
    setNotice(chain.valid ? 'Audit hash chain is valid.' : `Audit chain broken at sequence ${chain.broken_sequence}.`);
  });

  const exportReport = (format) => run(`export-${format}`, async () => {
    const filename = await downloadFile(`/api/v1/applications/${selectedId}/report?format=${format}`, {
      token,
      fallbackName: `application-report.${format === 'markdown' ? 'md' : format}`,
    });
    setNotice(`Exported advisory ${format} report as ${filename}. It is a review aid, not a signed or official document.`);
  });

  if (!auth) {
    return (
      <div className="max-w-xl mx-auto neo-box p-8 bg-card">
        <h1 className="text-3xl font-bold mb-2">AICTE Compliance Console</h1>
        <p className="font-mono text-sm mb-6">Seeded users · synthetic records · advisory findings.</p>
        <form onSubmit={login} className="space-y-4">
          <label className="block font-bold">Demo account
            <select className="mt-1 w-full border-2 border-border p-3 bg-background" value={email} onChange={(e) => setEmail(e.target.value)}>
              {ACCOUNTS.map(([value, label]) => <option key={value} value={value}>{label} — {value}</option>)}
            </select>
          </label>
          <label className="block font-bold">Password
            <input type="password" className="mt-1 w-full border-2 border-border p-3 bg-background" value={password} onChange={(e) => setPassword(e.target.value)} />
          </label>
          <button disabled={busy === 'login'} className="neo-button bg-primary text-primary-foreground w-full p-3 font-bold flex items-center justify-center gap-2">
            {busy === 'login' ? <Loader2 className="animate-spin" size={18} /> : <LockKeyhole size={18} />} Sign in
          </button>
          {error && <p className="text-red-700 font-mono text-sm">{error}</p>}
        </form>
        <p className="text-xs font-mono mt-6">Default seeded password: ChangeMe123!. No real AICTE, DigiLocker, or issuer access.</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <header className="neo-box p-6 bg-card flex flex-wrap gap-4 justify-between items-center">
        <div>
          <h1 className="text-3xl font-bold">AICTE Compliance Console</h1>
          <p className="font-mono text-sm">{auth.user.email} · {role}</p>
        </div>
        <div className="flex gap-2">
          <button onClick={() => run('refresh', async () => { await loadApplications(); await loadDetail(); })} className="neo-button border-2 border-border px-3 py-2 font-bold flex items-center gap-2"><RefreshCw size={16} /> Refresh</button>
          <button onClick={() => { persist(null); setApplications([]); setDetail(null); setOverview(null); }} className="neo-button border-2 border-border px-3 py-2 font-bold">Sign out</button>
        </div>
      </header>

      {(error || notice) && <div className={`neo-box p-3 font-mono text-sm ${error ? 'bg-red-50 border-red-400' : 'bg-emerald-50 border-emerald-400'}`}>{error || notice}</div>}

      {dashboard && (
        <section className="grid grid-cols-2 md:grid-cols-5 gap-3">
          {Object.entries(dashboard.counts || {}).map(([status, count]) => <div key={status} className="neo-box bg-card p-3"><div className="text-xs font-mono">{status}</div><div className="text-2xl font-bold">{count}</div></div>)}
        </section>
      )}

      <section className="grid lg:grid-cols-[300px_1fr] gap-6 items-start">
        <aside className="neo-box p-4 bg-card space-y-3">
          <h2 className="font-bold text-xl">Applications</h2>
          {role === 'APPLICANT' && <div className="flex gap-2"><input value={cycle} onChange={(e) => setCycle(e.target.value)} className="border-2 border-border p-2 w-28 font-mono" aria-label="Cycle" /><button onClick={createApplication} disabled={busy === 'create'} className="neo-button bg-primary text-primary-foreground px-3 py-2 font-bold">Create</button></div>}
          <div className="space-y-2 max-h-[32rem] overflow-auto">
            {applications.map((app) => <button key={app.id} onClick={() => setSelectedId(app.id)} className={`w-full text-left border-2 p-3 ${selectedId === app.id ? 'border-border bg-muted' : 'border-transparent hover:border-border'}`}><div className="font-bold">{app.reference_no}</div><div className="text-xs font-mono">{app.cycle} · {app.status}</div></button>)}
            {!applications.length && <p className="text-sm font-mono">No applications available.</p>}
          </div>
        </aside>

        <main className="space-y-6">
          {detail && <div className="neo-box p-5 bg-card"><div className="flex flex-wrap justify-between gap-2"><div><h2 className="text-2xl font-bold">{detail.reference_no}</h2><p className="font-mono text-sm">{detail.category_code} · {detail.cycle}</p></div><Badge value={detail.status} /></div><p className="font-mono text-xs mt-2">Synthetic institution: {detail.institution?.name || detail.institution_id}</p>{role === 'APPLICANT' && <button onClick={submit} disabled={busy === 'submit'} className="neo-button bg-primary text-primary-foreground px-4 py-2 font-bold flex items-center gap-2 mt-4"><Send size={16} /> Submit for validation</button>}</div>}

          {detail && <DeclarationForm
            key={detail.id}
            applicationId={detail.id}
            token={token}
            editable={role === 'APPLICANT' && detail.status === 'DRAFT'}
            onSaved={async (saved) => {
              await loadDetail();
              setSelfCheckKey((key) => key + 1);
              setNotice(`Declaration v${saved.version} saved. Declared values are not verified; validation compares them with documents and synthetic records.`);
            }}
          />}

          {detail && role === 'APPLICANT' && ['DRAFT', 'RECTIFICATION_REQUESTED'].includes(detail.status) && (
            <SelfCheckPanel applicationId={detail.id} token={token} refreshKey={selfCheckKey} />
          )}

          {checklist.length > 0 && <div className="neo-box p-5 bg-card"><h3 className="text-xl font-bold">Evidence checklist</h3><div className="mt-3 space-y-2">{checklist.map((item) => <div key={item.id} className="border-2 border-border p-3 flex flex-wrap gap-3 justify-between items-center"><div><div className="font-bold">{item.title}</div><div className="text-xs font-mono">{item.code} · {item.accepted_document_types.join(', ')}</div></div><div className="flex items-center gap-3"><Badge value={item.status} />{role === 'APPLICANT' && <label className="neo-button bg-accent text-accent-foreground px-3 py-1.5 font-bold cursor-pointer flex items-center gap-2"><FileUp size={16} /> Upload<input type="file" className="hidden" accept=".pdf,.png,.jpg,.jpeg" onChange={(e) => e.target.files[0] && upload(item, e.target.files[0])} /></label>}</div></div>)}</div></div>}

          {selectedId && <div className="neo-box p-5 bg-card space-y-3"><h3 className="text-xl font-bold flex items-center gap-2"><ShieldCheck size={20} /> Faculty eligibility threshold proof</h3><p className="text-sm font-mono">Sound Groth16 circuit · server-issued challenge · pinned verification key.</p><div className="flex flex-wrap gap-2 items-end"><label className="font-bold">CGPA (0–10)<input value={cgpa} onChange={(e) => setCgpa(e.target.value)} className="block border-2 border-border p-2 w-28 font-mono" /></label><button onClick={createProof} disabled={busy === 'proof'} className="neo-button bg-primary text-primary-foreground px-4 py-2 font-bold">{busy === 'proof' ? 'Proving…' : 'Generate and verify proof'}</button></div>{proofs.map((proof) => <div key={proof.id} className="border-2 border-border p-2 text-xs font-mono break-all"><Badge value={proof.status} /> commitment {proof.commitment.slice(0, 24)}… · nullifier {proof.nullifier.slice(0, 24)}… · chain {proof.chain_status}</div>)}<p className="text-xs font-mono">The proof establishes the committed private value meets the threshold. It does not prove the value is true or that the applicant is the real credential holder.</p></div>}

          {role !== 'APPLICANT' && selectedId && <div className="neo-box p-5 bg-card space-y-3"><div className="flex flex-wrap justify-between gap-2 items-center"><h3 className="text-xl font-bold">Human review</h3><div className="flex flex-wrap items-center gap-2"><span className="font-mono text-[10px] text-muted-foreground">Export advisory report:</span><button onClick={() => exportReport('json')} disabled={busy === 'export-json'} className="neo-button border-2 border-border px-3 py-1.5 font-bold flex items-center gap-1"><Download size={14} /> JSON</button><button onClick={() => exportReport('markdown')} disabled={busy === 'export-markdown'} className="neo-button border-2 border-border px-3 py-1.5 font-bold flex items-center gap-1"><Download size={14} /> Markdown</button><button onClick={() => exportReport('html')} disabled={busy === 'export-html'} className="neo-button border-2 border-border px-3 py-1.5 font-bold flex items-center gap-1"><Download size={14} /> HTML</button><button onClick={loadReview} className="neo-button border-2 border-border px-3 py-1.5 font-bold">Load review overview</button></div></div><textarea value={note} onChange={(e) => setNote(e.target.value)} className="w-full border-2 border-border p-2 font-mono text-sm" rows={2} /><div className="flex flex-wrap gap-2"><button onClick={() => action('ASSIGN')} className="neo-button border-2 border-border px-3 py-1.5 font-bold">Assign to me</button><button onClick={() => action('NOTE')} className="neo-button border-2 border-border px-3 py-1.5 font-bold">Add note</button><button onClick={() => action('REQUEST_RECTIFICATION')} className="neo-button border-2 border-border px-3 py-1.5 font-bold">Request rectification</button><button onClick={verifyAudit} className="neo-button border-2 border-border px-3 py-1.5 font-bold">Verify audit chain</button></div>{(role === 'APPROVER' || role === 'ADMIN') && <div className="border-t-2 border-border pt-3 space-y-2"><textarea value={rationale} onChange={(e) => setRationale(e.target.value)} className="w-full border-2 border-border p-2 font-mono text-sm" rows={2} /><div className="flex gap-2"><button onClick={() => decide('APPROVE')} className="neo-button bg-emerald-600 text-white px-3 py-1.5 font-bold flex items-center gap-1"><CheckCircle2 size={16} /> Approve</button><button onClick={() => decide('REJECT')} className="neo-button bg-red-600 text-white px-3 py-1.5 font-bold flex items-center gap-1"><XCircle size={16} /> Reject</button></div></div>}</div>}

          {overview && <EvidenceWorkspace overview={overview} token={token} />}

          {overview && role !== 'APPLICANT' && (
            <AlertPanel
              applicationId={selectedId}
              alerts={overview.alerts}
              token={token}
              onRefreshed={loadReview}
            />
          )}

          {overview && <VerificationTools applicationId={selectedId} overview={overview} token={token} onRefreshed={loadReview} />}

          {overview && <div className="grid md:grid-cols-2 gap-4"><div className="neo-box p-4 bg-card"><h3 className="font-bold">Advisory anomaly signals</h3>{!(overview.anomaly_signals || []).length && <p className="text-sm font-mono">No signals.</p>}{(overview.anomaly_signals || []).map((signal) => <div key={signal.id} className="border-t border-border py-2 text-sm"><b>{signal.signal_code}</b> · {signal.severity}<br />{signal.message}</div>)}</div><div className="neo-box p-4 bg-card"><h3 className="font-bold">Issuer verification</h3>{!(overview.issuer_verifications || []).filter((item) => !['qr-payload', 'pdf-signature'].includes(item.adapter_code)).length && <p className="text-sm font-mono">No issuer verification attempts. Technical inspection results appear above.</p>}{(overview.issuer_verifications || []).filter((item) => !['qr-payload', 'pdf-signature'].includes(item.adapter_code)).map((item) => <div key={item.id} className="border-t border-border py-2 text-sm"><Badge value={item.status} /> <span className="font-mono text-xs">{item.adapter_code}</span> {item.simulated_source && <span className="font-mono text-xs">(simulated source)</span>}<br />{item.message}</div>)}</div><div className="neo-box p-4 bg-card md:col-span-2"><h3 className="font-bold">Audit history</h3><div className="max-h-64 overflow-auto font-mono text-xs mt-2">{(overview.audit_events || []).map((event) => <div key={event.id} className="border-t border-border py-1">{event.sequence} · {event.event_type} · {event.actor_id?.slice(0, 8) || 'system'} · {event.event_hash?.slice(0, 16)}…</div>)}</div></div></div>}
        </main>
      </section>

      <p className="font-mono text-xs text-center pb-6">All institutions, records, issuer responses, and documents are synthetic. Findings are advisory; no automated rejection. Final decisions require an authorized human.</p>
    </div>
  );
}
