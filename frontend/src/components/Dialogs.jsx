import React, { useEffect, useRef, useState } from 'react';
import { api } from '../api';
import { localInput, money } from '../format';

export function Dialog({ title, eyebrow, onClose, children }) {
  const ref = useRef(null);
  useEffect(() => { ref.current.showModal(); }, []);
  return <dialog ref={ref} aria-label={title} onCancel={onClose}>
    <div className="modal-head"><div>{eyebrow && <p className="eyebrow">{eyebrow}</p>}<h2>{title}</h2></div>
      <button type="button" className="icon-button" onClick={onClose} aria-label="Close dialog">×</button></div>
    {children}
  </dialog>;
}
function FormActions({ busy, onClose, label }) {
  return <div className="modal-actions"><button type="button" onClick={onClose}>Cancel</button>
    <button className="primary" type="submit" disabled={busy}>{busy ? 'Saving…' : label}</button></div>;
}

export function CreateForm({ onClose, onSaved, now }) {
  const [enabled, setEnabled] = useState(true);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  // Keep default form times stable while the parent updates its countdown clock.
  const [defaults] = useState(() => ({
    start: localInput(new Date(now)), close: localInput(new Date(now + 3600000)),
    forced: localInput(new Date(now + 7200000)), service: localInput(new Date(now + 7 * 86400000)).slice(0, 10),
  }));
  async function submit(event) {
    event.preventDefault();
    const f = new FormData(event.currentTarget);
    setBusy(true); setError('');
    try {
      const result = await api('/api/rfqs', {
        name: f.get('name'), reference: f.get('reference'), currency: f.get('currency'),
        start_at: new Date(f.get('start_at')).toISOString(), close_at: new Date(f.get('close_at')).toISOString(),
        forced_close_at: new Date(f.get('forced_close_at')).toISOString(), service_date: f.get('service_date'),
        british_enabled: enabled, trigger_minutes: enabled ? Number(f.get('trigger_minutes')) : 10,
        extension_minutes: enabled ? Number(f.get('extension_minutes')) : 5, triggers: f.getAll('triggers'),
      });
      onSaved(result.id);
    } catch (e) { setError(e.message); } finally { setBusy(false); }
  }
  return <Dialog title="Create an RFQ" eyebrow="NEW AUCTION" onClose={onClose}>
    <p className="muted">Set your bidding schedule and extension rules.</p>
    <form onSubmit={submit}>{error && <div className="form-error" role="alert">{error}</div>}
      <div className="form-grid">
        <label className="full">RFQ name<input name="name" required maxLength="120" placeholder="e.g. Mumbai to Delhi · Road freight" /></label>
        <label>Reference ID<input name="reference" required maxLength="40" placeholder="RFQ-004" /></label>
        <label>Currency<select name="currency">{['INR', 'USD', 'EUR', 'GBP'].map(c => <option key={c}>{c}</option>)}</select></label>
        <label>Bid start<input name="start_at" type="datetime-local" required defaultValue={defaults.start} /></label>
        <label>Bid close<input name="close_at" type="datetime-local" required defaultValue={defaults.close} /></label>
        <label>Forced bid close<input name="forced_close_at" type="datetime-local" required defaultValue={defaults.forced} /></label>
        <label>Pickup / service date<input name="service_date" type="date" required defaultValue={defaults.service} /></label>
      </div>
      <div className="form-divider" />
      <label className="check strong"><input type="checkbox" checked={enabled} onChange={e => setEnabled(e.target.checked)} />Enable British Auction extensions</label>
      <fieldset disabled={!enabled}><legend className="sr-only">Extension rules</legend><div className="form-grid">
        <label>Trigger window (minutes)<input name="trigger_minutes" type="number" min="1" max="1440" defaultValue="10" required /></label>
        <label>Extension duration (minutes)<input name="extension_minutes" type="number" min="1" max="1440" defaultValue="5" required /></label>
      </div><p className="field-label">Extend when any selected condition occurs</p>
        <label className="check"><input name="triggers" type="checkbox" value="bid_received" defaultChecked />A new bid is received</label>
        <label className="check"><input name="triggers" type="checkbox" value="rank_change" />A supplier’s rank changes</label>
        <label className="check"><input name="triggers" type="checkbox" value="l1_change" />The lowest bidder (L1) changes</label>
        <p className="hint">Only a strictly lower auction best price can trigger an extension, inside the current trigger window. The first bid does not extend. Forced close is always the limit.</p>
      </fieldset><FormActions busy={busy} onClose={onClose} label="Create RFQ" />
    </form>
  </Dialog>;
}

export function QuoteForm({ auction, now, onClose, onSaved }) {
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [charges, setCharges] = useState({ freight: '', origin: '0', destination: '0' });
  const [validUntil] = useState(() => localInput(new Date(now + 7 * 86400000)));
  const total = Object.values(charges).reduce((sum, value) => sum + Math.round(Number(value || 0) * 100), 0);
  async function submit(event) {
    event.preventDefault();
    const f = new FormData(event.currentTarget);
    setBusy(true); setError('');
    try {
      const result = await api(`/api/rfqs/${auction.id}/quotes`, {
        carrier: f.get('carrier'), ...charges, transit_days: Number(f.get('transit_days')),
        valid_until: new Date(f.get('valid_until')).toISOString(),
      });
      onSaved(result.extended);
    } catch (e) { setError(e.message); } finally { setBusy(false); }
  }
  return <Dialog title="Submit a quote" eyebrow="JOIN THE COMPETITION" onClose={onClose}>
    <p className="muted">{auction.reference} · {auction.currency} · Lowest: {money(auction.lowest_cents, auction.currency)}</p>
    <form onSubmit={submit}>{error && <div className="form-error" role="alert">{error}</div>}
      <div className="form-grid"><label className="full">Carrier / supplier name<input name="carrier" required maxLength="80" placeholder="Your carrier name" autoComplete="organization" /></label>
        {Object.keys(charges).map(key => <label key={key}>{key[0].toUpperCase() + key.slice(1)} charges
          <input name={key} type="number" min="0" max="1000000000" step="0.01" required placeholder="0.00" value={charges[key]}
            onChange={e => setCharges({ ...charges, [key]: e.target.value })} /></label>)}
        <label>Transit time (days)<input name="transit_days" type="number" min="1" max="3650" required placeholder="3" /></label>
        <label className="full">Quote valid until<input name="valid_until" type="datetime-local" required defaultValue={validUntil} /></label>
      </div><div className="quote-total"><span>Total quote</span><strong>{money(total, auction.currency)}</strong></div>
      <p className="hint">Ranked on the total of all three charges. Revised quotes must lower your previous total. Equal totals with another supplier are not allowed.</p>
      <FormActions busy={busy} onClose={onClose} label="Submit quote" />
    </form>
  </Dialog>;
}
