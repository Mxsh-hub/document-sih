import React, { useEffect, useState } from 'react';
import { ClipboardList, Loader2, Plus, Save, Trash2 } from 'lucide-react';
import { api } from '../../lib/api';

const EMPTY_PROGRAMME = { code: '', name: '', level: '', intake: '' };

function toInputValue(value) {
  return value === null || value === undefined ? '' : String(value);
}

function toInt(value) {
  if (value === '' || value === null || value === undefined) return null;
  const parsed = Number.parseInt(value, 10);
  return Number.isNaN(parsed) ? null : parsed;
}

/**
 * Applicant-declared structured facts.
 *
 * These values are applicant-supplied and explicitly unverified. Saving them
 * lets validation compare the declaration with extracted document fields and
 * with the synthetic institutional records; every resulting finding stays
 * advisory.
 */
export default function DeclarationForm({ applicationId, token, editable, onSaved }) {
  const [form, setForm] = useState({
    affiliation_number: '',
    affiliation_valid_until: '',
    total_intake: '',
    faculty_count: '',
    previous_approval_reference: '',
  });
  const [programmes, setProgrammes] = useState([]);
  const [version, setVersion] = useState(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    let cancelled = false;
    if (!applicationId) return () => { cancelled = true; };
    setLoading(true);
    setError('');
    api(`/api/v1/applications/${applicationId}/declaration`, { token })
      .then((body) => {
        if (cancelled) return;
        const declaration = body?.declaration;
        setVersion(declaration?.version ?? null);
        setForm({
          affiliation_number: toInputValue(declaration?.affiliation_number),
          affiliation_valid_until: toInputValue(declaration?.affiliation_valid_until),
          total_intake: toInputValue(declaration?.total_intake),
          faculty_count: toInputValue(declaration?.faculty_count),
          previous_approval_reference: toInputValue(declaration?.previous_approval_reference),
        });
        setProgrammes(
          (declaration?.programmes || []).map((item) => ({
            code: toInputValue(item.code),
            name: toInputValue(item.name),
            level: toInputValue(item.level),
            intake: toInputValue(item.intake),
          })),
        );
      })
      .catch((err) => { if (!cancelled) setError(err.message); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [applicationId, token]);

  const setField = (key, value) => setForm((current) => ({ ...current, [key]: value }));

  const setProgramme = (index, key, value) =>
    setProgrammes((current) =>
      current.map((item, itemIndex) => (itemIndex === index ? { ...item, [key]: value } : item)),
    );

  const addProgramme = () => setProgrammes((current) => [...current, { ...EMPTY_PROGRAMME }]);
  const removeProgramme = (index) =>
    setProgrammes((current) => current.filter((_, itemIndex) => itemIndex !== index));

  const save = async () => {
    setSaving(true);
    setError('');
    try {
      const saved = await api(`/api/v1/applications/${applicationId}/declaration`, {
        token,
        method: 'PUT',
        body: {
          affiliation_number: form.affiliation_number.trim() || null,
          affiliation_valid_until: form.affiliation_valid_until || null,
          programmes: programmes
            .filter((item) => item.code.trim())
            .map((item) => ({
              code: item.code,
              name: item.name.trim() || null,
              level: item.level.trim() || null,
              intake: toInt(item.intake),
            })),
          total_intake: toInt(form.total_intake),
          faculty_count: toInt(form.faculty_count),
          previous_approval_reference: form.previous_approval_reference.trim() || null,
        },
      });
      setVersion(saved.version);
      if (onSaved) await onSaved(saved);
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <section className="neo-box p-5 bg-card space-y-4">
      <div className="flex flex-wrap justify-between gap-2 items-center">
        <h3 className="text-xl font-bold flex items-center gap-2">
          <ClipboardList size={20} /> Application declaration
        </h3>
        <span className="font-mono text-xs">
          {version ? `saved version ${version}` : 'not yet saved'}
          {editable ? '' : ' · read-only'}
        </span>
      </div>

      <p className="text-xs font-mono">
        Declared values are applicant-supplied and <b>not verified</b>. Validation compares them with extracted
        document fields and synthetic institutional records; differences are advisory for human review.
      </p>

      {loading ? (
        <p className="font-mono text-sm flex items-center gap-2"><Loader2 className="animate-spin" size={16} /> Loading declaration…</p>
      ) : (
        <>
          <div className="grid md:grid-cols-3 gap-3">
            <label className="font-bold text-sm">Affiliation number
              <input
                value={form.affiliation_number}
                onChange={(event) => setField('affiliation_number', event.target.value)}
                disabled={!editable}
                className="mt-1 w-full border-2 border-border p-2 font-mono text-sm disabled:bg-muted"
                placeholder="AFF/2026/001"
              />
            </label>
            <label className="font-bold text-sm">Affiliation valid until
              <input
                type="date"
                value={form.affiliation_valid_until}
                onChange={(event) => setField('affiliation_valid_until', event.target.value)}
                disabled={!editable}
                className="mt-1 w-full border-2 border-border p-2 font-mono text-sm disabled:bg-muted"
              />
            </label>
            <label className="font-bold text-sm">Previous approval reference
              <input
                value={form.previous_approval_reference}
                onChange={(event) => setField('previous_approval_reference', event.target.value)}
                disabled={!editable}
                className="mt-1 w-full border-2 border-border p-2 font-mono text-sm disabled:bg-muted"
                placeholder="APP-2025-000421"
              />
            </label>
            <label className="font-bold text-sm">Total sanctioned intake
              <input
                type="number"
                min="0"
                value={form.total_intake}
                onChange={(event) => setField('total_intake', event.target.value)}
                disabled={!editable}
                className="mt-1 w-full border-2 border-border p-2 font-mono text-sm disabled:bg-muted"
              />
            </label>
            <label className="font-bold text-sm">Total faculty count
              <input
                type="number"
                min="0"
                value={form.faculty_count}
                onChange={(event) => setField('faculty_count', event.target.value)}
                disabled={!editable}
                className="mt-1 w-full border-2 border-border p-2 font-mono text-sm disabled:bg-muted"
              />
            </label>
          </div>

          <div className="space-y-2">
            <div className="flex justify-between items-center">
              <h4 className="font-bold">Declared programmes</h4>
              {editable && (
                <button type="button" onClick={addProgramme} className="neo-button border-2 border-border px-3 py-1 font-bold flex items-center gap-1">
                  <Plus size={14} /> Add programme
                </button>
              )}
            </div>
            {!programmes.length && <p className="font-mono text-sm">No programmes declared.</p>}
            {programmes.map((programme, index) => (
              <div key={index} className="grid grid-cols-2 md:grid-cols-[110px_1fr_90px_110px_auto] gap-2 items-end">
                <label className="font-bold text-xs">Code
                  <input value={programme.code} onChange={(event) => setProgramme(index, 'code', event.target.value)} disabled={!editable} className="mt-1 w-full border-2 border-border p-2 font-mono text-sm disabled:bg-muted" placeholder="CSE" />
                </label>
                <label className="font-bold text-xs">Name
                  <input value={programme.name} onChange={(event) => setProgramme(index, 'name', event.target.value)} disabled={!editable} className="mt-1 w-full border-2 border-border p-2 font-mono text-sm disabled:bg-muted" placeholder="B.Tech Computer Science" />
                </label>
                <label className="font-bold text-xs">Level
                  <input value={programme.level} onChange={(event) => setProgramme(index, 'level', event.target.value)} disabled={!editable} className="mt-1 w-full border-2 border-border p-2 font-mono text-sm disabled:bg-muted" placeholder="UG" />
                </label>
                <label className="font-bold text-xs">Intake
                  <input type="number" min="0" value={programme.intake} onChange={(event) => setProgramme(index, 'intake', event.target.value)} disabled={!editable} className="mt-1 w-full border-2 border-border p-2 font-mono text-sm disabled:bg-muted" />
                </label>
                {editable && (
                  <button type="button" onClick={() => removeProgramme(index)} aria-label={`Remove ${programme.code || 'programme'}`} className="neo-button border-2 border-border px-2 py-2 text-red-700">
                    <Trash2 size={16} />
                  </button>
                )}
              </div>
            ))}
          </div>

          {editable && (
            <button type="button" onClick={save} disabled={saving} className="neo-button bg-primary text-primary-foreground px-4 py-2 font-bold flex items-center gap-2">
              {saving ? <Loader2 className="animate-spin" size={16} /> : <Save size={16} />} Save declaration
            </button>
          )}
          {error && <p className="text-red-700 font-mono text-sm">{error}</p>}
        </>
      )}
    </section>
  );
}
