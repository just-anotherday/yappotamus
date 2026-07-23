'use client';

import { useEffect, useState } from 'react';
import { API_BASE } from '@/types/stock';
import {
  apiFetch,
  clearAppToken,
  getAppToken,
  setAppToken,
  AUTH_INVALID_EVENT,
} from '@/lib/apiFetch';

export default function AuthGate({ children }: { children: React.ReactNode }) {
  const [unlocked, setUnlocked] = useState(false);
  const [checked, setChecked] = useState(false);
  const [input, setInput] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [validating, setValidating] = useState(false);

  useEffect(() => {
    setUnlocked(!!getAppToken());
    setChecked(true);

    const onInvalid = () => {
      setUnlocked(false);
      setError('Session expired or invalid token. Please re-enter your access token.');
    };
    window.addEventListener(AUTH_INVALID_EVENT, onInvalid);
    return () => window.removeEventListener(AUTH_INVALID_EVENT, onInvalid);
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim()) return;

    setValidating(true);
    setError(null);
    setAppToken(input.trim());

    try {
      const response = await apiFetch(`${API_BASE}/api/auth/verify`);
      if (!response.ok) {
        clearAppToken();
        setUnlocked(false);
        setError('Unable to verify the access token. Please try again.');
        return;
      }

      setUnlocked(true);
      setInput('');
    } catch {
      clearAppToken();
      setUnlocked(false);
      setError('Unable to reach the API. Check the connection and try again.');
    } finally {
      setValidating(false);
    }
  };

  // Avoid a flash of protected content before we've checked sessionStorage.
  if (!checked) return null;

  if (!unlocked) {
    return (
      <div className="min-h-screen flex items-center justify-center p-8 bg-gradient-to-br from-orange-50 to-orange-100 dark:from-slate-800 dark:via-gray-900 dark:to-slate-700">
        <form
          onSubmit={handleSubmit}
          style={{ boxShadow: '0 4px 16px rgba(0,0,0,0.08)' }}
          className="w-full max-w-sm p-8 rounded-xl bg-white border border-orange-200 dark:bg-slate-800 dark:border-slate-700"
        >
          <h1 className="m-0 mb-2 text-xl font-bold text-gray-700 dark:text-white">
            Enter App Access Token
          </h1>
          <p className="m-0 mb-5 text-sm text-gray-500 dark:text-slate-400">
            This app is private. Enter the access token to continue.
          </p>
          <input
            type="password"
            autoFocus
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Access token"
            className="w-full mb-4 px-3.5 py-2.5 rounded-lg text-sm outline-none box-border bg-white border border-gray-300 text-gray-700 dark:bg-slate-900 dark:border-slate-600 dark:text-gray-200"
          />
          <button
            type="submit"
            disabled={!input.trim() || validating}
            className={`w-full py-2.5 px-4 rounded-lg border-0 text-white text-sm font-semibold ${
              input.trim() && !validating ? 'bg-orange-500 cursor-pointer' : 'bg-gray-400 cursor-not-allowed'
            }`}
          >
            {validating ? 'Verifying…' : 'Unlock'}
          </button>
          {error && (
            <div className="mt-4 px-3 py-2.5 rounded-lg text-sm bg-red-50 border border-red-200 text-red-600 dark:bg-red-900/30 dark:border-red-800 dark:text-red-400">
              {error}
            </div>
          )}
        </form>
      </div>
    );
  }

  return <>{children}</>;
}
