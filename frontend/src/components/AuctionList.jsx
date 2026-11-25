import React, { useState } from 'react';
import { money, dateTime, countdown } from '../format';
import { Status, Empty, Stats } from './ui';

export default function Listing({ auctions, now, onCreate }) {
  const [search, setSearch] = useState('');
  const [status, setStatus] = useState('');
  const visible = auctions.filter(a => `${a.name} ${a.reference}`.toLowerCase().includes(search.trim().toLowerCase()) &&
    (!status || a.status === status));
  const sum = key => auctions.reduce((n, a) => n + a[key], 0);
  return <section>
    <div className="page-heading"><div><p className="eyebrow">BRITISH AUCTIONS</p>
      <h1>Make every bid count.</h1><p className="muted">Manage your RFQs and follow the competition as it happens.</p>
    </div><button className="primary" onClick={onCreate}>+ Create RFQ</button></div>
    <Stats items={[
      ['Active auctions', auctions.filter(a => a.status === 'Active').length, 'Open for supplier quotes'],
      ['Total RFQs', auctions.length, 'Across your workspace'],
      ['Quotes received', sum('bid_count'), 'Including supplier revisions'],
      ['Time extensions', sum('extension_count'), 'More time for better prices'],
    ]} />
    <section className="panel"><div className="panel-heading"><div>
      <h2>Auction overview <span className="count">{visible.length}</span></h2>
      <p className="muted">Live prices, clear deadlines, complete visibility.</p></div>
      <div className="filters"><label className="sr-only" htmlFor="search">Search auctions</label>
        <input id="search" type="search" value={search} onChange={e => setSearch(e.target.value)} placeholder="Search name or reference…" />
        <label className="sr-only" htmlFor="status-filter">Filter status</label>
        <select id="status-filter" value={status} onChange={e => setStatus(e.target.value)}>
          <option value="">All statuses</option>{['Active', 'Scheduled', 'Closed', 'Force Closed'].map(s => <option key={s}>{s}</option>)}
        </select></div></div>
      <div className="table-wrap">{visible.length ? <table><thead><tr>
        <th>RFQ / REFERENCE</th><th>LOWEST QUOTE</th><th>BID CLOSE</th><th>FORCED CLOSE</th><th>STATUS</th><th><span className="sr-only">Actions</span></th>
      </tr></thead><tbody>{visible.map(a => <tr key={a.id}>
        <td><span className="table-name">{a.name}</span><span className="meta">{a.reference} · {a.british_enabled ? 'British Auction' : 'Standard RFQ'}</span></td>
        <td><span className="price">{money(a.lowest_cents, a.currency)}</span><span className="meta">{a.suppliers} suppliers · {a.bid_count} bids</span></td>
        <td>{dateTime(a.close_at)}<span className="meta">{a.status === 'Active' ? countdown(a.close_at, now) : `${a.extension_count} extension(s)`}</span></td>
        <td>{dateTime(a.forced_close_at)}<span className="meta">Hard deadline</span></td>
        <td><Status value={a.status} /></td><td><a className="row-link" href={`#rfq/${a.id}`} aria-label={`View ${a.reference}`}>View details</a></td>
      </tr>)}</tbody></table> : <Empty title={auctions.length ? 'No matching auctions' : 'Your first auction starts here'}>
        {auctions.length ? 'Try a different search or status.' : 'Create an RFQ to invite your first supplier quote.'}</Empty>}</div>
    </section>
    <div className="footnote"><span className="live-dot" />Refreshes every 5 seconds<span>All times shown in your device timezone.</span></div>
  </section>;
}
