'use client';

import { createContext, useContext } from 'react';

export const SessionControlsContext = createContext<{
  signOut: () => Promise<void>;
  busy: boolean;
} | null>(null);

export const useSessionControls = () => useContext(SessionControlsContext);
