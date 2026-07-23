'use client';

import Image from 'next/image';
import Link from 'next/link';
import ThemeToggle from '@/components/ThemeToggle';
import { AnalysisStatusProvider, useAnalysisStatus } from '@/hooks/useAnalysisStatus';

function AnalysisStatusBar() {
  const { isAnalyzing, analyzingTicker } = useAnalysisStatus();

  if (!isAnalyzing) return null;

  return (
    <div className="w-full bg-gradient-to-r from-orange-500 via-amber-500 to-orange-500 animate-pulse">
      <div className="max-w-7xl mx-auto px-4 py-2 flex items-center justify-center gap-3">
        <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
        <span className="text-sm font-bold text-white tracking-wide">
          Generating AI Analysis for {analyzingTicker}...
        </span>
      </div>
    </div>
  );
}

function HeaderContent() {
  return (
    <>
      {/* Live analysis status bar */}
      <AnalysisStatusBar />

      {/* Header - Logo + Branding */}
      <header className="bg-white dark:bg-slate-900 shadow-xl border-b border-gray-200 dark:border-slate-700">
        <div className="max-w-7xl mx-auto px-4 py-6 flex items-center justify-between">
          <div>
            <Link href="/" className="inline-block">
              <div className="flex items-center gap-3">
                <Image
                  src="/yapvibes_orange.png"
                  alt="yapvibes logo"
                  width={100}
                  height={100}
                  className="hover:opacity-90 transition-opacity cursor-pointer mt-3"
                />
                <div>
                  <h1 className="text-5xl font-black tracking-tight hover:opacity-90 transition-opacity cursor-pointer bg-gradient-to-r from-orange-400 via-orange-500 to-yellow-500 bg-clip-text text-transparent">
                    yapvibes
                  </h1>
                  <span className="text-xl font-semibold tracking-normal text-gray-700 dark:text-gray-300 hover:opacity-90 transition-opacity cursor-pointer">
                    Market Companion
                  </span>
                </div>
              </div>
            </Link>
            
            <div className="mt-4 ml-1 flex items-center gap-2">
              <span className="inline-block w-3 h-3 bg-green-500 rounded-full animate-pulse"></span>
              <p className="text-lg max-w-2xl font-medium">
                <span className="bg-gradient-to-r from-orange-400 via-orange-500 to-yellow-500 bg-clip-text text-transparent font-bold"> Market News</span>
                <span className="text-gray-600 dark:text-gray-300"> — </span>
                <span className="bg-gradient-to-r from-orange-400 via-orange-500 to-yellow-500 bg-clip-text text-transparent font-bold"> AI Analysis Reports</span>
                <span className="text-gray-600 dark:text-gray-300"> — </span>
                <span className="bg-gradient-to-r from-orange-400 via-orange-500 to-yellow-500 bg-clip-text text-transparent font-bold"> &more,</span>
                <span className="text-gray-600 dark:text-gray-300"> — </span>
                <span className="bg-gradient-to-r from-orange-400 via-orange-500 to-yellow-500 bg-clip-text text-transparent font-bold"> coming soon!</span>
                <span className="text-gray-600 dark:text-gray-300 animate-bounce inline-block"> 👋</span>
              </p>

            </div>
          </div>
          <ThemeToggle />
        </div>
      </header>

      {/* Navbar - Navigation + Theme Toggle */}
      <nav className="bg-white dark:bg-slate-900 border-b border-gray-200 dark:border-slate-700 shadow-sm">
        <div className="max-w-7xl mx-auto px-4 py-3">
          <div className="flex items-center justify-between">
            {/* Left: Navigation Links */}
            <div className="flex items-center gap-3">
              <Link
                href="/"
                className="group px-4 py-2 rounded-lg bg-gradient-to-r from-orange-500 to-orange-600 text-white text-sm font-bold shadow-md hover:from-orange-600 hover:to-orange-700 hover:shadow-lg transition-all duration-300 flex items-center gap-2 tracking-wide"
              >
                <svg className="w-8 h-8 group-hover:scale-110 transition-transform" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M3 12l2-2m0 0l9-9 9 9M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6" />
                </svg>
                Home
              </Link>

              <Link
                href="/news"
                className="group px-4 py-2 rounded-lg bg-gradient-to-r from-orange-500 to-orange-600 text-white text-sm font-bold shadow-md hover:from-orange-600 hover:to-orange-700 hover:shadow-lg transition-all duration-300 flex items-center gap-2 tracking-wide"
              >
                <svg className="w-8 h-8 group-hover:scale-110 transition-transform" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M19 20H5a2 2 0 01-2-2V6a2 2 0 012-2h10a2 2 0 012 2v1m2 11a2 2 0 01-2-2V7m2 10a2 2 0 002-2V9a2 2 0 00-2-2h-4" />
                </svg>
                 News
              </Link>

               <Link
                 href="/analysis/reports"
                 className="group px-4 py-2 rounded-lg bg-gradient-to-r from-orange-500 to-orange-600 text-white text-sm font-bold shadow-md hover:from-orange-600 hover:to-orange-700 hover:shadow-lg transition-all duration-300 flex items-center gap-2 tracking-wide"
               >
                 <svg className="w-8 h-8 group-hover:scale-110 transition-transform" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                   <path strokeLinecap="round" strokeLinejoin="round" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                 </svg>
                  Analysis Reports
               </Link>

               {/* TODO: Uncomment when Intelligence feature is ready for production
               <Link
                 href="/intelligence"
                 className="group px-4 py-2 rounded-lg bg-gradient-to-r from-orange-500 to-orange-600 text-white text-sm font-bold shadow-md hover:from-orange-600 hover:to-orange-700 hover:shadow-lg transition-all duration-300 flex items-center gap-2 tracking-wide"
               >
                 <svg className="w-8 h-8 group-hover:scale-110 transition-transform" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                   <path strokeLinecap="round" strokeLinejoin="round" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
                 </svg>
                 Intelligence
               </Link>
               */}

                 <Link
                   href="/activity"
                   className="group px-4 py-2 rounded-lg bg-gradient-to-r from-gray-600 to-gray-700 text-white text-sm font-bold shadow-md hover:from-gray-700 hover:to-gray-800 hover:shadow-lg transition-all duration-300 flex items-center gap-2 tracking-wide"
                 >
                   <svg className="w-8 h-8 group-hover:scale-110 transition-transform" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                     <path strokeLinecap="round" strokeLinejoin="round" d="M13 10V3L4 14h7v7l9-11h-7z" />
                   </svg>
                   Activity
                 </Link>

              </div>
          </div>
        </div>
      </nav>
    </>
  );
}

export default function AppHeader() {
  return (
    <AnalysisStatusProvider>
      <HeaderContent />
    </AnalysisStatusProvider>
  );
}
