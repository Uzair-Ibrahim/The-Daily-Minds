import { requestHeaders } from '../auth-client';
import React, { useEffect, useRef, useState } from 'react';

export function ArticleImage({ article, editionID, readerID, section, lead }) {
  const [picture, setPicture] = useState('');
  const [metadata, setMetadata] = useState(article);
  const [state, setState] = useState('loading');
  const [visible, setVisible] = useState(lead);
  const frame = useRef(null);
  useEffect(() => {
    if (lead || !window.IntersectionObserver) { setVisible(true); return; }
    const observer = new IntersectionObserver(entries => { if (entries.some(entry => entry.isIntersecting)) { setVisible(true); observer.disconnect(); } }, {rootMargin:'200px'});
    if (frame.current) observer.observe(frame.current);
    return () => observer.disconnect();
  }, [lead]);
  useEffect(() => {
    if (!visible) return;
    let active = true;
    let objectURL = '';
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 22000);
    setPicture(''); setState('loading');
    const path = `/api/editions/${encodeURIComponent(editionID)}/articles/${encodeURIComponent(article.id)}/image`;
    const options = {headers:requestHeaders(), signal:controller.signal};
    (async () => {
      try {
        const details = await fetch(path + '/metadata', options);
        if (!details.ok) throw new Error('Image metadata unavailable');
        const resolved = await details.json();
        if (!active) return;
        setMetadata({...article,...resolved});
        if (!resolved.image_url || resolved.image_status !== 'ready') throw new Error('Publisher image unavailable');
        const response = await fetch(path, options);
        if (!response.ok || response.status === 204 || !response.headers.get('content-type')?.startsWith('image/')) throw new Error('Image unavailable');
        const blob = await response.blob();
        if (!active) return;
        objectURL = URL.createObjectURL(blob); setPicture(objectURL);
      } catch { if (active) setState('missing'); }
      finally { clearTimeout(timer); }
    })();
    return () => { active=false; clearTimeout(timer); controller.abort(); if(objectURL) URL.revokeObjectURL(objectURL); };
  }, [visible, article.id, article.image_url, editionID, readerID]);
  return <figure ref={frame} className={`editorial-image ${lead ? 'editorial-image-lead' : 'editorial-image-secondary'} image-state-${state}`}>
    <div className={`editorial-image-frame ${state}`}>
      {picture && state !== 'missing' && <img src={picture} loading={lead ? 'eager' : 'lazy'} alt={metadata.image_alt || `Publisher-supplied image for: ${article.title}`} onLoad={() => setState('ready')} onError={() => setState('missing')}/>}
      {state !== 'ready' && <div className="section-image-placeholder" role="img" aria-label={`${section}: ${state === 'loading' ? 'image loading' : 'publisher image unavailable'}`}><span>{section}</span><small>{state === 'loading' ? 'Finding publisher photography...' : 'Text edition: No publisher photograph available'}</small></div>}
    </div>
    {state === 'ready' && <figcaption>{metadata.image_credit || 'Image via ' + article.source} | Publisher/source rights retained.</figcaption>}
  </figure>;
}
