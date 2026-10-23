'use client';

import { useEffect, useState, useRef } from 'react';
import { API_BASE } from '@/lib/serviceUrls';
import { apiFetch } from '@/lib/apiFetch';
import { requireOk } from '@/lib/apiError';
import { useAnalysisStatus } from '@/hooks/useAnalysisStatus';
import ArticleSelectionMeter from '@/components/ArticleSelectionMeter';
import { easternDayLabel, formatApiTimestamp } from '@/lib/formatters';
import { PROMPT_VERSION_OPTIONS, promptVersionRequestFields, type PromptVersion } from '@/lib/promptVersionSelector';

interface GenerationProvider {
  id: string;
  name: string;
  available: boolean;
  models: Array<{ name: string } | string>;
}
interface GenerationArticle {
  id: number;
  title: string | null;
  summary: string | null;
  provider_name: string | null;
  pub_date: string | null;
}
interface CoverageCompany { ticker: string; symbol?: string; company_name?: string | null }
const modelName = (model: GenerationProvider['models'][number]) => typeof model === 'string' ? model : model.name;

export default function ReportGenerator({ onGenerated, onCompanyNames }: {
  onGenerated: () => void;
  onCompanyNames: (names: Record<string, string>) => void;
}) {
  const { setAnalyzing, clearAnalyzing } = useAnalysisStatus();
  // ---- Generate new analysis state ----
  const [providers, setProviders] = useState<GenerationProvider[]>([]);
  const [selectedProvider, setSelectedProvider] = useState<string>('ollama');
  const [selectedModel, setSelectedModel] = useState<string>('');
  const [selectedPromptVersion, setSelectedPromptVersion] = useState<PromptVersion>('2.0');
  const [selectedTicker, setSelectedTicker] = useState<string>('');
  const [watchlistTickers, setWatchlistTickers] = useState<string[]>([]);
  const [generating, setGenerating] = useState(false);
  const [genError, setGenError] = useState<string | null>(null);

   // ---- Article picker state ----
   const [availableArticles, setAvailableArticles] = useState<GenerationArticle[]>([]);
   const [selectedArticleIds, setSelectedArticleIds] = useState<number[]>([]);
   const [daysBack, setDaysBack] = useState(3);
   const [maxArticles, setMaxArticles] = useState(50);
   const [loadingArticles, setLoadingArticles] = useState(false);
   const [articleSearch, setArticleSearch] = useState('');
   const [articleGroupingNow, setArticleGroupingNow] = useState(0);
   const maxArticlesRef = useRef(maxArticles);
   useEffect(() => { maxArticlesRef.current = maxArticles; }, [maxArticles]);

   const changeTicker = (ticker: string) => {
     setSelectedTicker(ticker);
     setAvailableArticles([]);
     setSelectedArticleIds([]);
     setArticleGroupingNow(0);
     setLoadingArticles(Boolean(ticker));
   };

  // ---- Load generation dependencies only when the form is opened ----
  useEffect(() => {
    // Fetch available providers and models
    apiFetch(`${API_BASE}/api/analysis/providers`)
      .then(res => res.json())
      .then((data: { providers?: GenerationProvider[] }) => {
        setProviders(data.providers || []);
        // Auto-select first available provider with models, prefer online over offline
        if (data.providers && data.providers.length > 0) {
          // Prefer an available provider; fallback to any provider as last resort
          const availableList = data.providers.filter((p) => p.available);
          const pool = availableList.length > 0 ? availableList : data.providers;
          const chosen = pool.find((p) => p.models?.length > 0) || pool[0];
          if (chosen) {
            setSelectedProvider(chosen.id);
            if (chosen.models && chosen.models.length > 0) {
              setSelectedModel(modelName(chosen.models[0]));
            }
          } else {
            setSelectedModel('llama3.2');
          }
        } else {
          setSelectedModel('llama3.2');
        }
      })
      .catch(() => setProviders([]));

    // The form needs saved ticker names, not a live quote for every company.
    apiFetch(`${API_BASE}/api/analysis/reports/coverage`)
      .then(async res => {
        await requireOk(res, 'Unable to load watchlist');
        return res.json();
      })
      .then((data: { items?: CoverageCompany[] }) => {
        if (Array.isArray(data.items)) {
          setWatchlistTickers(data.items.map((item) => item.ticker));
          onCompanyNames(Object.fromEntries(data.items
            .filter((item) => (item.ticker || item.symbol) && item.company_name)
            .map((item) => [item.ticker || item.symbol, item.company_name])));
        }
      })
      .catch(() => setWatchlistTickers([]));
  }, [onCompanyNames]);

  // ---- Fetch available articles when ticker/daysBack changes ----
  useEffect(() => {
    if (!selectedTicker) return;
    const controller = new AbortController();
    const timer = setTimeout(() => {
      void (async () => {
        setLoadingArticles(true);
        try {
          const res = await apiFetch(
            `${API_BASE}/api/analysis/articles/${selectedTicker.toUpperCase()}?days_back=${daysBack}`,
            { signal: controller.signal }
          );
          await requireOk(res, 'Failed to fetch articles');
          const data: { articles?: GenerationArticle[] } = await res.json();
          if (controller.signal.aborted) return;
          setAvailableArticles(data.articles || []);
          setArticleGroupingNow(Date.now());
          // Auto-select up to the current max by default
          const ids = (data.articles || []).slice(0, maxArticlesRef.current).map((a) => a.id);
          setSelectedArticleIds(ids);
        } catch (e) {
          if (!controller.signal.aborted) {
            console.error('[Articles] Fetch error:', e);
          }
        } finally {
          if (!controller.signal.aborted) setLoadingArticles(false);
        }
      })();
    }, 0);
    return () => { clearTimeout(timer); controller.abort(); };
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
    setSelectedArticleIds(availableArticles.slice(0, maxArticles).map((a) => a.id));
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
            ...promptVersionRequestFields(
              selectedPromptVersion,
            ),
            article_ids: selectedArticleIds.length > 0 ? selectedArticleIds : undefined,
          }),
      });

      await requireOk(response, 'Analysis failed');

      onGenerated();
    } catch (e) {
      setGenError(e instanceof Error ? e.message : 'Unknown error');
    } finally {
      setGenerating(false);
      clearAnalyzing();
    }
  };

  return (
      <div id="report-generator" style={{
        padding: '1.5rem', borderRadius: '12px', marginBottom: '2rem',
        background: 'linear-gradient(135deg, var(--accent-soft), var(--card-bg))',
        border: '1px solid var(--accent-border)',
      }}
      className="dark:bg-gradient-to-br dark:from-slate-800 dark:to-slate-900 dark:border-slate-700">
        <h2 style={{ margin: '0 0 1rem', fontSize: '1.25rem', fontWeight: 700, color: 'var(--text-secondary)' }}
          className="dark:text-white">
          Generate New Analysis Report
        </h2>

        {/* Step 1: Select Watchlist Ticker */}
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '1rem', alignItems: 'center', marginBottom: '1rem' }}>
          <label htmlFor="ticker-select" style={{ fontSize: '0.875rem', fontWeight: 500, color: 'var(--text-secondary)', minWidth: '80px' }}
            className="dark:text-gray-300">
            1. Ticker:
          </label>
          <select
            id="ticker-select"
            value={selectedTicker}
            onChange={(e) => changeTicker(e.target.value)}
            disabled={generating}
            style={{
              padding: '0.5rem 1rem', borderRadius: '8px', border: '1px solid var(--card-border)',
              background: 'var(--card-bg)', fontSize: '0.875rem', fontWeight: 500, color: 'var(--text-secondary)',
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
          <label htmlFor="provider-select" style={{ fontSize: '0.875rem', fontWeight: 500, color: 'var(--text-secondary)', minWidth: '80px' }}
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
              const prov = providers.find((p) => p.id === newProvider);
              if (prov && prov.models.length > 0) {
                setSelectedModel(modelName(prov.models[0]));
              } else {
                setSelectedModel('');
              }
            }}
            disabled={generating}
            style={{
              padding: '0.5rem 1rem', borderRadius: '8px', border: '1px solid var(--card-border)',
              background: 'var(--card-bg)', fontSize: '0.875rem', fontWeight: 500, color: 'var(--text-secondary)',
              minWidth: 120,
              opacity: generating ? 0.5 : 1,
              cursor: generating ? 'not-allowed' : 'pointer',
            }}
            className="dark:bg-slate-800 dark:border-slate-600 dark:text-gray-200"
          >
           {providers.map((p) => (
               <option key={p.id} value={p.id} disabled={!p.available}>
                 {p.name} {!p.available ? '(offline)' : ''}
               </option>
             ))}
            {providers.length === 0 && (
              <option value="ollama">ollama (default)</option>
            )}
          </select>

          {/* Provider status indicators */}
          {providers.map((p) => (
            <span key={p.id} style={{
              display: 'inline-flex', alignItems: 'center', gap: '0.4rem',
              fontSize: '0.75rem', color: p.available ? 'var(--positive)' : 'var(--negative)',
            }}
            className="dark:text-muted">
              <span style={{
                width: 8, height: 8, borderRadius: '50%', display: 'inline-block',
                background: p.available ? '#166b52' : '#b1364e',
              }} />
              {p.name} {p.available ? 'Ready' : 'Offline'}
            </span>
          ))}
        </div>

        {/* Step 2b: Model Selector (indented under provider) */}
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '1rem', alignItems: 'center', marginBottom: '1rem' }}>
          <label htmlFor="model-select" style={{ fontSize: '0.875rem', fontWeight: 500, color: 'var(--text-secondary)', minWidth: '80px' }}
            className="dark:text-gray-300">
            Model:
          </label>
          <select
            id="model-select"
            value={selectedModel}
            onChange={(e) => setSelectedModel(e.target.value)}
            disabled={generating}
            style={{
              padding: '0.5rem 1rem', borderRadius: '8px', border: '1px solid var(--card-border)',
              background: 'var(--card-bg)', fontSize: '0.875rem', fontWeight: 500, color: 'var(--text-secondary)',
              minWidth: 200,
              opacity: generating ? 0.5 : 1,
              cursor: generating ? 'not-allowed' : 'pointer',
            }}
            className="dark:bg-slate-800 dark:border-slate-600 dark:text-gray-200"
          >
            <option value="">— Select a model —</option>
            {(() => {
              const selectedProv = providers.find((p) => p.id === selectedProvider);
              const models = selectedProv?.models || [];
              return models.map((m) => (
                <option key={modelName(m)} value={modelName(m)}>{modelName(m)}</option>
              ));
            })()}
          </select>
        </div>

          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '1rem', alignItems: 'center', marginBottom: '1rem' }}>
            <label htmlFor="prompt-version-select" style={{ fontSize: '0.875rem', fontWeight: 500, color: 'var(--text-secondary)', minWidth: '80px' }}
              className="dark:text-gray-300">
              Prompt Version:
            </label>
            <select
              id="prompt-version-select"
              value={selectedPromptVersion}
              onChange={(event) => setSelectedPromptVersion(event.target.value as PromptVersion)}
              disabled={generating}
              style={{
                padding: '0.5rem 1rem', borderRadius: '8px', border: '1px solid var(--card-border)',
                background: 'var(--card-bg)', fontSize: '0.875rem', fontWeight: 500, color: 'var(--text-secondary)',
                minWidth: 220,
                opacity: generating ? 0.5 : 1,
                cursor: generating ? 'not-allowed' : 'pointer',
              }}
              className="dark:bg-slate-800 dark:border-slate-600 dark:text-gray-200"
            >
              {PROMPT_VERSION_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>{option.label}</option>
              ))}
            </select>
          </div>
        {/* Step 3: Days Back Slider */}
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '1rem', alignItems: 'center', marginBottom: '1rem' }}>
          <label htmlFor="days-back" style={{ fontSize: '0.875rem', fontWeight: 500, color: 'var(--text-secondary)', minWidth: '80px' }}
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
          <span style={{ fontSize: '0.875rem', fontWeight: 600, color: 'var(--accent)', minWidth: 40 }}
            className="dark:text-accent">
            {daysBack} day{daysBack > 1 ? 's' : ''}
          </span>
        </div>

        {/* Step 4: Article Picker */}
        {selectedTicker && (
          <div style={{ marginBottom: '1rem' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '1rem', marginBottom: '0.75rem', flexWrap: 'wrap' }}>
              <label style={{ fontSize: '0.875rem', fontWeight: 500, color: 'var(--text-secondary)' }}
                className="dark:text-gray-300">
                4. Select Articles
              </label>
              <div style={{ display: 'flex', gap: '0.5rem' }}>
                <button
                  onClick={selectAllArticles}
                  disabled={loadingArticles || selectedArticleIds.length >= maxArticles}
                  style={{
                    padding: '0.25rem 0.5rem', borderRadius: '4px', border: '1px solid var(--card-border)',
                    background: 'var(--card-bg)', fontSize: '0.75rem', cursor: 'pointer', color: 'var(--text-secondary)',
                  }}
                  className="dark:bg-slate-800 dark:border-slate-600 dark:text-gray-200"
                >
                  Select All
                </button>
                <button
                  onClick={clearAllArticles}
                  disabled={loadingArticles}
                  style={{
                    padding: '0.25rem 0.5rem', borderRadius: '4px', border: '1px solid var(--card-border)',
                    background: 'var(--card-bg)', fontSize: '0.75rem', cursor: 'pointer', color: 'var(--text-secondary)',
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
                width: '100%', padding: '0.5rem 0.75rem', borderRadius: '6px', border: '1px solid var(--card-border)',
                fontSize: '0.8125rem', outline: 'none', marginBottom: '0.5rem', boxSizing: 'border-box',
                background: 'var(--card-bg)', color: 'var(--text-secondary)',
              }}
              className="dark:bg-slate-800 dark:border-slate-600 dark:text-gray-200"
            />

            <div style={{
              maxHeight: 320, overflowY: 'auto', borderRadius: '8px', border: '1px solid var(--card-border)',
              background: 'var(--section-bg)',
            }}
            className="dark:bg-slate-900 dark:border-slate-600">
              {loadingArticles ? (
                <div style={{ padding: '2rem', textAlign: 'center', color: 'var(--text-muted)' }}>Loading articles...</div>
              ) : availableArticles.length === 0 ? (
                <div style={{ padding: '2rem', textAlign: 'center', color: 'var(--text-muted)' }}>
                  No articles found for {selectedTicker} in the last {daysBack} day{daysBack > 1 ? 's' : ''}
                </div>
              ) : (
                (() => {
                  // Filter by search
                  const filtered = availableArticles.filter((a) => {
                    if (!articleSearch) return true;
                    const q = articleSearch.toLowerCase();
                    return (a.title || '').toLowerCase().includes(q) ||
                           (a.provider_name || '').toLowerCase().includes(q) ||
                           (a.summary || '').toLowerCase().includes(q);
                  });

                  // Group by date
                  const groups: Record<string, GenerationArticle[]> = {};
                  filtered.forEach((a) => {
                    const dateKey = easternDayLabel(a.pub_date, articleGroupingNow);
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
                            color: 'var(--text-muted)', background: 'var(--section-bg)', borderBottom: '1px solid var(--card-border)',
                            display: 'flex', alignItems: 'center', gap: '0.5rem',
                          }}
                          className="dark:bg-slate-800 dark:border-slate-700 dark:text-slate-400">
                            <span>{dateKey}</span>
                            <span style={{ fontSize: '0.625rem', fontWeight: 400, color: 'var(--text-muted)' }}
                              className="dark:text-slate-500">
                              ({groups[dateKey].length})
                            </span>
                          </div>
                          {/* Articles in this group */}
                          {groups[dateKey].map((article) => {
                            const isSelected = selectedArticleIds.includes(article.id);
                            return (
                              <div
                                key={article.id}
                                onClick={() => toggleArticle(article.id)}
                                style={{
                                  display: 'flex', alignItems: 'flex-start', gap: '0.5rem',
                                  padding: '0.5rem 0.75rem', cursor: selectedArticleIds.length < maxArticles || isSelected ? 'pointer' : 'not-allowed',
                                  background: isSelected ? 'var(--accent-soft)' : 'transparent',
                                  borderBottom: '1px solid var(--section-bg)',
                                  opacity: (!isSelected && selectedArticleIds.length >= maxArticles) ? 0.4 : 1,
                                }}
                                className="dark:bg-slate-800 dark:border-slate-700 dark:bg-opacity-50"
                              >
                                {/* Checkbox */}
                                <div style={{
                                  width: 16, height: 16, borderRadius: 4, flexShrink: 0, marginTop: 2,
                                  border: isSelected ? '2px solid var(--action)' : '2px solid var(--card-border)',
                                  background: isSelected ? 'var(--action)' : 'white',
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
                                    fontSize: '0.8125rem', fontWeight: 600, color: 'var(--text-primary)',
                                    whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
                                  }}
                                  className="dark:text-gray-200">
                                    {article.title || 'Untitled'}
                                  </div>
                                  <div style={{ display: 'flex', gap: '0.75rem', fontSize: '0.6875rem', color: 'var(--text-muted)', marginTop: 2 }}
                                    className="dark:text-slate-400">
                                    {article.provider_name && (
                                      <span style={{
                                        display: 'inline-block', padding: '1px 6px', borderRadius: 4,
                                        background: 'var(--card-border)', fontSize: '0.625rem', fontWeight: 500,
                                      }}
                                      className="dark:bg-slate-700 dark:text-gray-300">
                                        {article.provider_name}
                                      </span>
                                    )}
                                    {article.pub_date && <span>{formatApiTimestamp(article.pub_date, { year: 'numeric', month: 'numeric', day: 'numeric' })}</span>}
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
            background: generating || !selectedModel || !selectedTicker ? 'var(--text-muted)' : 'var(--action)',
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
            background: 'var(--negative-soft)', border: '1px solid var(--negative-border)', color: 'var(--negative)', fontSize: '0.875rem',
          }}
          className="dark:bg-negative-soft/30 dark:border-negative-border dark:text-negative">
            <strong>Error:</strong> {genError}
          </div>
        )}
      </div>

  );
}
