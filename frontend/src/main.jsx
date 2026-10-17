import React, { useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { ArrowUpRight, ArrowRight, ArrowLeft, Bookmark, Heart, X, Check, Download, RefreshCw, Sparkles, Newspaper, SlidersHorizontal, Archive, Globe2, Cpu, FlaskConical, Landmark, Trophy, Palette, MapPin, LoaderCircle, RotateCcw, ChevronRight, Info } from 'lucide-react';
import { Button } from './components/ui/button';
import { EditorialMemory } from './components/editorial-memory';
import { ArticleImage } from './components/article-image';
import './styles.css';

function identity() {
  try {
    const current = localStorage.getItem('daily-mind-reader');
    if (current) return current;
    const id = crypto.randomUUID();
    localStorage.setItem('daily-mind-reader', id);
    return id;
  } catch { return crypto.randomUUID(); }
}
const readerID = identity();
const icons = { technology: Cpu, world: Globe2, pakistan: MapPin, business: Landmark, science: FlaskConical, sports: Trophy, culture: Palette };
const labels = { technology: 'Technology & AI', world: 'World affairs', pakistan: 'Pakistan', business: 'Business & economy', science: 'Science & discovery', sports: 'Sport', culture: 'Culture & ideas' };
async function api(path, options = {}) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 85000);
  try {
    const response = await fetch('/api' + path, { ...options, signal: controller.signal, headers: { 'Content-Type': 'application/json', 'X-Reader-ID': readerID, ...options.headers } });
    if (!response.ok) {
      let error = null;
      try { error = await response.json(); } catch {}
      const detail = error?.detail;
      throw new Error(typeof detail === 'string' ? detail : detail?.message || `Service unavailable (${response.status}). Please try again.`);
    }
    return options.blob ? response.blob() : response.json();
  } catch (error) {
    if (error.name === 'AbortError') throw new Error('This took too long. Your saved editions are safe. Please retry.');
    if (error instanceof TypeError) throw new Error('Cannot reach The Daily Mind. Check that the local server is running.');
    throw error;
  } finally { clearTimeout(timer); }
}
const post = (path, body = {}) => api(path, { method: 'POST', body: JSON.stringify(body) });
const displayDate = (date, long = false) => new Date(date + 'T12:00:00').toLocaleDateString('en-GB', { weekday: long ? 'long' : 'short', day: 'numeric', month: long ? 'long' : 'short', year: 'numeric' });

