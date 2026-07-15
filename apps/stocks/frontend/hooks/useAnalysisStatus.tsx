'use client';

import React, { createContext, useContext, useState, useCallback } from 'react';

interface AnalysisStatusContextType {
  isAnalyzing: boolean;
  analyzingTicker: string | null;
  setAnalyzing: (ticker: string) => void;
  clearAnalyzing: () => void;
}

const AnalysisStatusContext = createContext<AnalysisStatusContextType>({
  isAnalyzing: false,
  analyzingTicker: null,
  setAnalyzing: () => {},
  clearAnalyzing: () => {},
});

export function AnalysisStatusProvider({ children }: { children: React.ReactNode }): React.ReactElement {
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [analyzingTicker, setAnalyzingTickerState] = useState<string | null>(null);

  const setAnalyzing = useCallback((ticker: string) => {
    setIsAnalyzing(true);
    setAnalyzingTickerState(ticker.toUpperCase());
  }, []);

  const clearAnalyzing = useCallback(() => {
    setIsAnalyzing(false);
    setAnalyzingTickerState(null);
  }, []);

  return (
    <AnalysisStatusContext.Provider value={{ isAnalyzing, analyzingTicker, setAnalyzing, clearAnalyzing }}>
      {children}
    </AnalysisStatusContext.Provider>
  );
}

export function useAnalysisStatus() {
  return useContext(AnalysisStatusContext);
}
