import React, { useRef, useState } from 'react';
import { Heart, Bookmark, Share2, X } from 'lucide-react';
import { shareLinks } from './share-links';


export function ArticleEngagement({ article, liked, saved, disabled, onAction, notify }) {
  const [sharing, setSharing] = useState(false);
  const [manual, setManual] = useState(false);
  const [working, setWorking] = useState(false);
  const trigger = useRef(null);
  const menu = useRef(null);
  const links = shareLinks(article);
  function close() { setSharing(false); trigger.current?.focus(); }
  async function copy() {
    try {
      if (!navigator.clipboard?.writeText) throw new Error('Clipboard unavailable');
      await navigator.clipboard.writeText(article.url);
      notify('Source link copied.'); close();
    } catch { setManual(true); notify('Select and copy the original source link below.'); }
  }
  async function nativeShare() {
    if (!navigator.share) { setManual(true); notify('Native sharing is unavailable. Use a share option or copy the source link.'); return; }
    setWorking(true);
    try { await navigator.share({ title: article.title, text: article.title, url: article.url }); notify('Source shared.'); close(); }
    catch (error) { if (error.name === 'AbortError') notify('Sharing cancelled.'); else { setManual(true); notify('Sharing unavailable. Copy the source link instead.', 'error'); } }
    finally { setWorking(false); }
  }
  function keys(event) {
    if (event.key === 'Escape') { event.preventDefault(); close(); }
    if (['ArrowDown','ArrowUp','Home','End'].includes(event.key)) {
      event.preventDefault();
      const items = [...menu.current.querySelectorAll('button:not(:disabled), a')];
      let index = items.indexOf(document.activeElement);
      index = event.key === 'Home' ? 0 : event.key === 'End' ? items.length - 1 : (index + (event.key === 'ArrowDown' ? 1 : -1) + items.length) % items.length;
      items[index]?.focus();
    }
  }
  return <div className="engagement-cluster">
    <div className="article-actions">
      <button className={liked ? 'selected-action' : ''} aria-label={(liked ? 'Unlike ' : 'Like ') + article.title} aria-pressed={!!liked} disabled={disabled} onClick={() => onAction(article, 'liked')} title="Your local reader's like"><Heart size={16} fill={liked ? 'currentColor' : 'none'}/><span className="local-like-count" aria-label="Your active like count">{liked ? 1 : 0}</span></button>
      <button className={saved ? 'selected-action' : ''} aria-label={(saved ? 'Unsave ' : 'Save ') + article.title} aria-pressed={!!saved} disabled={disabled} onClick={() => onAction(article, 'saved')}><Bookmark size={16} fill={saved ? 'currentColor' : 'none'}/></button>
      <button aria-label={'Skip ' + article.title} disabled={disabled} onClick={() => onAction(article, 'skipped')}><X size={17}/></button>
      <button ref={trigger} disabled={!links} aria-label={'Share ' + article.title} aria-expanded={sharing} aria-controls={'share-' + article.id} onClick={() => { setSharing(value => !value); setManual(false); notify('Choose how to share the original source.'); }}><Share2 size={16}/></button>
    </div>
    <small className="like-scope">YOUR LOCAL LIKE · {liked ? 1 : 0}</small>
    {sharing && <div ref={menu} id={'share-' + article.id} className="share-menu" role="group" aria-label="Share original news source" onKeyDown={keys}>
      <b>Share the original story</b>
      {Object.entries(links || {}).map(([name,url]) => <a key={name} href={url} target="_blank" rel="noopener noreferrer" onClick={() => notify(name + ' sharing opened.')}>{name}</a>)}
      <button onClick={copy}>Copy link</button>
      <button disabled={working} onClick={nativeShare}>{working ? 'Opening sharing…' : 'Share from this device'}</button>
      {manual && <label className="manual-copy">Original source link<input readOnly value={article.url} aria-label="Original source link" onFocus={event => event.target.select()}/></label>}
      <button onClick={close}>Close share menu</button>
    </div>}
  </div>;
}
