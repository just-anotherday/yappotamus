'use client';

import { useEffect, useState, useRef, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { API_BASE } from '@/types/stock';
import { apiFetch } from '@/lib/apiFetch';
import type { ReportSummary, ReportPaginationResponse, OllamaConfigStatus } from '@/types/stock';
import { useAnalysisStatus } from '@/hooks/useAnalysisStatus';
import ArticleSelectionMeter from '@/components/ArticleSelectionMeter';
import { formatReportDateTime, getPromptBadge } from '@/lib/reportPresentation';

export default function ReportsPage() {
  const router = useRouter();
  const { setAnalyzing, clearAnalyzing } = useAnalysisStatus();

  // ---- Saved reports state ----
  const [reports, setReports] = useState<ReportSummary[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [hasMore, setHasMore] = useState(false);
  const [loading, setLoading] = useState(false);
  const [fetchError, setFetchError] = useState<string | null>(null);
  const [limit] = useState(20);

  // ---- Filters ----
  const [tickerFilter, setTickerFilter] = useState('');
  const [debouncedFilter, setDebouncedFilter] = useState('');
  const debounceTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);
  const [sort, setSort] = useState<'newest' | 'oldest'>('newest');

  // ---- Generate new analysis state ----
  const [config, setConfig] = useState<OllamaConfigStatus | null>(null);
  const [providers, setProviders] = useState<any[]>([]);
  const [selectedProvider, setSelectedProvider] = useState<string>('ollama');
  const [selectedModel, setSelectedModel] = useState<string>('');
  const [selectedTicker, setSelectedTicker] = useState<string>('');
  const [watchlistTickers, setWatchlistTickers] = useState<string[]>([]);
  const [generating, setGenerating] = useState(false);
  const [genError, setGenError] = useState<string | null>(null);

   // ---- Article picker state ----
   const [availableArticles, setAvailableArticles] = useState<any[]>([]);
   const [selectedArticleIds, setSelectedArticleIds] = useState<number[]>([]);
   const [daysBack, setDaysBack] = useState(3);
   const [maxArticles, setMaxArticles] = useState(15);
   const [loadingArticles, setLoadingArticles] = useState(false);
   const [articleSearch, setArticleSearch] = useState('');
   const [articleGroupByDate, setArticleGroupByDate] = useState(true);

  // ---- Fetch Ollama config + providers + watchlist tickers on mount ----
  useEffect(() => {
    apiFetch(`${API_BASE}/api/analysis/config`)
      .then(res => res.json())
      .then(data => {
        setConfig(data);
      })
      .catch(() => setConfig(null));

    // Fetch available providers and models
    apiFetch(`${API_BASE}/api/analysis/providers`)
      .then(res => res.json())
      .then(data => {
        setProviders(data.providers || []);
        // Auto-select first available provider with models, prefer online over offline
        if (data.providers && data.providers.length > 0) {
          // Prefer an available provider; fallback to any provider as last resort
          const availableList = data.providers.filter((p: any) => p.available);
          const pool = availableList.length > 0 ? availableList : data.providers;
          const chosen = pool.find((p: any) => p.models?.length > 0) || pool[0];
          if (chosen) {
            setSelectedProvider(chosen.id);
            if (chosen.models && chosen.models.length > 0) {
              setSelectedModel(chosen.models[0].name || chosen.models[0]);
            }
          } else {
            setSelectedModel('llama3.2');
          }
        } else {
          setSelectedModel('llama3.2');
        }
      })
      .catch(() => setProviders([]));

    // Fetch watchlist tickers from backend
    apiFetch(`${API_BASE}/api/watchlist`)
      .then(res => res.json())
      .then(data => {
        if (Array.isArray(data)) {
          setWatchlistTickers(data.map((item: any) => item.ticker || item.symbol));
        }
      })
      .catch(() => setWatchlistTickers([]));
  }, []);

  // ---- Debounce cleanup on unmount ----
  useEffect(() => {
    return () => {
      if (debounceTimerRef.current) clearTimeout(debounceTimerRef.current);
      if (abortControllerRef.current) abortControllerRef.current.abort();
    };
  }, []);

  // ---- Fetch saved reports with abort support ----
  const doFetch = useCallback(async (pg: number, lim: number, st: string, tf: string) => {
    // Abort any in-flight request
    if (abortControllerRef.current) abortControllerRef.current.abort();
    const controller = new AbortController();
    abortControllerRef.current = controller;

    setLoading(true);
    setFetchError(null);
    try {
      const params = new URLSearchParams();
      params.set('page', String(pg));
      params.set('limit', String(lim));
      params.set('sort', st);
      if (tf) params.set('ticker', tf.toUpperCase());

      const res = await apiFetch(`${API_BASE}/api/analysis/reports/?${params}`, { signal: controller.signal });
      if (!res.ok) throw new Error(`Failed to fetch reports (${res.status})`);
      const data: ReportPaginationResponse = await res.json();
      setReports(data.items);
      setTotal(data.total);
      setHasMore(data.has_more);
    } catch (e: any) {
      if (e.name !== 'AbortError') {
        console.error('[Reports] Fetch error:', e);
        setFetchError(e.message || 'Failed to load reports');
      }
    } finally {
      setLoading(false);
    }
  }, []);

  // ---- Debounce ticker filter: wait 400ms after last keystroke, then fetch ----
  useEffect(() => {
    if (debounceTimerRef.current) clearTimeout(debounceTimerRef.current);
    debounceTimerRef.current = setTimeout(() => {
      setDebouncedFilter(tickerFilter);
    }, 400);
  }, [tickerFilter]);

  // ---- Fetch when debounced filter, page, or sort changes ----
  useEffect(() => {
    doFetch(page, limit, sort, debouncedFilter);
  }, [page, limit, sort, debouncedFilter, doFetch]);

  // ---- Fetch available articles when ticker/daysBack changes ----
  useEffect(() => {
    if (!selectedTicker) {
      setAvailableArticles([]);
      setSelectedArticleIds([]);
      return;
    }
    const controller = new AbortController();
    (async () => {
      setLoadingArticles(true);
      try {
        const res = await apiFetch(
          `${API_BASE}/api/analysis/articles/${selectedTicker.toUpperCase()}?days_back=${daysBack}`,
          { signal: controller.signal }
        );
        if (!res.ok) throw new Error('Failed to fetch articles');
        const data = await res.json();
        setAvailableArticles(data.articles || []);
        // Auto-select up to the current max by default
        const ids = (data.articles || []).slice(0, maxArticles).map((a: any) => a.id);
        setSelectedArticleIds(ids);
      } catch (e: any) {
        if (e.name !== 'AbortError') {
          console.error('[Articles] Fetch error:', e);
        }
      } finally {
        setLoadingArticles(false);
      }
    })();
    return () => controller.abort();
    // maxArticles intentionally omitted: it only seeds the initial auto-select
    // on ticker/day-range change, and shouldn't wipe a manual selection when
    // the user nudges the gauge's max afterward.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedTicker, daysBack]);

  // ---- Article selection helpers ----
  const toggleArticle = (id: number) => {
    setSelectedArticleIds(prev => {
      if (prev.includes(id)) return prev.filter(x => x !== id);
      if (prev.length >= maxArticles) return prev;
      return [...prev, id];
    });
  };

  const selectAllArticles = () => {
    setSelectedArticleIds(availableArticles.slice(0, maxArticles).map((a: any) => a.id));
  };

  const clearAllArticles = () => {
    setSelectedArticleIds([]);
  };

  // ---- Generate analysis handler (updated to use selected articles) ----
  const handleGenerateAnalysis = async () => {
    if (!selectedTicker) {
      setGenError('Please select a ticker from your watchlist');
      return;
    }
    if (!selectedModel) {
      setGenError('Please select a model first');
      return;
    }

    setGenerating(true);
    setGenError(null);

    try {
      setAnalyzing(selectedTicker.toUpperCase());
      const response = await apiFetch(`${API_BASE}/api/analysis/analyze_ticker`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            ticker: selectedTicker.toUpperCase(),
            max_articles: maxArticles,
            days_back: daysBack,
            model: selectedModel,
            provider: selectedProvider,
            article_ids: selectedArticleIds.length > 0 ? selectedArticleIds : undefined,
          }),
      });

      if (!response.ok) {
        const err = await response.json();
        throw new Error(err.detail || 'Analysis failed');
      }

      // Analysis generated — refresh reports list so the new report appears at #1
      setPage(1);
      doFetch(1, limit, sort, tickerFilter);
    } catch (e: any) {
      setGenError(e.message || 'Unknown error');
    } finally {
      setGenerating(false);
      clearAnalyzing();
    }
  };

  // ---- Delete handler (re-fetches to trigger re-numbering) ----
  const handleDeleteReport = async (reportId: number) => {
    if (!confirm('Are you sure you want to delete this report?')) return;
    try {
      const res = await apiFetch(`${API_BASE}/api/analysis/reports/${reportId}`, { method: 'DELETE' });
      if (!res.ok) throw new Error('Failed to delete');
      // Re-fetch reports to trigger numbering recalculation
      await doFetch(page, limit, sort, tickerFilter);
    } catch (e) {
      console.error(e);
      alert('Could not delete report');
    }
  };

  const resetFilters = () => {
    setTickerFilter('');
    setSort('newest');
    setPage(1);
  };

  const getSentimentColor = (sentiment: string) => {
    switch (sentiment) {
      case 'Very Bullish': return '#10b981';
      case 'Bullish': return '#34d399';
      case 'Neutral': return '#f59e0b';
      case 'Bearish': return '#f87171';
      case 'Very Bearish': return '#ef4444';
      default: return '#6b7280';
    }
  };

  const hasActiveFilters = tickerFilter;

  return (
    <div style={{ maxWidth: 900, margin: '0 auto', padding: '2rem', color: 'var(--foreground, #171717)' }}>

      {/* ============================================================ */}
      {/* SECTION: Generate New Analysis                               */}
      {/* ============================================================ */}
      <div style={{
        padding: '1.5rem', borderRadius: '12px', marginBottom: '2rem',
        background: 'linear-gradient(135deg, #fff7ed 0%, #ffedd5 100%)',
        border: '1px solid #fed7aa',
      }}
      className="dark:bg-gradient-to-br dark:from-slate-800 dark:to-slate-900 dark:border-slate-700">
        <h2 style={{ margin: '0 0 1rem', fontSize: '1.25rem', fontWeight: 700, color: '#374151' }}
          className="dark:text-white">
          Generate New Analysis Report
        </h2>

        {/* Step 1: Select Watchlist Ticker */}
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '1rem', alignItems: 'center', marginBottom: '1rem' }}>
          <label htmlFor="ticker-select" style={{ fontSize: '0.875rem', fontWeight: 500, color: '#374151', minWidth: '80px' }}
            className="dark:text-gray-300">
            1. Ticker:
          </label>
          <select
            id="ticker-select"
            value={selectedTicker}
            onChange={(e) => setSelectedTicker(e.target.value)}
            disabled={generating}
            style={{
              padding: '0.5rem 1rem', borderRadius: '8px', border: '1px solid #d1d5db',
              background: '#fff', fontSize: '0.875rem', fontWeight: 500, color: '#374151',
              minWidth: 160,
            }}
            className="dark:bg-slate-800 dark:border-slate-600 dark:text-gray-200"
          >
            <option value="">— Select from watchlist —</option>
            {watchlistTickers.map((t) => (
              <option key={t} value={t}>{t}</option>
            ))}
            {watchlistTickers.length === 0 && (
              <option value="">No watchlist items</option>
            )}
          </select>
        </div>

        {/* Step 2: Select Provider & Model */}
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '1rem', alignItems: 'center', marginBottom: '1rem' }}>
          <label htmlFor="provider-select" style={{ fontSize: '0.875rem', fontWeight: 500, color: '#374151', minWidth: '80px' }}
            className="dark:text-gray-300">
            2. Provider:
          </label>
          <select
            id="provider-select"
            value={selectedProvider}
            onChange={(e) => {
              const newProvider = e.target.value;
              setSelectedProvider(newProvider);
              // Auto-select first model from the new provider
              const prov = providers.find((p: any) => p.id === newProvider);
              if (prov?.models?.length > 0) {
                setSelectedModel(prov.models[0].name || prov.models[0]);
              } else {
                setSelectedModel('');
              }
            }}
            disabled={generating}
            style={{
              padding: '0.5rem 1rem', borderRadius: '8px', border: '1px solid #d1d5db',
              background: '#fff', fontSize: '0.875rem', fontWeight: 500, color: '#374151',
              minWidth: 120,
              opacity: generating ? 0.5 : 1,
              cursor: generating ? 'not-allowed' : 'pointer',
            }}
            className="dark:bg-slate-800 dark:border-slate-600 dark:text-gray-200"
          >
           {providers.map((p: any) => (
               <option key={p.id} value={p.id} disabled={!p.available}>
                 {p.name} {!p.available ? '(offline)' : ''}
               </option>
             ))}
            {providers.length === 0 && (
              <option value="ollama">ollama (default)</option>
            )}
          </select>

          {/* Provider status indicators */}
          {providers.map((p: any) => (
            <span key={p.id} style={{
              display: 'inline-flex', alignItems: 'center', gap: '0.4rem',
              fontSize: '0.75rem', color: p.available ? '#10b981' : '#ef4444',
            }}
            className="dark:text-gray-400">
              <span style={{
                width: 8, height: 8, borderRadius: '50%', display: 'inline-block',
                background: p.available ? '#10b981' : '#ef4444',
              }} />
              {p.name} {p.available ? 'Ready' : 'Offline'}
            </span>
          ))}
        </div>

        {/* Step 2b: Model Selector (indented under provider) */}
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '1rem', alignItems: 'center', marginBottom: '1rem' }}>
          <label htmlFor="model-select" style={{ fontSize: '0.875rem', fontWeight: 500, color: '#374151', minWidth: '80px' }}
            className="dark:text-gray-300">
            Model:
          </label>
          <select
            id="model-select"
            value={selectedModel}
            onChange={(e) => setSelectedModel(e.target.value)}
            disabled={generating}
            style={{
              padding: '0.5rem 1rem', borderRadius: '8px', border: '1px solid #d1d5db',
              background: '#fff', fontSize: '0.875rem', fontWeight: 500, color: '#374151',
              minWidth: 200,
              opacity: generating ? 0.5 : 1,
              cursor: generating ? 'not-allowed' : 'pointer',
            }}
            className="dark:bg-slate-800 dark:border-slate-600 dark:text-gray-200"
          >
            <option value="">— Select a model —</option>
            {(() => {
              const selectedProv = providers.find((p: any) => p.id === selectedProvider);
              const models = selectedProv?.models || [];
              return models.map((m: any) => (
                <option key={m.name} value={m.name}>{m.name}</option>
              ));
            })()}
          </select>
        </div>

        {/* Step 3: Days Back Slider */}
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '1rem', alignItems: 'center', marginBottom: '1rem' }}>
          <label htmlFor="days-back" style={{ fontSize: '0.875rem', fontWeight: 500, color: '#374151', minWidth: '80px' }}
            className="dark:text-gray-300">
            3. Days Back:
          </label>
          <input
            id="days-back"
            type="range"
            min={1}
            max={14}
            value={daysBack}
            onChange={(e) => setDaysBack(Number(e.target.value))}
            disabled={!selectedTicker || generating}
            style={{ flex: 1, minWidth: 120, opacity: (!selectedTicker || generating) ? 0.5 : 1 }}
          />
          <span style={{ fontSize: '0.875rem', fontWeight: 600, color: '#f97316', minWidth: 40 }}
            className="dark:text-orange-400">
            {daysBack} day{daysBack > 1 ? 's' : ''}
          </span>
        </div>

        {/* Step 4: Article Picker */}
        {selectedTicker && (
          <div style={{ marginBottom: '1rem' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '1rem', marginBottom: '0.75rem', flexWrap: 'wrap' }}>
              <label style={{ fontSize: '0.875rem', fontWeight: 500, color: '#374151' }}
                className="dark:text-gray-300">
                4. Select Articles
              </label>
              <div style={{ display: 'flex', gap: '0.5rem' }}>
                <button
                  onClick={selectAllArticles}
                  disabled={loadingArticles || selectedArticleIds.length >= maxArticles}
                  style={{
                    padding: '0.25rem 0.5rem', borderRadius: '4px', border: '1px solid #d1d5db',
                    background: 'white', fontSize: '0.75rem', cursor: 'pointer', color: '#374151',
                  }}
                  className="dark:bg-slate-800 dark:border-slate-600 dark:text-gray-200"
                >
                  Select All
                </button>
                <button
                  onClick={clearAllArticles}
                  disabled={loadingArticles}
                  style={{
                    padding: '0.25rem 0.5rem', borderRadius: '4px', border: '1px solid #d1d5db',
                    background: 'white', fontSize: '0.75rem', cursor: 'pointer', color: '#374151',
                  }}
                  className="dark:bg-slate-800 dark:border-slate-600 dark:text-gray-200"
                >
                  Clear All
                </button>
              </div>
            </div>

            <div style={{ marginBottom: '0.75rem' }}>
              <ArticleSelectionMeter
                selected={selectedArticleIds.length}
                max={maxArticles}
                available={availableArticles.length}
                onMaxChange={setMaxArticles}
              />
            </div>

            {/* Article Search */}
            <input
              type="text"
              placeholder="Search articles by title or source..."
              value={articleSearch}
              onChange={(e) => setArticleSearch(e.target.value)}
              style={{
                width: '100%', padding: '0.5rem 0.75rem', borderRadius: '6px', border: '1px solid #d1d5db',
                fontSize: '0.8125rem', outline: 'none', marginBottom: '0.5rem', boxSizing: 'border-box',
                background: 'white', color: '#374151',
              }}
              className="dark:bg-slate-800 dark:border-slate-600 dark:text-gray-200"
            />

            <div style={{
              maxHeight: 320, overflowY: 'auto', borderRadius: '8px', border: '1px solid #e5e7eb',
              background: '#fafafa',
            }}
            className="dark:bg-slate-900 dark:border-slate-600">
              {loadingArticles ? (
                <div style={{ padding: '2rem', textAlign: 'center', color: '#9ca3af' }}>Loading articles...</div>
              ) : availableArticles.length === 0 ? (
                <div style={{ padding: '2rem', textAlign: 'center', color: '#9ca3af' }}>
                  No articles found for {selectedTicker} in the last {daysBack} day{daysBack > 1 ? 's' : ''}
                </div>
              ) : (
                (() => {
                  // Filter by search
                  const filtered = availableArticles.filter((a: any) => {
                    if (!articleSearch) return true;
                    const q = articleSearch.toLowerCase();
                    return (a.title || '').toLowerCase().includes(q) ||
                           (a.provider_name || '').toLowerCase().includes(q) ||
                           (a.summary || '').toLowerCase().includes(q);
                  });

                  // Group by date
                  const groups: Record<string, any[]> = {};
                  filtered.forEach((a: any) => {
                    let dateKey = 'No Date';
                    if (a.pub_date) {
                      try {
                        const d = new Date(a.pub_date);
                        const now = new Date();
                        const diffMs = now.getTime() - d.getTime();
                        const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));
                        if (diffDays === 0) dateKey = 'Today';
                        else if (diffDays === 1) dateKey = 'Yesterday';
                        else dateKey = d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
                      } catch { /* keep default */ }
                    }
                    if (!groups[dateKey]) groups[dateKey] = [];
                    groups[dateKey].push(a);
                  });

                  const dateOrder = ['Today', 'Yesterday', ...Object.keys(groups).filter(k => k !== 'Today' && k !== 'Yesterday'), 'No Date'];
                  const sortedKeys = Object.keys(groups).sort((a, b) => dateOrder.indexOf(a) - dateOrder.indexOf(b));

                  return (
                    <>
                      {sortedKeys.map(dateKey => (
                        <div key={dateKey}>
                          {/* Date Group Header */}
                          <div style={{
                            padding: '0.4rem 0.75rem', fontSize: '0.6875rem', fontWeight: 700,
                            color: '#6b7280', background: '#f3f4f6', borderBottom: '1px solid #e5e7eb',
                            display: 'flex', alignItems: 'center', gap: '0.5rem',
                          }}
                          className="dark:bg-slate-800 dark:border-slate-700 dark:text-slate-400">
                            <span>{dateKey}</span>
                            <span style={{ fontSize: '0.625rem', fontWeight: 400, color: '#9ca3af' }}
                              className="dark:text-slate-500">
                              ({groups[dateKey].length})
                            </span>
                          </div>
                          {/* Articles in this group */}
                          {groups[dateKey].map((article: any) => {
                            const isSelected = selectedArticleIds.includes(article.id);
                            return (
                              <div
                                key={article.id}
                                onClick={() => toggleArticle(article.id)}
                                style={{
                                  display: 'flex', alignItems: 'flex-start', gap: '0.5rem',
                                  padding: '0.5rem 0.75rem', cursor: selectedArticleIds.length < maxArticles || isSelected ? 'pointer' : 'not-allowed',
                                  background: isSelected ? '#fff7ed' : 'transparent',
                                  borderBottom: '1px solid #f3f4f6',
                                  opacity: (!isSelected && selectedArticleIds.length >= maxArticles) ? 0.4 : 1,
                                }}
                                className="dark:bg-slate-800 dark:border-slate-700 dark:bg-opacity-50"
                              >
                                {/* Checkbox */}
                                <div style={{
                                  width: 16, height: 16, borderRadius: 4, flexShrink: 0, marginTop: 2,
                                  border: isSelected ? '2px solid #f97316' : '2px solid #d1d5db',
                                  background: isSelected ? '#f97316' : 'white',
                                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                                }}
                                className="dark:border-slate-500 dark:bg-slate-800">
                                  {isSelected && (
                                    <svg width={12} height={12} viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth={3}>
                                      <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                                    </svg>
                                  )}
                                </div>

                                {/* Article info */}
                                <div style={{ flex: 1, minWidth: 0 }}>
                                  <div style={{
                                    fontSize: '0.8125rem', fontWeight: 600, color: '#111827',
                                    whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
                                  }}
                                  className="dark:text-gray-200">
                                    {article.title || 'Untitled'}
                                  </div>
                                  <div style={{ display: 'flex', gap: '0.75rem', fontSize: '0.6875rem', color: '#9ca3af', marginTop: 2 }}
                                    className="dark:text-slate-400">
                                    {article.provider_name && (
                                      <span style={{
                                        display: 'inline-block', padding: '1px 6px', borderRadius: 4,
                                        background: '#e5e7eb', fontSize: '0.625rem', fontWeight: 500,
                                      }}
                                      className="dark:bg-slate-700 dark:text-gray-300">
                                        {article.provider_name}
                                      </span>
                                    )}
                                    {article.pub_date && <span>{new Date(article.pub_date).toLocaleDateString()}</span>}
                                  </div>
                                </div>
                              </div>
                            );
                          })}
                        </div>
                      ))}
                    </>
                  );
                })()
              )}
            </div>
          </div>
        )}

        {/* Generate Button */}
        <button
          onClick={handleGenerateAnalysis}
          disabled={generating || !selectedModel || !selectedTicker}
          style={{
            padding: '0.75rem 2rem', borderRadius: '8px', border: 'none',
            background: generating || !selectedModel || !selectedTicker ? '#9ca3af' : '#f97316',
            color: 'white', fontSize: '1rem', fontWeight: 600,
            cursor: generating || !selectedModel || !selectedTicker ? 'not-allowed' : 'pointer',
            width: '100%',
          }}
        >
          {generating ? 'Generating Analysis Report...' : `Start AI Generated Analysis Report (${selectedArticleIds.length > 0 ? selectedArticleIds.length + ' articles' : 'auto-select'})`}
        </button>

        {/* Error */}
        {genError && (
          <div style={{
            marginTop: '1rem', padding: '0.75rem 1rem', borderRadius: '8px',
            background: '#fef2f2', border: '1px solid #fecaca', color: '#dc2626', fontSize: '0.875rem',
          }}
          className="dark:bg-red-900/30 dark:border-red-800 dark:text-red-400">
            <strong>Error:</strong> {genError}
          </div>
        )}
      </div>

      {/* ============================================================ */}
      {/* SECTION: My Reports (Saved) - Container Wrapper              */}
      {/* ============================================================ */}
      <div style={{
        padding: '1.5rem', borderRadius: '12px', marginBottom: '2rem',
        background: '#f9fafb', border: '1px solid #e5e7eb',
      }}
      className="dark:bg-slate-800 dark:border-slate-700">
        <h1 style={{ margin: '0 0 1rem', fontSize: '1.25rem', fontWeight: 700, color: '#374151' }}
          className="dark:text-white">
          Generated Analysis Reports
        </h1>

        {/* Filters */}
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.75rem', marginBottom: '1.5rem', alignItems: 'center' }}>
          <input
            type="text"
            placeholder="Ticker..."
            value={tickerFilter}
            onChange={e => { setTickerFilter(e.target.value); setPage(1); }}
            style={{
              padding: '0.5rem 0.75rem', borderRadius: '6px', border: '1px solid #d1d5db',
              fontSize: '0.875rem', outline: 'none', minWidth: '120px',
              background: 'white', color: '#374151',
            }}
            className="dark:bg-slate-900 dark:border-slate-600 dark:text-gray-200"
          />

          <select
            value={sort}
            onChange={e => setSort(e.target.value as 'newest' | 'oldest')}
            style={{
              padding: '0.5rem 0.75rem', borderRadius: '6px', border: '1px solid #d1d5db',
              fontSize: '0.875rem', outline: 'none', background: 'white', color: '#374151',
            }}
            className="dark:bg-slate-900 dark:border-slate-600 dark:text-gray-200"
          >
            <option value="newest">Newest First</option>
            <option value="oldest">Oldest First</option>
          </select>

          {hasActiveFilters && (
            <button onClick={resetFilters} style={{
              padding: '0.5rem 0.75rem', borderRadius: '6px', border: 'none',
              background: '#e5e7eb', color: '#374151', fontSize: '0.875rem', cursor: 'pointer', fontWeight: 600,
            }}
            className="dark:bg-slate-700 dark:text-gray-200">
              Clear
            </button>
          )}

          <span style={{ fontSize: '0.875rem', color: '#6b7280', marginLeft: 'auto' }}
            className="dark:text-slate-400">
            {total} report{total !== 1 ? 's' : ''} found
          </span>
        </div>

        {/* Fetch Error Banner */}
        {fetchError && (
          <div style={{
            marginBottom: '1rem', padding: '0.75rem 1rem', borderRadius: '8px',
            background: '#fef2f2', border: '1px solid #fecaca', color: '#dc2626', fontSize: '0.875rem',
          }}
          className="dark:bg-red-900/30 dark:border-red-800 dark:text-red-400">
            <strong>Error:</strong> {fetchError}
          </div>
        )}

        {/* Report List */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
          {loading && reports.length === 0 ? (
            Array.from({ length: 4 }).map((_, i) => (
              <div key={i} style={{ padding: '1rem', borderRadius: '8px', background: '#f3f4f6', border: '1px solid #e5e7eb' }}
                className="dark:bg-slate-800 dark:border-slate-700">
                Loading...
              </div>
            ))
          ) : reports.length === 0 ? (
            <div style={{ padding: '2rem', borderRadius: '8px', background: '#f9fafb', textAlign: 'center', color: '#6b7280' }}
              className="dark:bg-slate-800 dark:text-slate-400">
              No reports found. Generate your first analysis using the form above.
            </div>
          ) : (
            reports.map((report) => (
              <div
                key={report.id}
                style={{
                  display: 'flex', alignItems: 'center', gap: '1rem',
                  padding: '1rem', borderRadius: '8px',
                  background: 'white', border: '1px solid #e5e7eb', cursor: 'pointer',
                  transition: 'box-shadow 0.15s ease, background 0.15s ease',
                }}
                className="dark:bg-slate-800 dark:border-slate-700"
                onClick={() => router.push(`/analysis/reports/${report.id}`)}
                onMouseEnter={e => { e.currentTarget.style.boxShadow = '0 2px 8px rgba(0,0,0,0.1)'; }}
                onMouseLeave={e => { e.currentTarget.style.boxShadow = 'none'; }}
              >
                {/* Descriptive report label */}
                <div style={{ minWidth: '170px' }}>
                  <div style={{ fontWeight: 700, fontSize: '1.125rem', color: '#111827' }}
                    className="dark:text-white">
                    {report.ticker} Analysis
                  </div>
                  <div style={{ marginTop: 2, fontSize: '0.75rem', color: '#6b7280' }}
                    className="dark:text-slate-400">
                    {formatReportDateTime(report.created_at)}
                  </div>
                </div>

                {/* Sentiment badge */}
                <span style={{
                  padding: '0.25rem 0.75rem', borderRadius: '999px',
                  background: getSentimentColor(report.overall_sentiment),
                  color: 'white', fontSize: '0.75rem', fontWeight: 600, whiteSpace: 'nowrap',
                }}>
                  {report.overall_sentiment}
                </span>

                {/* Confidence bar */}
                <div style={{ flex: 1, maxWidth: '160px' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.75rem', color: '#6b7280', marginBottom: '2px' }}
                    className="dark:text-slate-400">
                    <span>Confidence</span>
                    <span style={{ fontWeight: 600 }}>{report.confidence_score}%</span>
                  </div>
                  <div style={{ height: 4, borderRadius: 2, background: '#e5e7eb', overflow: 'hidden' }}
                    className="dark:bg-slate-600">
                    <div style={{
                      width: `${report.confidence_score}%`, height: '100%', borderRadius: 2,
                      background: report.confidence_score > 70 ? '#10b981' : report.confidence_score > 40 ? '#f59e0b' : '#ef4444',
                    }} />
                  </div>
                </div>

                {/* Price */}
                {report.current_price_at_analysis != null && (
                  <div style={{ fontSize: '0.875rem', color: '#374151', fontWeight: 500 }}
                    className="dark:text-gray-300">
                    ${Number(report.current_price_at_analysis).toFixed(2)}
                  </div>
                )}

                {/* Articles count */}
                <div style={{ fontSize: '0.75rem', color: '#9ca3af' }}
                  className="dark:text-slate-500">
                  {report.articles_count} articles
                </div>

                {/* Prompt version & model */}
                <div style={{ textAlign: 'right', fontSize: '0.75rem', color: '#9ca3af' }}
                  className="dark:text-slate-500">
                  <div style={{ fontWeight: 600, color: report.prompt_hash ? '#7c3aed' : '#9ca3af' }}>
                    {getPromptBadge(report.prompt_version, report.prompt_hash)}
                  </div>
                  <div>{report.model_used}</div>
                </div>

                {/* Delete button */}
                <button
                  onClick={(e) => { e.stopPropagation(); handleDeleteReport(report.id); }}
                  style={{
                    padding: '0.25rem 0.5rem', borderRadius: '4px', border: '1px solid #fca5a5',
                    background: 'transparent', color: '#ef4444', fontSize: '0.75rem', cursor: 'pointer',
                    display: 'flex', alignItems: 'center',
                  }}
                  className="dark:border-red-800 dark:text-red-500"
                  title="Delete report"
                >
                  <svg width="16" height="16" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                  </svg>
                </button>

                {/* Arrow */}
                <svg width="16" height="16" style={{ color: '#9ca3af', minWidth: '16px' }} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
                </svg>
              </div>
            ))
          )}
        </div>

        {/* Pagination */}
        {reports.length > 0 && (
          <div style={{ display: 'flex', justifyContent: 'center', gap: '0.5rem', marginTop: '1.5rem' }}>
            <button
              onClick={() => setPage(p => Math.max(1, p - 1))}
              disabled={page <= 1 || loading}
              style={{
                padding: '0.5rem 1rem', borderRadius: '6px', border: '1px solid #d1d5db',
                background: page <= 1 ? '#f3f4f6' : 'white', cursor: page <= 1 ? 'not-allowed' : 'pointer',
                fontSize: '0.875rem', color: '#374151',
              }}
              className="dark:bg-slate-800 dark:border-slate-600 dark:text-gray-200 dark:disabled:bg-slate-700"
            >
              ← Previous
            </button>

            <span style={{ padding: '0.5rem 1rem', fontSize: '0.875rem', color: '#6b7280' }}
              className="dark:text-slate-400">
              Page {page}
            </span>

            <button
              onClick={() => setPage(p => p + 1)}
              disabled={!hasMore || loading}
              style={{
                padding: '0.5rem 1rem', borderRadius: '6px', border: '1px solid #d1d5db',
                background: !hasMore ? '#f3f4f6' : 'white', cursor: !hasMore ? 'not-allowed' : 'pointer',
                fontSize: '0.875rem', color: '#374151',
              }}
              className="dark:bg-slate-800 dark:border-slate-600 dark:text-gray-200 dark:disabled:bg-slate-700"
            >
              Next →
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
