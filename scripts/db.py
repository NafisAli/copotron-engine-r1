import sqlite3
from pathlib import Path

INDEX_SCHEMA_VERSION = 1
DB_FILENAME = ".index.sqlite3"

def get_db_path(vault_dir: Path) -> Path:
    """Return the absolute path to the SQLite index file inside vault_dir."""
    return Path(vault_dir) / DB_FILENAME

def create_tables(conn: sqlite3.Connection):
    """Create relational schema and FTS5 virtual table if they do not already exist."""
    conn.execute("""
    CREATE TABLE IF NOT EXISTS memories (
        id TEXT PRIMARY KEY,
        file_path TEXT NOT NULL,
        title TEXT NOT NULL,
        date TEXT NOT NULL,
        summary TEXT NOT NULL,
        type TEXT NOT NULL,
        status TEXT NOT NULL,
        persona TEXT,
        inherited_persona TEXT,
        tags_json TEXT NOT NULL,
        open_tail_json TEXT NOT NULL,
        parents_json TEXT NOT NULL DEFAULT '[]',
        mtime REAL NOT NULL,
        hash TEXT NOT NULL
    );
    """)

    conn.execute("""
    CREATE TABLE IF NOT EXISTS memory_edges (
        parent_id TEXT NOT NULL,
        child_id TEXT NOT NULL,
        PRIMARY KEY (parent_id, child_id)
    );
    """)

    conn.execute("CREATE INDEX IF NOT EXISTS idx_edges_parent ON memory_edges(parent_id);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_edges_child ON memory_edges(child_id);")

    conn.execute("""
    CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(
        id UNINDEXED,
        title,
        summary,
        tags,
        body,
        tokenize = 'porter unicode61'
    );
    """)

def drop_all_tables(conn: sqlite3.Connection):
    """Drop all tables and FTS virtual tables to wipe the local cache."""
    conn.execute("DROP TABLE IF EXISTS memories_fts;")
    conn.execute("DROP TABLE IF EXISTS memory_edges;")
    conn.execute("DROP TABLE IF EXISTS memories;")

def init_db(db_path: Path) -> sqlite3.Connection:
    """
    Initialize SQLite connection with WAL mode and schema version lifecycle.
    If user_version does not match INDEX_SCHEMA_VERSION, all tables are dropped
    and rebuilt cleanly without manual migration files.
    """
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    conn.execute("PRAGMA foreign_keys = ON;")

    current_version = conn.execute("PRAGMA user_version;").fetchone()[0]
    if current_version != INDEX_SCHEMA_VERSION:
        drop_all_tables(conn)
        create_tables(conn)
        conn.execute(f"PRAGMA user_version = {INDEX_SCHEMA_VERSION};")
        conn.commit()
    else:
        create_tables(conn)

    return conn

def get_readonly_db(db_path: Path) -> sqlite3.Connection:
    """
    Open a read connection to the existing database in WAL mode.
    Raises FileNotFoundError if the database file does not exist.
    """
    db_path = Path(db_path)
    if not db_path.is_file():
        raise FileNotFoundError(f"Database not found at {db_path}. Run indexer.py first.")

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL;")
    return conn
