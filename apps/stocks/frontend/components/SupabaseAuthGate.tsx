'use client';

import { useEffect, useRef, useState } from 'react';
import { getSupabaseAuth } from '@/lib/supabaseAuth';
import { AUTH_INVALID_EVENT, clearAppToken, setAppToken } from '@/lib/apiFetch';
import { requireOk } from '@/lib/apiError';
import { API_BASE } from '@/lib/serviceUrls';
import LoginScreen from '@/components/LoginScreen';
import { SessionControlsContext } from '@/components/SessionControls';

export default function SupabaseAuthGate({ children }: { children: React.ReactNode }) {
  const [unlocked, setUnlocked] = useState(false);
  const [checking, setChecking] = useState(true);
  const [busy, setBusy] = useState(false);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const generation = useRef(0);

  useEffect(() => {
    let active = true;
    let verified = false;
    let verifiedUserId: string | null = null;
    clearAppToken(); // Never reuse the old shared app token in Supabase mode.
    const onInvalid = () => {
      generation.current += 1;
      verified = false;
      setUnlocked(false);
      setChecking(false);
      setError('Your session is invalid or this account does not have access. Please sign in again.');
    };
    window.addEventListener(AUTH_INVALID_EVENT, onInvalid);
    let unsubscribe = () => {};
    try {
      const supabase = getSupabaseAuth();
      const { data } = supabase.auth.onAuthStateChange((_event, session) => {
        // Keep this callback synchronous; calling Supabase Auth methods inside
        // it can deadlock the SDK's session lock.
        const current = ++generation.current;
        if (!session) {
          verified = false;
          clearAppToken();
          setUnlocked(false);
          setChecking(false);
          return;
        }
        setAppToken(session.access_token);
        // A refresh of an already authorized session keeps the mounted app.
        // Subsequent API requests still verify the owner on the backend.
        if (verified && verifiedUserId === session.user.id) return;
        verified = false;
        setUnlocked(false);
        setChecking(true);
        void (async () => {
          try {
            const response = await fetch(`${API_BASE}/api/auth/verify`, {
              headers: { Authorization: `Bearer ${session.access_token}` },
              cache: 'no-store',
            });
            await requireOk(response, 'Unable to verify your account. Please try again.');
            if (active && current === generation.current) {
              verified = true;
              verifiedUserId = session.user.id;
              setUnlocked(true);
              setError(null);
            }
          } catch (err) {
            if (active && current === generation.current) {
              clearAppToken();
              setUnlocked(false);
              setError(err instanceof Error ? err.message : 'Unable to verify your account.');
            }
          } finally {
            if (active && current === generation.current) setChecking(false);
          }
        })();
      });
      unsubscribe = () => data.subscription.unsubscribe();
    } catch (err) {
      queueMicrotask(() => {
        if (!active) return;
        setError(err instanceof Error ? err.message : 'Login is not configured.');
        setChecking(false);
      });
    }
    return () => {
      active = false;
      generation.current += 1;
      unsubscribe();
      window.removeEventListener(AUTH_INVALID_EVENT, onInvalid);
    };
  }, []);

  async function signIn(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const { error: authError } = await getSupabaseAuth().auth.signInWithPassword({ email: email.trim(), password });
      if (authError) throw authError;
      setPassword('');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to sign in.');
    } finally {
      setBusy(false);
    }
  }

  async function signOut() {
    setBusy(true);
    try {
      const { error: authError } = await getSupabaseAuth().auth.signOut({ scope: 'local' });
      if (authError) throw authError;
      clearAppToken();
      setUnlocked(false);
    } catch {
      setError('Unable to sign out. Please try again.');
    } finally {
      setBusy(false);
    }
  }

  if (checking) return <div role="status" className="session-loading"><span className="session-loading-mark">y<span>.</span></span><span className="button-spinner" /><span>Opening your workspace…</span></div>;

  if (unlocked) return <SessionControlsContext.Provider value={{ signOut, busy }}>
    {error && <div role="alert" className="login-error mx-4 mt-3">{error}</div>}
    {children}
  </SessionControlsContext.Provider>;

  return <LoginScreen email={email} password={password} onEmailChange={setEmail} onPasswordChange={setPassword} onSubmit={signIn} busy={busy} error={error} />;
}
