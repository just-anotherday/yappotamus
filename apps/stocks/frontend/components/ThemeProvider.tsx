'use client';

import { ThemeProvider as ThemeContextProvider, useTheme } from '@/hooks/useTheme';
import React, { type ReactNode } from 'react';

export default function ThemeProvider({ children }: { children: ReactNode }) {
  return <ThemeContextProvider>{children}</ThemeContextProvider>;
}

export { useTheme };
