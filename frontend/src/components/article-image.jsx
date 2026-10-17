import React, { useEffect, useState } from 'react';

export function ArticleImage({ article, editionID, readerID, section, lead }) {
  const [picture, setPicture] = useState('');
  const [state, setState] = useState(article.image_url ? 'loading' : 'missing');
  useEffect(() => {
    let active = true;
    let objectURL = '';
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 10000);
    setPicture('');
    setState(article.image_url ? 'loading' : 'missing');
    if (article.image_url) {
      fetch(`/api/editions/${encodeURIComponent(editionID)}/articles/${encodeURIComponent(article.id)}/image`, {
        headers: { 'X-Reader-ID': readerID }, signal: controller.signal,
      }).then(async response => {
        if (!response.ok || response.status === 204 || !response.headers.get('content-type')?.startsWith('image/')) throw new Error('Image unavailable');
        const blob = await response.blob();
        if (!active) return;
        objectURL = URL.createObjectURL(blob);
        setPicture(objectURL);
      }).catch(() => { if (active) setState('missing'); })
        .finally(() => clearTimeout(timer));
    }
    return () => { active = false; clearTimeout(timer); controller.abort(); if (objectURL) URL.revokeObjectURL(objectURL); };
  }, [article.id, article.image_url, editionID, readerID]);
  return <figure className={`editorial-image ${lead ? 'editorial-image-lead' : 'editorial-image-secondary'}`}>
    <div className={`editorial-image-frame ${state}`}>
      {picture && state !== 'missing' && <img src={picture} alt={`Publisher-supplied image for: ${article.title}`} onLoad={() => setState('ready')} onError={() => setState('missing')}/>}
      {state !== 'ready' && <div className="section-image-placeholder" role="img" aria-label={`${section}: ${state === 'loading' ? 'image loading' : 'publisher image unavailable'}`}><span className="placeholder-rule"/><span>{section}</span><em>In focus</em><small>{state === 'loading' ? 'Loading publisher image…' : 'Publisher image unavailable'}</small></div>}
    </div>
    <figcaption>{state === 'ready' ? `${article.image_credit || 'Image via ' + article.source} · Publisher/source rights retained.` : 'Section treatment · No substitute photograph'}</figcaption>
  </figure>;
}
