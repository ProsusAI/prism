SCHEMA_SQL = """
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;
PRAGMA synchronous = NORMAL;

CREATE TABLE IF NOT EXISTS schema_version (version INTEGER PRIMARY KEY);

CREATE TABLE IF NOT EXISTS sessions (
  id TEXT PRIMARY KEY,
  ide TEXT NOT NULL DEFAULT '',
  cwd TEXT,
  started_at INTEGER NOT NULL,
  ended_at INTEGER
);

CREATE TABLE IF NOT EXISTS observations (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
  project_id TEXT NOT NULL,
  event TEXT NOT NULL,
  tool TEXT NOT NULL DEFAULT '',
  source TEXT NOT NULL DEFAULT 'claude_code',
  input_summary TEXT NOT NULL,
  compressed INTEGER NOT NULL DEFAULT 1,
  intensity TEXT DEFAULT 'lite',
  extracted_at INTEGER,
  insight_type TEXT,
  evidence TEXT,
  ts INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_observations_session ON observations(session_id, ts);
CREATE INDEX IF NOT EXISTS idx_observations_project ON observations(project_id, extracted_at, ts);
CREATE INDEX IF NOT EXISTS idx_observations_ts ON observations(ts);

CREATE VIRTUAL TABLE IF NOT EXISTS observations_fts USING fts5(
  input_summary,
  content='observations',
  content_rowid='id',
  tokenize='porter unicode61'
);

CREATE TRIGGER IF NOT EXISTS obs_ai AFTER INSERT ON observations BEGIN
  INSERT INTO observations_fts(rowid, input_summary) VALUES (new.id, new.input_summary);
END;
CREATE TRIGGER IF NOT EXISTS obs_ad AFTER DELETE ON observations BEGIN
  INSERT INTO observations_fts(observations_fts, rowid, input_summary) VALUES('delete', old.id, old.input_summary);
END;
CREATE TRIGGER IF NOT EXISTS obs_au AFTER UPDATE ON observations BEGIN
  INSERT INTO observations_fts(observations_fts, rowid, input_summary) VALUES('delete', old.id, old.input_summary);
  INSERT INTO observations_fts(rowid, input_summary) VALUES (new.id, new.input_summary);
END;

INSERT OR IGNORE INTO schema_version(version) VALUES (1);
"""
