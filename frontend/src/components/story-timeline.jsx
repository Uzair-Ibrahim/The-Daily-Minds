import React, { useState } from 'react';

export function StoryTimeline({ storyID, api }) {
  const [story, setStory] = useState(null);
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  async function load() {
    setOpen(true); setBusy(true); setError('');
    try { setStory(await api('/stories/' + storyID)); }
    catch (e) { setError(e.message); }
    finally { setBusy(false); }
  }
  async function follow() {
    setBusy(true); setError('');
    try { setStory(await api('/stories/' + storyID + '/follow', { method: 'PUT', body: JSON.stringify({ followed: !story.followed }) })); }
    catch (e) { setError(e.message); }
    finally { setBusy(false); }
  }
  return <section className="story-memory" aria-label="Living story">
    <button className="story-toggle" aria-expanded={open} onClick={() => open ? setOpen(false) : load()}>Living story · {open ? 'Close timeline' : 'Explore timeline'}</button>
    {open && <div aria-live="polite">
      {busy && <p>Opening story memory…</p>}
      {error && <p role="alert">{error} <button disabled={busy} onClick={load}>Retry</button></p>}
      {story && <>
        <p className="story-caution">{story.limitation} Showing up to 150 observations.</p>
        <button className="story-toggle" disabled={busy} aria-pressed={story.followed} onClick={follow}>{story.followed ? 'Unfollow this story' : 'Follow this story'}</button>
        <p className="story-caution">Following gives new coverage a small priority boost in future editions.</p>
        {!story.timeline.length ? <p>No source observations available.</p> : <ol className="story-timeline">{story.timeline.map((event, i) => <Observation key={event.article_id + ':' + i} event={event}/>)}</ol>}
      </>}
    </div>}
  </section>;
}

function Observation({ event }) {
  return <li>
    <a href={event.url} target="_blank" rel="noopener noreferrer">{event.title}</a>
    <p>{event.source} · Published: {event.published_at || 'Unknown'}<br/>Observed: {event.observed_at}</p>
    <blockquote>{event.description || 'No source excerpt supplied.'}</blockquote>
    <p>{event.change}</p>
    <details><summary>Why these articles are connected</summary><ul>{event.signals.map(signal => <li key={signal}>{signal}</li>)}</ul></details>
  </li>;
}

export function ContinuingStories({ edition }) {
  const stories = edition.continuing_stories || [];
  const updates = edition.story_updates?.stories || [];
  if (!stories.length && !updates.length) return null;
  return <section className="continuing-stories" aria-label="Continuing stories">
    {updates.length > 0 && <><h2>Since your last edition</h2><p>Newly observed coverage in stories you follow. Older publications may have been retrieved later.</p><ul>{updates.map(story => <li key={story.id}>{story.title} · {story.timeline.length} new source observation(s)</li>)}</ul></>}
    {stories.length > 0 && <><span className="eyebrow">THE CONTINUING STORIES</span><h2>The story so far.</h2><p>Saved with this edition. Connections are possible relationships, not independent verification.</p>{stories.map(story => <section key={story.id}><h3>{story.title}</h3><ol className="story-timeline">{story.timeline.map((event, i) => <Observation key={i} event={event}/>)}</ol></section>)}</>}
  </section>;
}
