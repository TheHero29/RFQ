import React from 'react';
import { money, dateTime, serviceDate, countdown, triggerLabels } from '../format';
import { Status, Empty, Stats } from './ui';

export default function AuctionDetail({ data, now, onQuote }) {
  const { rfq: a, rankings, quotes, events } = data;
  const active = a.status === 'Active' && new Date(a.close_at).getTime() > now;
  const info = [
    ['Bid start', dateTime(a.start_at)], ['Original close', dateTime(a.original_close_at)],
    ['Current close', dateTime(a.close_at)], ['Forced close', dateTime(a.forced_close_at)],
    ['Trigger window', `${a.trigger_minutes} minutes`], ['Extension duration', `${a.extension_minutes} minutes`],
  ];
  return <section id="detail"><a className="back-link" href="#">Back to auctions</a>
    <div className="page-heading detail-heading"><div><p className="eyebrow">{a.reference} · {a.british_enabled ? 'BRITISH AUCTION' : 'STANDARD RFQ'}</p>
      <h1>{a.name}</h1><p className="muted">Pickup / service: {serviceDate(a.service_date)} <Status value={a.status} /></p>
    </div><button className="primary" disabled={!active} onClick={onQuote}>
      {a.status === 'Scheduled' ? 'Bidding not started' : active ? 'Submit a quote' : 'Bidding closed'}</button></div>
    <Stats items={[
      ['Current lowest quote', money(a.lowest_cents, a.currency), rankings.length ? `${rankings[0].carrier} · L1` : 'Be the first to bid'],
      ['Time remaining', active ? countdown(a.close_at, now) : a.status, `Closes ${dateTime(a.close_at)}`],
      ['Participating suppliers', a.suppliers, `${a.bid_count} quotes received`],
      ['Time extensions', a.extension_count, `Forced close ${dateTime(a.forced_close_at)}`],
    ]} />
    <div className="detail-grid"><div>
      <section className="panel"><div className="panel-heading"><div><h2>Supplier rankings</h2>
        <p className="muted">Latest quote from each supplier, lowest total first.</p></div><span className="count">{a.currency}</span></div>
        <div className="table-wrap">{rankings.length ? <table><thead><tr><th>RANK</th><th>SUPPLIER</th><th>TOTAL &amp; CHARGES</th><th>QUOTE DETAILS</th></tr></thead>
          <tbody>{rankings.map(q => <tr key={q.id}>
            <td><span className={`rank ${q.rank === 1 ? 'first' : ''}`}>L{q.rank}</span></td>
            <td><strong>{q.carrier}</strong><span className="meta">{dateTime(q.submitted_at)}</span></td>
            <td><span className="price">{money(q.total_cents, a.currency)}</span><span className="meta">Freight {money(q.freight_cents, a.currency)}<br />
              Origin {money(q.origin_cents, a.currency)} · Destination {money(q.destination_cents, a.currency)}</span></td>
            <td>{q.transit_days} days<span className="meta">Valid until {dateTime(q.valid_until)}</span></td>
          </tr>)}</tbody></table> : <Empty title="The competition is open">Supplier quotes will appear here.</Empty>}</div>
        <p className="rank-note">L1 is the lowest bidder. Total = freight + origin + destination charges.</p></section>
      <section className="panel below-panel"><div className="panel-heading"><div><h2>All submitted quotes</h2>
        <p className="muted">Complete price-sorted history, including earlier revisions.</p></div></div>
        <div className="table-wrap">{quotes.length ? <table className="history"><thead><tr>
          {['SUPPLIER', 'TOTAL', 'FREIGHT', 'ORIGIN', 'DESTINATION', 'TRANSIT', 'VALID UNTIL', 'SUBMITTED'].map(h => <th key={h}>{h}</th>)}
        </tr></thead><tbody>{quotes.map(q => <tr key={q.id} className={q.current ? '' : 'archived'}>
          <td>{q.carrier}<span className="meta">{q.current ? 'Current quote' : 'Superseded'}</span></td>
          {[q.total_cents, q.freight_cents, q.origin_cents, q.destination_cents].map((v, i) => <td key={i}>{money(v, a.currency)}</td>)}
          <td>{q.transit_days} days</td><td>{dateTime(q.valid_until)}</td><td>{dateTime(q.submitted_at)}</td>
        </tr>)}</tbody></table> : <Empty title="No quote history yet">Accepted quotes are recorded automatically.</Empty>}</div></section>
    </div><div className="detail-aside">
      <section className="panel"><h3>Auction configuration</h3>{info.map(([label, value]) =>
        <div className="info-row" key={label}><span>{label}</span><strong>{value}</strong></div>)}
        <p className="field-label">{a.british_enabled ? 'Enabled triggers' : 'Extensions disabled'}</p>
        <p className="muted">{a.british_enabled ? a.triggers.map(t => <React.Fragment key={t}>{triggerLabels[t]}<br /></React.Fragment>) : 'Fixed close time'}</p>
        {a.british_enabled && <p className="hint">Requires a new lowest price inside the trigger window. One extension per qualifying bid.</p>}
      </section>
      <section className="panel"><h3>Activity log <span className="count">{events.length}</span></h3>
        <ol className="timeline">{events.map(e => <li key={e.id}>
          <span className="event-tag">{e.kind === 'extension' ? 'TIME EXTENDED' : e.kind === 'bid' ? 'QUOTE RECEIVED' : 'AUCTION CREATED'}</span><br />
          {e.details.message}
          {e.kind === 'bid' && <><br /><strong>{money(e.details.total_cents, a.currency)}</strong></>}
          {e.kind === 'extension' && <div className="extension-note">{dateTime(e.details.old_close_at)} → {dateTime(e.details.new_close_at)}
            {e.details.capped && <><br />Forced close limit reached.</>}<br />
            Matched: {e.details.triggers.map(t => triggerLabels[t]).join(', ')}</div>}
          <span className="meta">{new Date(e.occurred_at).toLocaleString()}</span>
        </li>)}</ol></section>
    </div></div>
  </section>;
}
