-- Expected leaderboard schema after all migrations are applied

CREATE TABLE IF NOT EXISTS leaderboard (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  score REAL NOT NULL,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  rounds INTEGER NOT NULL DEFAULT 1,
  total_wpm REAL NOT NULL DEFAULT 0,
  total_accuracy REAL NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_leaderboard_score
ON leaderboard(score DESC);
