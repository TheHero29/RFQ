import React, { useEffect, useState } from 'react';
import { api } from './api';
import Listing from './components/AuctionList';
import AuctionDetail from './components/AuctionDetail';
import { Dialog, CreateForm, QuoteForm } from './components/Dialogs';
import { Empty } from './components/ui';

const routeId = () => Number(location.hash.match(/^#rfq\/(\d+)$/)?.[1]) || null;

export default function App() {
  const [id, setId] = useState(routeId);
  const [data, setData] = useState(null);
  const [modal, setModal] = useState(null);
  const [notice, setNotice] = useState(null);
  const [refreshKey, setRefreshKey] = useState(0);
  const [clock, setClock] = useState(Date.now());
  const [offset, setOffset] = useState(0);
  const now = clock + offset;

  useEffect(() => {
    const navigate = () => { setId(routeId()); setData(null); setModal(null); setNotice(null); };
    window.addEventListener('hashchange', navigate);
    const timer = setInterval(() => setClock(Date.now()), 1000);
    return () => { window.removeEventListener('hashchange', navigate); clearInterval(timer); };
  }, []);

  useEffect(() => {
    let cancelled = false, pending = false;
    async function load() {
      if (pending) return;
      pending = true;
      try {
        const result = await api(id ? `/api/rfqs/${id}` : '/api/rfqs');
        if (!cancelled) { setData(result); setOffset(new Date(result.server_time).getTime() - Date.now()); }
      } catch (e) { if (!cancelled) setNotice({ text: e.message, error: true }); }
      finally { pending = false; }
    }
    load();
    const timer = setInterval(() => { if (!document.hidden) load(); }, 5000);
    return () => { cancelled = true; clearInterval(timer); };
  }, [id, refreshKey]);

  function quoteSaved(extended) {
    setModal(null); setRefreshKey(k => k + 1);
    setNotice({ text: extended ? 'Quote accepted. The auction close time was extended.' : 'Quote accepted. Supplier rankings updated.' });
  }
  return <>
    <aside className="sidebar"><a className="brand" href="#"><span className="brand-mark">b.</span>
      <span>british<span className="brand-sub">RFQ WORKSPACE</span></span></a>
      <div className="nav-label">WORKSPACE</div><a className="nav-item active" href="#"><span aria-hidden="true">▦</span>Auctions</a>
      <button className="nav-item" onClick={() => setModal('help')}><span aria-hidden="true">ⓘ</span>How bidding works</button>
      <div className="sidebar-bottom"><span className="small-label">BETTER BIDS. FAIRER OUTCOMES.</span><p>A clear view of every quote, every rank, every extension.</p></div>
    </aside>
    <main><header className="topbar"><span>Procurement / <strong>Auctions</strong></span><span className="workspace-badge">Buyer workspace</span></header>
      <div className="page">{notice && <div className={`notice ${notice.error ? 'error' : ''}`} role="status">{notice.text}</div>}
        {!data ? <Empty title="Loading auctions…">{id && <a href="#">Back to auctions</a>}</Empty> : id ?
          <AuctionDetail data={data} now={now} onQuote={() => setModal('quote')} /> :
          <Listing auctions={data.rfqs} now={now} onCreate={() => setModal('create')} />}
      </div>
    </main>
    {modal === 'create' && <CreateForm now={now} onClose={() => setModal(null)} onSaved={newId => { setModal(null); location.hash = `rfq/${newId}`; }} />}
    {modal === 'quote' && data?.rfq && <QuoteForm auction={data.rfq} now={now} onClose={() => setModal(null)} onSaved={quoteSaved} />}
    {modal === 'help' && <Dialog title="How bidding works" onClose={() => setModal(null)}><div className="help-copy">
      <p><strong>L1 is the lowest-priced supplier.</strong> L2 is second lowest, and so on. Your latest quote determines your position; older quotes stay in the history.</p>
      <p>You can enter a quote without beating L1, but a revision must lower your own total. No two suppliers can hold equal current totals.</p>
      <p>British Auctions extend only when a new bid beats the previous auction best price, falls within the trigger window, and matches a selected trigger. Multiple matches add just one extension.</p>
      <p>Each qualifying bid can extend the updated close time again. Bidding stops at the current close time and can never continue beyond forced close.</p>
      <p>An auction that reaches its forced deadline is “Force Closed”. An auction that ends earlier stays “Closed”.</p>
    </div></Dialog>}
  </>;
}
