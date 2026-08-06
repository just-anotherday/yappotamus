import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'
import { AuthProvider } from './context/AuthProvider.tsx'
import { AuthenticatedUserSettingsProvider } from './context/AuthenticatedUserSettingsProvider.tsx'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <AuthProvider>
      <AuthenticatedUserSettingsProvider>
        <App />
      </AuthenticatedUserSettingsProvider>
    </AuthProvider>
  </StrictMode>,
)
