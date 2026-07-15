# YapVibes Monorepo

A consolidated workspace containing three independent applications managed under a single repository using npm workspaces.

## Project Structure

```
YapVibes/
├── apps/
│   ├── website/          # Landing page (Next.js + Python backend)
│   ├── projects/         # Projects/Tasks app (React + Vite + TypeScript + Supabase)
│   └── stocks/           # Stock Data Dashboard (Next.js frontend + FastAPI backend)
│
├── packages/             # Shared libraries (coming soon)
│   ├── ui/
│   ├── types/
│   ├── shared/
│   └── config/
│
├── docs/                 # Documentation
│
├── package.json          # Root workspace configuration
└── .gitignore            # Global git ignore rules
```

## Applications

### Website (`apps/website`)
- **Frontend:** Next.js (located in `frontend/app`)
- **Backend:** Python AI generator (`backend/ai-generator-backend`)
- **Purpose:** Landing page and marketing site

### Projects (`apps/projects`)
- **Framework:** React + Vite + TypeScript
- **Styling:** Tailwind CSS
- **Backend:** Supabase
- **Purpose:** Project and task management application

### Stocks (`apps/stocks`)
- **Frontend:** Next.js (located in `frontend/`)
- **Backend:** FastAPI + Python (located in `backend/`)
- **Database:** PostgreSQL with Alembic migrations
- **Purpose:** Stock analysis and data dashboard

## Getting Started

### Prerequisites
- Node.js 18+ 
- npm 9+
- Python 3.10+ (for stocks backend)
- PostgreSQL (for stocks)

### Install Dependencies

```bash
# Install all workspace dependencies at once
npm install
```

### Development Commands

Run individual applications from the root:

```bash
# Website
npm run dev:website

# Projects app
npm run dev:projects

# Stocks frontend
npm run dev:stocks-frontend
```

Or navigate to each app directory and run locally:

```bash
cd apps/projects && npm run dev
cd apps/stocks/frontend && npm run dev
cd apps/website/frontend/app && npm run dev
```

### Build Commands

```bash
# Build all (coming soon)
npm run build:website
npm run build:projects
npm run build:stocks-frontend
```

## Architecture Decisions

- **npm workspaces** chosen over Turborepo/pnpm for simplicity and native npm support
- Each application remains independently runnable
- No shared code migration yet (future phase)
- Python backends managed separately from npm ecosystem
- Explicit workspace paths avoid build artifact detection issues

## Future Work

- [ ] Migrate shared UI components to `packages/ui`
- [ ] Create shared TypeScript types in `packages/types`
- [ ] Shared utilities in `packages/shared`
- [ ] Standardized ESLint/Prettier configs
- [ ] CI/CD pipeline configuration

## Author

just-anotherday