function App() {
  const [profile, setProfile] = useState(null);
  const [edition, setEdition] = useState(null);
  const [archive, setArchive] = useState([]);
  const [dna, setDna] = useState([]);
  const [view, setView] = useState('paper');
  const [editing, setEditing] = useState(false);
  const [initializing, setInitializing] = useState(true);
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');
  const [toast, setToast] = useState(null);
  const [actions, setActions] = useState({});
  const [hidden, setHidden] = useState({});
  function notify(message, kind = 'success') { setToast({ message, kind }); }
  useEffect(() => { if (!toast) return; const timer = setTimeout(() => setToast(null), 5000); return () => clearTimeout(timer); }, [toast]);
  useEffect(() => {
    if (dna.length && dna.every(item => item.events === 0)) { setActions({}); setHidden({}); }
  }, [dna]);
  async function run(label, task) {
    setBusy(label); setError('');
    try { return await task(); }
    catch (e) { setError(e.message); notify(e.message, 'error'); }
    finally { setBusy(''); }
  }
  async function refreshData() {
    const [past, interests] = await Promise.all([api('/editions'), api('/profile/interests')]);
    setArchive(past); setDna(interests.weights);
    return past;
  }
  function showEdition(value) {
    setEdition(value); setHidden({});
    const recorded = {};
    for (const event of value.reader_actions || []) recorded[event.article_id + ':' + event.action] = true;
    setActions(recorded); setView('paper');
  }
  async function initialize() {
    setInitializing(true); setError('');
    try {
      const person = await api('/profile'); setProfile(person);
      const past = await refreshData();
      if (past.length) showEdition(await api('/editions/' + past[0].id));
      if (person.onboarded) {
        const today = new Intl.DateTimeFormat('en-CA', {timeZone: person.timezone, year:'numeric', month:'2-digit', day:'2-digit'}).format(new Date());
        if (!past.length || past[0].local_date !== today) {
          const current = await post('/editions/generate');
          showEdition(await api('/editions/' + current.id));
          await refreshData();
          notify(current.status === 'offline_fallback' ? 'Offline paper ready from previously retrieved sources.' : 'Your daily paper is ready.');
        }
      }
    } catch (e) { setError(e.message); }
    finally { setInitializing(false); }
  }
  useEffect(() => { initialize(); }, []);
  async function generate(regenerate = false) {
    return run('edition', async () => {
      const value = await post('/editions/generate', { regenerate });
      showEdition(await api('/editions/' + value.id));
      await refreshData();
      notify(regenerate ? `Edition ${value.version} is ready. Previous versions are in your archive.` : 'Your personal paper is ready.');
    });
  }
  async function savePreferences(input) {
    await run('preferences', async () => {
      const person = await api('/profile', { method: 'PUT', body: JSON.stringify(input) });
      setProfile(person); setEditing(false); await refreshData();
      notify('Preferences saved. Your next edition will reflect these interests.');
      if (!edition) {
        setBusy('edition');
        const value = await post('/editions/generate'); showEdition(value); await refreshData();
        notify('Welcome to your first edition.');
      } else setView('dna');
    });
  }
  async function interact(article, action) {
    const key = article.id + ':' + action;
    if (actions[key]) return;
    await run('interaction:' + key, async () => {
      const result = await post('/articles/' + article.id + '/interactions', { action });
      setActions(previous => ({ ...previous, [key]: true })); setDna(result.weights);
      if (action === 'skipped' || action === 'not_interested') setHidden(previous => ({ ...previous, [article.id]: true }));
      const messages = { liked: 'Liked. Related topics get a little more weight next time.', saved: 'Saved. This story stays in your archive.', skipped: 'Skipped. This story gets less priority next time.', not_interested: 'Preference recorded. We will dial down related topics.', opened: 'Opened source. This is a click signal, not a completed read.' };
      notify(messages[action]);
    });
  }
  async function downloadPDF() {
    await run('pdf', async () => {
      const blob = await api('/editions/' + edition.id + '/pdf', { blob: true });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement('a'); anchor.href = url; anchor.download = `daily-mind-${edition.local_date}-v${edition.version}.pdf`; anchor.click();
      setTimeout(() => URL.revokeObjectURL(url), 10000);
      notify('Your PDF is ready. Download started.');
    });
  }
  const selectedTopics = Object.keys(profile?.topics || {});
  const onboarding = profile && (!profile.onboarded || editing);
  return <div className="app-shell">
    <div className="top-strip"><span>A LITTLE LESS NOISE. A LITTLE MORE PERSPECTIVE.</span><span><span className="status-dot"/>YOUR PRIVATE, LOCAL EDITION</span></div>
    <header className="site-header"><button className="wordmark" onClick={() => { setView('paper'); setEditing(false); notify('Your paper.'); }} aria-label="The Daily Mind home">The Daily Mind<span>.</span></button>
      {profile?.onboarded && !editing && <nav aria-label="Main navigation">{[['paper', 'Your paper', Newspaper], ['archive', 'The archive', Archive], ['dna', 'Interest DNA', Sparkles]].map(([id, label, Icon]) => <button key={id} className={view === id ? 'nav-active' : ''} onClick={() => { setView(id); notify(label + ' opened.'); }}><Icon size={15}/>{label}</button>)}</nav>}
      <div className="header-end"><span className="small-caps">MADE FOR YOUR MIND</span><div className="avatar">M<span/></div></div>
    </header>
    {initializing ? <main className="page"><div className="initial-loading"><LoaderCircle className="spin"/><p>Opening your reading room…</p></div></main> : !profile ? <main className="page"><div className="empty-state"><Newspaper size={44}/><h1>Your reading room is offline.</h1><p>{error}</p><Button onClick={initialize}>Retry connection <RefreshCw size={16}/></Button></div></main> : onboarding ?
      <Onboarding profile={profile} saving={!!busy} onSave={savePreferences} onCancel={editing ? () => { setEditing(false); notify('Preferences editor closed.'); } : null} notify={notify}/> : <main className="page">
      {error && <div className="error-banner" role="alert"><Info size={18}/><span>{error}</span><button onClick={() => setError('')} aria-label="Dismiss error"><X size={16}/></button></div>}
      {view === 'paper' && <>
        <section className="welcome"><div><div className="eyebrow"><span className="mini-rule"/>THE PERSONAL EDITION</div><h1>A wider world.<br/><em>A clearer mind.</em></h1><p>Your interests, thoughtfully gathered into one good read.</p></div><div className="welcome-right"><div className="edition-stamp"><Newspaper size={25}/><span>CURATED BY YOUR CURIOSITY<br/><b>READ AT YOUR OWN PACE</b></span></div><Button disabled={!!busy} onClick={() => generate(!!edition)}>{busy === 'edition' ? <LoaderCircle size={16} className="spin"/> : <RefreshCw size={16}/>} {busy === 'edition' ? 'Preparing your edition…' : edition ? 'Make a new edition' : 'Make my first edition'}</Button></div></section>
        {busy === 'edition' ? <div className="loading-paper" aria-live="polite"><div className="loading-caption"><LoaderCircle size={17} className="spin"/>Gathering public feeds and arranging your edition. No invented stories.</div><div className="skeleton big"/><div className="skeleton-grid">{[1, 2, 3].map(i => <div className="skeleton" key={i}/>)}</div></div> : edition ? <>
          <div className="paper-toolbar"><div className="topic-pills">{selectedTopics.map(topic => <span key={topic}>{labels[topic]}</span>)}</div><Button variant="outline" disabled={!!busy} onClick={downloadPDF}>{busy === 'pdf' ? <LoaderCircle className="spin" size={15}/> : <Download size={15}/>} {busy === 'pdf' ? 'Printing your paper…' : 'Download PDF'}</Button></div>
          <section className="newspaper" aria-label="Your saved newspaper edition">
            {edition.status === 'offline_fallback' && <div className="error-banner" role="note"><Info size={18}/><span><strong>Offline edition — previously retrieved content, not fresh news.</strong> Sources retrieved {new Date(edition.source_retrieved_from).toLocaleString('en-GB')} to {new Date(edition.source_retrieved_to).toLocaleString('en-GB')}. The edition date records assembly, not publication.</span></div>}
            <div className="masthead-top"><span>VOL. {String(edition.version).padStart(2, '0')}</span><span>AN EDITION AS INDIVIDUAL AS YOU ARE</span><span>{edition.article_count} STORIES</span></div>
            <h2 className="masthead">The Daily Mind<span>.</span></h2><div className="paper-dateline"><span>{displayDate(edition.local_date, true)}</span><span>{edition.source_count} distinct publishers · {edition.timezone}</span><span>{edition.status === 'offline_fallback' ? 'OFFLINE / PREVIOUSLY RETRIEVED' : edition.status === 'cached_sources' ? 'CACHED RSS AT GENERATION' : 'RSS · SAVED SNAPSHOT'}</span></div>
            <div className="paper-intro"><span className="eyebrow">THIS EDITION’S READING LIST</span><span>Selected for {Object.keys(edition.profile_snapshot.topics).slice(0, 3).map(t => labels[t]).join(', ')}</span></div>
            <div className="articles-grid">{edition.articles.map((article, index) => hidden[article.id] ? <div className="skipped-card" key={article.id}><Check size={18}/><p>Story skipped.<br/><span>Your next paper will learn from this.</span></p><button onClick={() => { setHidden(prev => ({ ...prev, [article.id]: false })); notify('Story shown again. Your feedback is still recorded.'); }}>Show story</button></div> : <ArticleCard key={article.id} editionID={edition.id} article={article} index={index} actions={actions} disabled={!!busy} onAction={interact}/>)}</div>
            <EditorialMemory edition={edition}/>
            <div className="edition-notes"><Info size={15}/><p><strong>A note on your sources.</strong> These are attributed publisher excerpts, not AI-written reporting. Edition generated {new Date(edition.generated_at).toLocaleString('en-GB')}. Original retrieval times appear under “Why this story?”. Publication dates appear when provided; retrieval does not mean a story was published today. {edition.warnings.filter(w => !w.startsWith('Attributed')).join(' ')}</p></div>
          </section><div className="feedback-nudge"><Sparkles size={22}/><div><strong>Your next edition starts here.</strong><p>A like, save or skip helps shape tomorrow’s paper. See exactly how.</p></div><button onClick={() => { setView('dna'); notify('Your explainable Interest DNA opened.'); }}>Explore your Interest DNA <ArrowRight size={16}/></button></div>
        </> : <div className="empty-state"><Newspaper size={48}/><h2>Your first edition is waiting.</h2><p>We’ll gather real public news feeds and build a paper around your interests.<br/>No account. No paid APIs. Just a more thoughtful read.</p><Button disabled={!!busy} onClick={() => generate()}>Create my paper <ArrowRight size={17}/></Button>{archive.length > 0 && <button className="text-button" onClick={() => { setView('archive'); notify('Saved editions opened.'); }}>Read a saved edition instead</button>}</div>}
      </>}
      {view === 'archive' && <><SectionTitle eyebrow="YOUR PERSONAL LIBRARY" title="Good reads don’t expire." description="Every saved edition, exactly as it was. A new version never overwrites the old."/><div className="archive-grid">{archive.length ? archive.map((item, index) => <button className="archive-card" key={item.id} disabled={!!busy} onClick={() => run('archive', async () => { showEdition(await api('/editions/' + item.id)); notify('Saved edition opened without retrieving new stories.'); })}><div className="archive-preview"><div className="archive-mini-title">The Daily Mind.</div><div className="mini-lines"/><h3>{displayDate(item.local_date)}</h3><div className="mini-columns"><span/><span/><span/></div></div><div className="archive-meta"><span className="eyebrow">{index === 0 ? 'LATEST SAVED EDITION' : 'SAVED EDITION'}</span><h3>{displayDate(item.local_date)}</h3><p>Version {item.version} · {item.article_count} stories</p><span className="archive-open">Open this paper <ArrowUpRight size={16}/></span></div></button>) : <div className="empty-state"><Archive size={40}/><h2>A library starts with one paper.</h2><p>Generate your first edition to begin your archive.</p><Button onClick={() => generate()}>Create an edition</Button></div>}</div></>}
      {view === 'dna' && <><SectionTitle eyebrow="ADAPTIVE INTEREST DNA" title="A paper that grows with you." description="No hidden profiling. Your choices and a few bounded signals shape what comes next."/><div className="dna-layout"><section className="dna-panel"><div className="panel-heading"><h2>Your curiosity, mapped.</h2><span className="live-label">{dna.reduce((n, row) => n + row.events, 0)} topic signals</span></div><p className="muted">The pale bar is your chosen interest. Green shows its current weight after real feedback.</p>{dna.map(item => <div className="dna-row" key={item.topic}><div><span>{item.label}</span><span>{item.weight.toFixed(2)} <small>{item.feedback > 0 ? '+' : ''}{item.feedback.toFixed(2)} from feedback</small></span></div><div className="dna-track"><div className="dna-base" style={{width: `${item.base / 3 * 100}%`}}/><div className="dna-current" style={{width: `${item.weight / 3 * 100}%`}}/></div></div>)}<div className="dna-actions"><Button variant="outline" disabled={!!busy} onClick={() => { setEditing(true); notify('Edit your interests.'); }}><SlidersHorizontal size={15}/>Edit preferences</Button><Button variant="ghost" disabled={!!busy} onClick={() => run('reset', async () => { const result = await post('/profile/reset-feedback'); setDna(result.weights); notify('Feedback reset. Saved editions are unchanged.'); })}><RotateCcw size={15}/>Reset feedback</Button></div></section><aside className="dna-explainer"><Sparkles size={26}/><h2>Small signals.<br/>A more personal paper.</h2><p>Likes and saves gently raise topic weights. Skips reduce them. Opening a source is only a small click signal—not proof you read it.</p><div className="signal-list"><span><Heart size={15}/>Like <b>+0.35</b></span><span><Bookmark size={15}/>Save <b>+0.25</b></span><span><X size={15}/>Skip <b>−0.20</b></span></div><p className="tiny">Signals are shared across a story’s topics and capped at ±1 per topic. Ranking also considers known recency, publisher diversity and repetition. These are explainable heuristics, not confidence scores.</p><Button disabled={!!busy} onClick={() => generate(true)}>See it in your next edition <ArrowRight size={16}/></Button></aside></div></>}
    </main>}
    <footer className="site-footer"><span className="footer-brand">The Daily Mind<span>.</span></span><span>Your newspaper. Your curiosity. Your evolving intelligence.</span><span>LESS SCROLLING. MORE UNDERSTANDING.</span></footer>
    {toast && <div className={'toast ' + toast.kind} role="status">{toast.kind === 'error' ? <Info size={18}/> : <Check size={18}/>}<span>{toast.message}</span><button onClick={() => setToast(null)} aria-label="Dismiss notification"><X size={15}/></button></div>}
  </div>;
}

