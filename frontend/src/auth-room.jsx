import React, { useEffect, useRef, useState } from 'react';
import { LoaderCircle, X } from 'lucide-react';
import { authClient, authDeadline, boundedFetch, useAccount, useGuest, clearSession, accountExpected } from './auth-client';

export function AuthRoom({ children }) {
  const [client, setClient] = useState(null);
  const [mode, setMode] = useState('loading');
  const [session, setSession] = useState(null);
  const [form, setForm] = useState('');
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const active = useRef(false);
  useEffect(() => {
    const expire = () => { if (active.current) { setMode('locked'); setMessage('Your session expired. Sign in again to continue.'); } };
    window.addEventListener('daily-mind-auth-expired', expire);
    return () => window.removeEventListener('daily-mind-auth-expired', expire);
  }, []);
  useEffect(() => {
    let alive = true, subscription, provider;
    const fragment = new URLSearchParams(window.location.hash.slice(1));
    if (fragment.has('access_token') || fragment.has('refresh_token')) {
      history.replaceState(null, '', window.location.pathname + window.location.search);
      setMessage('Email confirmation received. Sign in to open your account.');
    }
    active.current = accountExpected();
    (async () => {
      try {
        const response = await boundedFetch('/api/auth/config');
        if (!response.ok) throw new Error();
        const config = await response.json();
        if (!alive) return;
        if (!config.enabled) { setMode(active.current ? 'locked' : 'guest'); return; }
        provider = await authClient(config);
        if (!alive) { provider.auth.stopAutoRefresh(); return; } setClient(provider);
        subscription = provider.auth.onAuthStateChange((event, value) => {
          if (!alive) return;
          if (value && active.current) { useAccount(value); setSession(value); setMode('account'); }
          else if (value) clearSession();
          else if (!value && active.current) { setSession(null); setMode('locked'); }
        }).data.subscription;
        const { data, error } = await authDeadline(provider.auth.getSession());
        if (!alive) return;
        if (error) throw error;
        if (data.session && active.current) { useAccount(data.session); setSession(data.session); setMode('account'); }
        else setMode(active.current ? 'locked' : 'guest');
      } catch { if (alive) { setMode(active.current ? 'locked' : 'guest'); setMessage('Account service unavailable. Guest reading is available offline.'); } }
    })();
    return () => { alive = false; subscription?.unsubscribe(); provider?.auth.stopAutoRefresh(); };
  }, []);
  async function submit(event) {
    event.preventDefault(); setBusy(true); setMessage('');
    active.current = true;
    try {
      if (!client) throw new Error('Account service is not configured. Continue as guest.');
      const result = await authDeadline(form === 'signup' ? client.auth.signUp({ email, password }) : client.auth.signInWithPassword({ email, password }));
      if (result.error) throw result.error;
      client.auth.startAutoRefresh();
      setPassword('');
      if (result.data.session) {
        useAccount(result.data.session); setSession(result.data.session); setMode('account'); setForm('');
        setMessage('Signed in. Your account has its own private reading room. Guest editions remain separate.');
      } else {
        active.current = false;
        setMessage('Check your email to confirm your account, then sign in.'); setForm('signin');
      }
    } catch (error) { active.current = mode === 'account' || mode === 'locked'; setMessage(error.message || 'Authentication unavailable. Please retry.'); }
    finally { setBusy(false); }
  }
  async function leave() {
    setBusy(true); active.current = false;
    useGuest(); setSession(null); setMode('guest'); setForm(''); setPassword('');
    try {
      client?.auth.stopAutoRefresh();
      const result = client && await authDeadline(client.auth.signOut({ scope: 'local' }));
      setMessage(result?.error ? 'Signed out on this device. Server revocation could not be confirmed.' : 'Guest reading room restored. Your account editions are saved.');
    } catch { setMessage('Signed out on this device. Account service is offline.'); }
    finally { clearSession(); setBusy(false); }
  }
  return <>
    <aside className="account-strip" aria-label="Reader account">
      <span>{mode === 'account' ? 'YOUR ACCOUNT EDITION' : mode === 'locked' ? 'SESSION NEEDS ATTENTION' : 'GUEST READING ROOM'}</span>
      <div>{mode === 'account' ? <button disabled={busy} onClick={leave}>Sign out</button> : <>
        <button disabled={busy} onClick={() => { setForm('signin'); setMessage(''); }}>Sign in</button>
        <button disabled={busy} onClick={() => { setForm('signup'); setMessage(''); }}>Create account</button>
        {(mode === 'locked' || mode === 'loading') && <button disabled={busy} onClick={leave}>Continue as guest</button>}
      </>}</div>
    </aside>
    {message && <div className="auth-notice" role="status">{message}<button aria-label="Dismiss account message" onClick={() => setMessage('')}><X size={15}/></button></div>}
    {mode === 'loading' ? <div className="auth-loading"><LoaderCircle className="spin"/> Opening your reading room…</div> : mode === 'locked' ? <main className="auth-locked"><h1>Return to your reading room.</h1><p>Your session expired or the account service is unavailable. Sign in again, or explicitly continue as guest. Your saved account editions remain in SQLite.</p></main> : React.cloneElement(children, { key: mode === 'account' ? session.user.id : 'guest', identityKey: mode === 'account' ? 'account:' + session.user.id : 'guest' })}
    {form && <div className="auth-overlay"><section className="auth-dialog" role="dialog" aria-modal="true" aria-labelledby="auth-title">
      <button className="auth-close" aria-label="Close account form" disabled={busy} onClick={() => { setForm(''); setPassword(''); }}><X/></button>
      <div className="eyebrow">THE DAILY MIND · READER ACCOUNT</div>
      <h1 id="auth-title">{form === 'signup' ? 'A place for your perspective.' : 'Welcome back, reader.'}</h1>
      <p>Optional sign-in. Guest preferences and archives stay separate. No profiles are silently merged.</p>
      {!client ? <p role="alert">Account service is not configured or is unavailable. Guest Mode remains available.</p> : <form onSubmit={submit}>
        <label>Email<input type="email" autoComplete="email" value={email} onChange={e => setEmail(e.target.value)} required maxLength={254}/></label>
        <label>Password<input type="password" autoComplete={form === 'signup' ? 'new-password' : 'current-password'} value={password} onChange={e => setPassword(e.target.value)} required minLength={form === 'signup' ? 8 : 1} maxLength={128}/></label>
        <button className="auth-submit" disabled={busy}>{busy ? <><LoaderCircle className="spin" size={16}/> Please wait…</> : form === 'signup' ? 'Create account' : 'Sign in'}</button>
      </form>}
      {message && <p role="status">{message}</p>}
      <button className="auth-switch" disabled={busy} onClick={() => { setForm(form === 'signup' ? 'signin' : 'signup'); setMessage(''); }}>{form === 'signup' ? 'Already a reader? Sign in' : 'New here? Create an account'}</button>
      <button className="auth-switch" disabled={busy} onClick={() => { setForm(''); setPassword(''); if (mode === 'locked') leave(); }}>Continue as guest</button>
    </section></div>}
  </>;
}
