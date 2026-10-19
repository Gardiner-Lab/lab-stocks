"""
Lab Stocks' database: glycerol stocks, primers, chemicals and antibodies, each lab's own.

    glycerol   a frozen culture holding a plasmid: which plasmid (from the Plasmid
               Editor), which clone, in which strain, where it is kept
    primers    an oligonucleotide: its sequence, what it is for, where the tube is
    chemicals  a chemical the lab keeps: its name, CAS number, room and size;
               its safety data sheet is a file on it captioned SDS
    antibodies an antibody: the lab's short code for it, what it is, primary or
               secondary, who makes it, the animal it is raised in, its product
               number, and notes about using it
    attachments, changes, counters, lab_codes   as in the Seed Bank

Codes start with the lab's code: GL-G-0042 a glycerol stock, GL-O-0007 a primer,
GL-C-0003 a chemical, GL-A-0005 an antibody.
"""

import os
import sqlite3
from typing import Optional

_path: Optional[str] = None

SCHEMA = """
CREATE TABLE IF NOT EXISTS glycerol (
    id TEXT PRIMARY KEY,
    code TEXT UNIQUE NOT NULL,
    lab TEXT NOT NULL,
    plasmid_id TEXT,
    plasmid_name TEXT NOT NULL DEFAULT '',
    clone TEXT NOT NULL DEFAULT '',
    host TEXT NOT NULL DEFAULT '',
    selection TEXT NOT NULL DEFAULT '',
    location TEXT NOT NULL DEFAULT '',
    made_on TEXT,
    source TEXT NOT NULL DEFAULT 'manual',
    status TEXT NOT NULL DEFAULT 'in stock',
    notes TEXT NOT NULL DEFAULT '',
    created_by TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    deleted_at TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_glycerol_plasmid ON glycerol(plasmid_id);

CREATE TABLE IF NOT EXISTS primers (
    id TEXT PRIMARY KEY,
    code TEXT UNIQUE NOT NULL,
    lab TEXT NOT NULL,
    name TEXT NOT NULL,
    sequence TEXT NOT NULL,
    direction TEXT NOT NULL DEFAULT '',
    target TEXT NOT NULL DEFAULT '',
    purpose TEXT NOT NULL DEFAULT '',
    modifications TEXT NOT NULL DEFAULT '',
    supplier TEXT NOT NULL DEFAULT '',
    ordered_on TEXT,
    concentration TEXT NOT NULL DEFAULT '',
    location TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'in stock',
    notes TEXT NOT NULL DEFAULT '',
    created_by TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    deleted_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS chemicals (
    id TEXT PRIMARY KEY,
    code TEXT UNIQUE NOT NULL,
    lab TEXT NOT NULL,
    name TEXT NOT NULL,
    cas TEXT NOT NULL DEFAULT '',
    room TEXT NOT NULL DEFAULT '',
    size TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'in stock',
    notes TEXT NOT NULL DEFAULT '',
    created_by TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    deleted_at TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_chemicals_cas ON chemicals(cas);

CREATE TABLE IF NOT EXISTS antibodies (
    id TEXT PRIMARY KEY,
    code TEXT UNIQUE NOT NULL,
    lab TEXT NOT NULL,
    short_code TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    type TEXT NOT NULL DEFAULT 'primary',
    producer TEXT NOT NULL DEFAULT '',
    host TEXT NOT NULL DEFAULT '',
    product_number TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'in stock',
    notes TEXT NOT NULL DEFAULT '',
    created_by TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    deleted_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS attachments (
    id TEXT PRIMARY KEY,
    record_kind TEXT NOT NULL,
    record_id TEXT NOT NULL,
    filename TEXT NOT NULL,
    mime TEXT NOT NULL,
    size INTEGER NOT NULL,
    sha256 TEXT NOT NULL,
    data BLOB NOT NULL,
    caption TEXT NOT NULL DEFAULT '',
    created_by TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    deleted_at TIMESTAMP,
    deleted_by TEXT
);
CREATE INDEX IF NOT EXISTS idx_attachments_record ON attachments(record_kind, record_id);

CREATE TABLE IF NOT EXISTS changes (
    record_kind TEXT NOT NULL,
    record_id TEXT NOT NULL,
    changed_by TEXT,
    changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    what TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_changes_record ON changes(record_kind, record_id);

CREATE TABLE IF NOT EXISTS counters (
    prefix TEXT PRIMARY KEY,
    value INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS lab_codes (
    lab TEXT PRIMARY KEY,
    code TEXT UNIQUE NOT NULL,
    set_by TEXT,
    set_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""


def set_path(path: str) -> None:
    global _path
    _path = path


def path() -> str:
    return _path or os.environ.get('STOCKS_DATABASE_PATH', '/stocks/stocks.db')


class _Connection:
    def __enter__(self) -> sqlite3.Connection:
        conn = sqlite3.connect(path(), timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA busy_timeout = 10000')
        self.conn = conn
        return conn

    def __exit__(self, exc_type, exc, tb):
        try:
            if exc_type is None:
                self.conn.commit()
            else:
                self.conn.rollback()
        finally:
            self.conn.close()
        return False


def connect() -> _Connection:
    return _Connection()


def initialize(db_path: Optional[str] = None) -> None:
    if db_path:
        set_path(db_path)
    directory = os.path.dirname(path())
    if directory:
        os.makedirs(directory, exist_ok=True)
    with connect() as conn:
        # The ordinary rollback journal, not WAL: the suite's backup reads the
        # database from a read-only mount, where SQLite cannot open WAL.
        conn.execute('PRAGMA journal_mode = DELETE')
        conn.executescript(SCHEMA)