function SectionTitle({ eyebrow, title, description }) { return <section className="section-title"><div className="eyebrow"><span className="mini-rule"/>{eyebrow}</div><h1>{title}</h1><p>{description}</p></section>; }

function ArticleCard({article, index, actions, disabled, onAction, editionID}) {
  const liked = actions[article.id + ':liked']; const saved = actions[article.id + ':saved'];
  const date = article.published_at ? new Date(article.published_at) : null;
  const older = date && Date.now() - date.getTime() > 72 * 3600000;
  const viaGoogle = new URL(article.url).hostname === 'news.google.com';
  return <article className={'article-card article-' + index}>
    <div className="article-kicker"><span>{labels[article.topics[0]] || 'World affairs'}</span><span>{String(index + 1).padStart(2, '0')}</span></div>
    <h3><a href={article.url} target="_blank" rel="noopener noreferrer" onClick={() => onAction(article, 'opened')}>{article.title}</a></h3>
    <div className="byline"><span className="source-dot"/>{article.source}<span>·</span><span>{date ? date.toLocaleDateString('en-GB', {day:'numeric',month:'short'}) + (older ? ' · Older coverage' : '') : 'Publication date unknown'}</span></div>
    {index < 3 && <ArticleImage article={article} editionID={editionID} readerID={readerID} section={labels[article.topics[0]] || 'World affairs'} lead={index === 0}/>}
    <p className="article-description">{article.description || 'No feed description supplied. Follow the original source for the full report.'}</p>
    <span className="excerpt-label">{viaGoogle ? 'GOOGLE NEWS RSS · PUBLISHER-LABELED HEADLINE / EXCERPT' : 'ATTRIBUTED PUBLISHER EXCERPT'}</span>
    <div className="article-bottom"><a className="read-source" href={article.url} target="_blank" rel="noopener noreferrer" onClick={() => onAction(article, 'opened')}>{viaGoogle ? 'Open via Google News' : 'Read original'} <ArrowUpRight size={15}/></a><div className="article-actions"><button className={liked ? 'selected-action' : ''} aria-label={'Like ' + article.title} disabled={disabled || liked} onClick={() => onAction(article, 'liked')} title="More like this"><Heart size={16} fill={liked ? 'currentColor' : 'none'}/></button><button className={saved ? 'selected-action' : ''} aria-label={'Save ' + article.title} disabled={disabled || saved} onClick={() => onAction(article, 'saved')} title="Save this story"><Bookmark size={16} fill={saved ? 'currentColor' : 'none'}/></button><button aria-label={'Skip ' + article.title} disabled={disabled} onClick={() => onAction(article, 'skipped')} title="Skip this story"><X size={17}/></button></div></div>
    <details className="ranking-details"><summary>Why this story? <Sparkles size={12}/></summary><p>{article.reasons.join('. ')}.</p><div className="breakdown">{Object.entries(article.breakdown).map(([key,value]) => <span key={key}>{key.replaceAll('_',' ')} <b>{value > 0 ? '+' : ''}{value}</b></span>)}</div><p>Priority points are ranking heuristics, not confidence. Retrieved {new Date(article.retrieved_at).toLocaleString('en-GB')}.</p><button disabled={disabled || actions[article.id + ':not_interested']} onClick={() => onAction(article, 'not_interested')}>Not interested in this topic</button></details>
  </article>;
}

