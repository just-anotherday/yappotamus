# YapVibes Environment Variable Conventions

## Naming Convention

All environment variables follow a consistent naming pattern across applications:

```
YAPVIBES_{APP}_{SERVICE}_{VARIABLE}
```

Where:
- `APP` = the application name (PROJECTS, STOCKS, WEBSITE)
- `SERVICE` = the service type (DB, API, AUTH, etc.)
- `VARIABLE` = the specific variable name

## Current Application Variables

### Projects App (`apps/projects/.env`)

| Variable | Description | Example |
|----------|-------------|---------|
| `VITE_SUPABASE_URL` | Supabase project URL | `https://xxx.supabase.co` |
| `VITE_SUPABASE_ANON_KEY` | Supabase anonymous key | `eyJ...` |

### Stocks App (`apps/stocks/.env`)

| Variable | Description | Example |
|----------|-------------|---------|
| `DATABASE_URL` | PostgreSQL connection string | `postgresql://user:pass@host/db` |
| `OPENAI_API_KEY` | OpenAI API key | `sk-xxx` |
| `NEWS_API_KEY` | News API key | `xxx` |

### Website App (`apps/website/`)

| Variable | Description | Example |
|----------|-------------|---------|
| (defined in Cloudflare workers/dev vars) | Vercel/Cloudflare deployment vars | N/A |

## Conventions

1. **Prefix**: Each app uses its own framework-specific prefix:
   - Vite apps: `VITE_`
   - Next.js apps: `NEXT_PUBLIC_` (for client-side variables)
   - Backend services: no prefix needed (server-only)

2. **File Location**: Environment files are always located at the app root:
   ```
   apps/{app-name}/.env          # Local development
   apps/{app-name}/.env.example  # Template with placeholder values
   ```

3. **Git Ignore**: All `.env` files are ignored by git. Each app includes its own `.gitignore`.

4. **Required vs Optional**: Required variables should be documented in the app's README.

## Migration Note

Existing environment variable names have NOT been changed to preserve functionality. The convention above is for future reference when adding new variables or creating shared packages.
