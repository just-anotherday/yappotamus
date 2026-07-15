'use client';

import React, { createContext, useContext, useState, useEffect, useCallback, useRef } from 'react';

type Theme = 'light' | 'dark';

interface ThemeContextType {
  theme: Theme;
  toggleTheme: () => void;
}

const ThemeContext = createContext<ThemeContextType>({ theme: 'dark', toggleTheme: () => {} });

export function ThemeProvider({ children }: { children: React.ReactNode }): React.JSX.Element {
  const [theme, setTheme] = useState<Theme>('dark');
  const initialized = useRef(false);

  // Load saved theme from localStorage on mount (no SSR flicker)
  useEffect(() => {
    try {
      const saved = localStorage.getItem('theme') as Theme | null;
      if (saved === 'light' || saved === 'dark') {
        setTheme(saved);
      }
    } catch {
      // ignore storage errors
    }
    initialized.current = true;
  }, []);

  // Apply the dark class to <html> so Tailwind dark: variants work
  useEffect(() => {
    const root = document.documentElement;
    if (theme === 'dark') {
      root.classList.add('dark');
      root.style.colorScheme = 'dark';
    } else {
      root.classList.remove('dark');
      root.style.colorScheme = 'light';
    }
  }, [theme]);

  const toggleTheme = useCallback(() => {
    setTheme(prev => {
      const next = prev === 'dark' ? 'light' : 'dark';
      try { localStorage.setItem('theme', next); } catch { /* ignore */ }
      return next;
    });
  }, []);

  return (
    <ThemeContext.Provider value={{ theme, toggleTheme }}>
      {children}
    </ThemeContext.Provider>
  );
}

export function useTheme(): ThemeContextType {
  return useContext(ThemeContext);
}