function Onboarding({ profile, saving, onSave, onCancel, notify }) {
  const [step, setStep] = useState(1);
  const [topics, setTopics] = useState(Object.keys(profile.topics));
  const [keywords, setKeywords] = useState(profile.keywords.join(', '));
  const [depth, setDepth] = useState(profile.depth);
  const [locale, setLocale] = useState(profile.locale);
  const [length, setLength] = useState(profile.edition_length);
  const [timezone, setTimezone] = useState(profile.timezone);
  function toggle(topic) { setTopics(current => current.includes(topic) ? current.filter(id => id !== topic) : [...current, topic]); notify(labels[topic] + ' preference updated.'); }
  function submit(event) { event.preventDefault(); onSave({ topics: Object.fromEntries(topics.map(topic => [topic, profile.topics[topic] || 1])), keywords: keywords.split(',').map(word => word.trim()).filter(Boolean), locale, depth, edition_length: Number(length), timezone, language:'en', onboarded:true }); }
  return <main className="onboarding-page"><aside className="onboarding-story"><span className="eyebrow">A BETTER KIND OF MORNING</span><div><div className="onboarding-sun"><span/><span/><span/></div><h1>The world is full<br/>of stories.<br/><em>Find your thread.</em></h1><p>A personal newspaper for the things that spark your curiosity. A little less noise. A little more you.</p></div><div className="onboarding-foot"><Newspaper size={22}/><span>REAL SOURCES. YOUR PERSPECTIVE.<br/>A NEW READING RITUAL.</span></div></aside><section className="onboarding-form"><div className="step-indicator"><span className={step === 1 ? 'active' : 'complete'}>01 <span>YOUR INTERESTS</span></span><i/><span className={step === 2 ? 'active' : ''}>02 <span>YOUR RITUAL</span></span></div><form onSubmit={submit}>{step === 1 ? <><span className="eyebrow">LET’S MAKE THIS PERSONAL</span><h2>What opens<br/><em>your mind?</em></h2><p className="form-description">Pick the worlds you want to explore.<br/>Your paper will evolve as you read.</p><div className="interest-grid">{Object.entries(labels).map(([key,label]) => { const Icon = icons[key]; return <button type="button" aria-pressed={topics.includes(key)} className={'interest-option ' + (topics.includes(key) ? 'chosen' : '')} key={key} onClick={() => toggle(key)}><Icon size={21}/><span>{label}</span><div className="checkbox">{topics.includes(key) && <Check size={12}/>}</div></button>; })}</div><label className="field-label" htmlFor="custom-interests">Anything more specific? <span>OPTIONAL</span></label><input id="custom-interests" value={keywords} maxLength={400} onChange={event => setKeywords(event.target.value)} placeholder="e.g. climate tech, architecture, space exploration"/><span className="field-hint">Separate interests with commas. Up to 8, 60 characters each.</span><div className="form-actions"><Button type="button" disabled={!topics.length || saving} onClick={() => { setStep(2); notify('Choose your reading ritual.'); }}>Find my rhythm <ArrowRight size={17}/></Button>{onCancel ? <button type="button" className="text-button" onClick={onCancel}>Cancel</button> : <button type="button" className="text-button" onClick={() => { setTopics(['technology','world','science']); setStep(2); notify('Thoughtful defaults selected.'); }}>Use thoughtful defaults</button>}</div></> : <><button type="button" className="back-link" onClick={() => { setStep(1); notify('Back to your interests.'); }}><ArrowLeft size={15}/>Your interests</button><span className="eyebrow">MAKE ROOM FOR A GOOD READ</span><h2>Your morning.<br/><em>Your rhythm.</em></h2><p className="form-description">A paper that fits the space you have.</p><label className="field-label">How do you like to read?</label><div className="depth-options">{[['brief','The quick read','A light morning glance'],['balanced','A little perspective','A balanced daily ritual'],['deep','Room to explore','More stories, more context']].map(([id,label,detail]) => <button type="button" className={depth === id ? 'selected-depth' : ''} key={id} onClick={() => { setDepth(id); setLength(id === 'brief' ? 4 : id === 'deep' ? 12 : 8); notify(label + ' selected.'); }}><span><b>{label}</b><small>{detail}</small></span>{depth === id && <Check size={17}/>}</button>)}</div><div className="field-pair"><div><label className="field-label" htmlFor="edition-length">Stories per edition</label><select id="edition-length" value={length} onChange={e => setLength(e.target.value)}>{[4,6,8,10,12,16].map(n => <option key={n} value={n}>{n} stories</option>)}</select></div><div><label className="field-label" htmlFor="language">Language</label><select id="language" value="en" onChange={() => notify('English is supported in this edition.')}><option value="en">English</option></select></div></div><label className="field-label" htmlFor="region">Local region <span>OPTIONAL</span></label><input id="region" value={locale} onChange={e => setLocale(e.target.value)} maxLength={60} placeholder="e.g. Karachi, Pakistan"/><label className="field-label" htmlFor="timezone">Edition timezone</label><select id="timezone" value={timezone} onChange={e => setTimezone(e.target.value)}>{[...new Set([timezone,'Asia/Karachi','UTC','Europe/London','America/New_York','Asia/Dubai'])].map(zone => <option key={zone}>{zone}</option>)}</select><p className="privacy-note"><Info size={14}/>No sign-up. Your anonymous reading profile stays on this local server. No payment required.</p><Button type="submit" disabled={saving} className="create-button">{saving ? <LoaderCircle className="spin" size={17}/> : <Newspaper size={17}/>} {saving ? 'Gathering your first edition…' : profile.onboarded ? 'Save my preferences' : 'Make my morning paper'}</Button></>}</form></section></main>;
}

createRoot(document.getElementById('root')).render(<App/>);
