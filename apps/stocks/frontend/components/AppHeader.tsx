'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import ThemeToggle from '@/components/ThemeToggle';
import AppIcon from '@/components/ui/AppIcon';
import BrandMark from '@/components/ui/BrandMark';
import { useSessionControls } from '@/components/SessionControls';
import { AnalysisStatusProvider, useAnalysisStatus } from '@/hooks/useAnalysisStatus';

const navigation = [
  { href: '/', label: 'Overview', icon: 'dashboard' },
  { href: '/analysis/reports', label: 'Research', icon: 'reports' },
  { href: '/news', label: 'Market news', icon: 'news' },
  { href: '/activity', label: 'Activity', icon: 'activity' },
] as const;

function HeaderContent() {
  const pathname = usePathname();
  const session = useSessionControls();
  const { isAnalyzing, analyzingTicker } = useAnalysisStatus();

  return <header className="workspace-header">
    <a className="skip-link" href="#main-content">Skip to content</a>
    <div className="workspace-header-top">
      <Link href="/" className="workspace-brand" aria-label="YapVibes overview">
        <BrandMark size={48} />
        <span>yapvibes<span className="brand-period">.</span><small>MARKET COMPANION</small></span>
      </Link>
      <div className="workspace-account">
        <span className="workspace-private"><AppIcon name="lock" width={13} height={13} /> Personal workspace</span>
        <span className="account-divider" />
        <ThemeToggle />
        {session && <button className="workspace-signout" type="button" onClick={session.signOut} disabled={session.busy} aria-label="Sign out of your workspace"><AppIcon name="logout" width={17} height={17} /><span>{session.busy ? 'Signing out…' : 'Sign out'}</span></button>}
      </div>
    </div>
    <nav aria-label="Main navigation" className="workspace-nav">
      {navigation.map(item => {
        const active = item.href === '/' ? pathname === '/' : pathname.startsWith(item.href);
        const researchActive = item.icon === 'reports' && pathname.startsWith('/intelligence');
        return <Link key={item.href} href={item.href} aria-current={active || researchActive ? 'page' : undefined} className={`workspace-nav-link${active || researchActive ? ' is-active' : ''}`}><AppIcon name={item.icon} width={17} height={17} />{item.label}</Link>;
      })}
      <span className="workspace-nav-note">Your space to see the bigger picture</span>
    </nav>
    {isAnalyzing && <div role="status" className="analysis-progress"><span className="button-spinner" />Preparing your analysis for {analyzingTicker}…</div>}
  </header>;
}

export default function AppHeader() {
  return <AnalysisStatusProvider><HeaderContent /></AnalysisStatusProvider>;
}
