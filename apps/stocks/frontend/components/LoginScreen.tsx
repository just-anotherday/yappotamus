'use client';

import { useState, type FormEvent } from 'react';
import AppIcon from '@/components/ui/AppIcon';
import ThemeToggle from '@/components/ThemeToggle';
import BrandMark from '@/components/ui/BrandMark';

interface LoginScreenProps {
  email: string;
  password: string;
  onEmailChange: (value: string) => void;
  onPasswordChange: (value: string) => void;
  onSubmit: (event: FormEvent) => void;
  busy: boolean;
  error: string | null;
}

export default function LoginScreen({ email, password, onEmailChange, onPasswordChange, onSubmit, busy, error }: LoginScreenProps) {
  const [showPassword, setShowPassword] = useState(false);
  const [capsLock, setCapsLock] = useState(false);

  return <main className="login-layout">
    <section className="login-story" aria-labelledby="login-story-heading">
      <div className="login-brand"><BrandMark size={56} /><span>yapvibes<span className="brand-period">.</span></span></div>
      <div className="login-story-copy">
        <p className="eyebrow"><span className="accent-line" /> Your market companion</p>
        <h1 id="login-story-heading">Less noise.<br /><span>More perspective.</span></h1>
        <p className="login-story-description">A little clarity for a market that never stops moving. Your watchlist, the stories behind it, and room to think.</p>
        <div className="login-illustration" aria-hidden="true">
          <div className="illustration-caption"><AppIcon name="chart" /> A wider perspective</div>
          <svg viewBox="0 0 500 160" fill="none" preserveAspectRatio="none">
            <defs><linearGradient id="login-chart-fill" x1="0" y1="0" x2="0" y2="1"><stop stopColor="#ef8b50" stopOpacity=".16" /><stop offset="1" stopColor="#ef8b50" stopOpacity="0" /></linearGradient></defs>
            <path d="M0 132 C35 140 45 100 78 110 S120 145 152 97 S195 117 224 70 S265 95 298 57 S345 81 380 35 S422 62 452 21 S480 27 500 10 V160 H0Z" fill="url(#login-chart-fill)" />
            <path d="M0 132 C35 140 45 100 78 110 S120 145 152 97 S195 117 224 70 S265 95 298 57 S345 81 380 35 S422 62 452 21 S480 27 500 10" stroke="#ef8b50" strokeWidth="2.5" />
          </svg>
          <div className="illustration-grid" />
        </div>
      </div>
      <div className="login-story-footer"><span>Follow what matters.</span><span>Make space for the bigger picture.</span></div>
    </section>

    <section className="login-form-panel" aria-labelledby="login-heading">
      <div className="login-topbar"><span className="login-mobile-brand"><BrandMark size={40} /><span>yapvibes<span className="brand-period">.</span></span></span><ThemeToggle /></div>
      <div className="login-form-content">
        <span className="private-badge"><AppIcon name="lock" width={13} height={13} /> Personal workspace</span>
        <h2 id="login-heading">Welcome back.</h2>
        <p className="login-intro">Your research desk is right where you left it.</p>
        <form onSubmit={onSubmit} aria-busy={busy} className="login-form">
          <label htmlFor="login-email">Email address</label>
          <div className="login-input-wrap"><AppIcon name="mail" width={18} height={18} /><input id="login-email" type="email" autoComplete="username" required value={email} onChange={e => onEmailChange(e.target.value)} placeholder="you@example.com" disabled={busy} /></div>
          <label htmlFor="login-password">Password</label>
          <div className="login-input-wrap"><AppIcon name="lock" width={18} height={18} /><input id="login-password" type={showPassword ? 'text' : 'password'} autoComplete="current-password" required value={password} onChange={e => onPasswordChange(e.target.value)} onKeyUp={e => setCapsLock(e.getModifierState('CapsLock'))} onKeyDown={e => setCapsLock(e.getModifierState('CapsLock'))} onBlur={() => setCapsLock(false)} placeholder="Enter your password" disabled={busy} aria-describedby={capsLock ? 'caps-lock-warning' : undefined} /><button type="button" className="password-visibility" onClick={() => setShowPassword(value => !value)} aria-label={showPassword ? 'Hide password' : 'Show password'} aria-pressed={showPassword}><AppIcon name={showPassword ? 'eyeOff' : 'eye'} width={18} height={18} /></button></div>
          {capsLock && <p id="caps-lock-warning" role="status" className="login-field-hint">Caps Lock is on.</p>}
          {error && <div role="alert" className="login-error">{error}</div>}
          <button type="submit" disabled={busy || !email.trim() || !password} className="login-submit">{busy ? <><span className="button-spinner" /> Signing in…</> : <>Open my workspace <AppIcon name="arrow" width={18} height={18} /></>}</button>
        </form>
        <p className="login-private-note"><AppIcon name="shield" width={16} height={16} /> Private by design. Access is limited to your account.</p>
      </div>
      <div className="login-bottom-note">A clearer view starts here.<span>YapVibes Market Companion</span></div>
    </section>
  </main>;
}
