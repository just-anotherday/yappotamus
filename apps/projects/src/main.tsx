import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'
import { AuthProvider } from './context/AuthProvider.tsx'
import { AuthenticatedUserSettingsProvider } from './context/AuthenticatedUserSettingsProvider.tsx'
import { AuthenticatedNotificationProvider } from './context/AuthenticatedNotificationProvider.tsx'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <AuthProvider>
      <AuthenticatedUserSettingsProvider>
        <AuthenticatedNotificationProvider>
          <App />
        </AuthenticatedNotificationProvider>
      </AuthenticatedUserSettingsProvider>
    </AuthProvider>
  </StrictMode>,
)
