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
DROP TRIGGER IF EXISTS obs_au;
CREATE TRIGGER obs_au AFTER UPDATE ON observations
WHEN old.input_summary != new.input_summary BEGIN
  INSERT INTO observations_fts(observations_fts, rowid, input_summary) VALUES('delete', old.id, old.input_summary);
  INSERT INTO observations_fts(rowid, input_summary) VALUES (new.id, new.input_summary);
END;

-- Retrieval analytics (v3). Event log of engrams returned to Claude/Cursor via
-- MCP, plus engrams surfaced into prism.md by sync. Decoupled from the engram
-- index/frontmatter: counts are DERIVED from these events, never stored on engrams.
CREATE TABLE IF NOT EXISTS retrievals (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id   TEXT NOT NULL,
  source       TEXT NOT NULL DEFAULT 'claude_code',  -- claude_code | cursor | sync
  tool         TEXT NOT NULL,                         -- prism_search|prism_get|prism_relevant|sync_push
  query        TEXT NOT NULL DEFAULT '',              -- scrubbed query / file_path / domain / id
  result_count INTEGER NOT NULL DEFAULT 0,
  ts           INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_retrievals_project ON retrievals(project_id, ts);
CREATE INDEX IF NOT EXISTS idx_retrievals_tool ON retrievals(tool, ts);

CREATE TABLE IF NOT EXISTS retrieval_engrams (
  retrieval_id INTEGER NOT NULL REFERENCES retrievals(id) ON DELETE CASCADE,
  engram_id    TEXT NOT NULL,
  ts           INTEGER NOT NULL   -- denormalized from parent for index-only window queries
);
CREATE INDEX IF NOT EXISTS idx_retrieval_engrams_engram ON retrieval_engrams(engram_id, ts);
CREATE INDEX IF NOT EXISTS idx_retrieval_engrams_rid ON retrieval_engrams(retrieval_id);

INSERT OR IGNORE INTO schema_version(version) VALUES (1);
INSERT OR IGNORE INTO schema_version(version) VALUES (2);
INSERT OR IGNORE INTO schema_version(version) VALUES (3);
"""

# Migration SQL applied to existing databases by _migrate_db() in storage.py.
MIGRATION_V2 = """
DROP TRIGGER IF EXISTS obs_au;
CREATE TRIGGER obs_au AFTER UPDATE ON observations
WHEN old.input_summary != new.input_summary BEGIN
  INSERT INTO observations_fts(observations_fts, rowid, input_summary) VALUES('delete', old.id, old.input_summary);
  INSERT INTO observations_fts(rowid, input_summary) VALUES (new.id, new.input_summary);
END;
"""

# v3: retrieval analytics tables (idempotent; mirrors the CREATE block in SCHEMA_SQL).
MIGRATION_V3 = """
CREATE TABLE IF NOT EXISTS retrievals (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id   TEXT NOT NULL,
  source       TEXT NOT NULL DEFAULT 'claude_code',
  tool         TEXT NOT NULL,
  query        TEXT NOT NULL DEFAULT '',
  result_count INTEGER NOT NULL DEFAULT 0,
  ts           INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_retrievals_project ON retrievals(project_id, ts);
CREATE INDEX IF NOT EXISTS idx_retrievals_tool ON retrievals(tool, ts);

CREATE TABLE IF NOT EXISTS retrieval_engrams (
  retrieval_id INTEGER NOT NULL REFERENCES retrievals(id) ON DELETE CASCADE,
  engram_id    TEXT NOT NULL,
  ts           INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_retrieval_engrams_engram ON retrieval_engrams(engram_id, ts);
CREATE INDEX IF NOT EXISTS idx_retrieval_engrams_rid ON retrieval_engrams(retrieval_id);
"""
