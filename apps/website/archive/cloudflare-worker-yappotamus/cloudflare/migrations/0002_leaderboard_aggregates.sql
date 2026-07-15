ALTER TABLE leaderboard ADD COLUMN rounds INTEGER NOT NULL DEFAULT 1;
ALTER TABLE leaderboard ADD COLUMN total_wpm REAL NOT NULL DEFAULT 0;
ALTER TABLE leaderboard ADD COLUMN total_accuracy REAL NOT NULL DEFAULT 0;

UPDATE leaderboard
SET
  rounds = CASE WHEN rounds IS NULL OR rounds < 1 THEN 1 ELSE rounds END,
  total_wpm = CASE WHEN total_wpm IS NULL OR total_wpm <= 0 THEN score / 100 ELSE total_wpm END,
  total_accuracy = CASE WHEN total_accuracy IS NULL OR total_accuracy <= 0 THEN 100 ELSE total_accuracy END;