'use client';

import React, { createContext, useContext, useEffect, useCallback, useSyncExternalStore } from 'react';

type Theme = 'light' | 'dark';

interface ThemeContextType {
  theme: Theme;
  toggleTheme: () => void;
}

const ThemeContext = createContext<ThemeContextType>({ theme: 'dark', toggleTheme: () => {} });

let volatileTheme: Theme = 'dark';
const THEME_CHANGED = 'yapvibes:theme-changed';

function themeSnapshot(): Theme {
  try {
    const saved = localStorage.getItem('theme');
    if (saved === 'light' || saved === 'dark') return saved;
  } catch { /* Keep theme controls usable when browser storage is blocked. */ }
  return volatileTheme;
}
function subscribeToTheme(onChange: () => void) {
  window.addEventListener('storage', onChange);
  window.addEventListener(THEME_CHANGED, onChange);
  return () => {
    window.removeEventListener('storage', onChange);
    window.removeEventListener(THEME_CHANGED, onChange);
  };
}
const serverTheme = (): Theme => 'dark';

export function ThemeProvider({ children }: { children: React.ReactNode }): React.JSX.Element {
  const theme = useSyncExternalStore(subscribeToTheme, themeSnapshot, serverTheme);

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
    volatileTheme = themeSnapshot() === 'dark' ? 'light' : 'dark';
    try { localStorage.setItem('theme', volatileTheme); } catch { /* Memory fallback. */ }
    window.dispatchEvent(new Event(THEME_CHANGED));
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
