"""
Lab Stocks' database: glycerol stocks, primers, chemicals and antibodies, each lab's own.

    glycerol   a frozen culture holding a plasmid: which plasmid (from the Plasmid
               Editor), which clone, in which strain, where it is kept
    primers    an oligonucleotide: its sequence, what it is for, where the tube is
    chemicals  a chemical the lab keeps: its name, CAS number, room and size;
               its safety data sheet is a file on it captioned SDS
    material   plant material kept for later processing, a tube each (often a box of
               them): its name on the tube, the tissue, the plant it came from,
               when and by whom it was collected, the experiment, where it is
    antibodies an antibody: the lab's short code for it, what it is, primary or
               secondary, who makes it, the animal it is raised in, its product
               number, and notes about using it
    orders     what the lab needs ordered: asked for by anyone in the lab (or by
               marking a chemical out), ordered and received by its lab admin
    attachments, changes, counters, lab_codes   as in the Seed Bank
    elab_settings, elab_links   where a lab's stocks are copied in eLabJournal, and
               what each record last sent there

Codes start with the lab's code: GL-G-0042 a glycerol stock, GL-O-0007 a primer,
GL-C-0003 a chemical, GL-A-0005 an antibody, GL-M-0001 plant material.
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
    -- and GLYCEROL_ADDED, below
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

CREATE TABLE IF NOT EXISTS material (
    id TEXT PRIMARY KEY,
    code TEXT UNIQUE NOT NULL,
    lab TEXT NOT NULL,
    name TEXT NOT NULL,
    tissue TEXT NOT NULL DEFAULT '',
    species TEXT NOT NULL DEFAULT '',
    from_plant TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    collected_on TEXT,
    collected_by TEXT NOT NULL DEFAULT '',
    experiment TEXT NOT NULL DEFAULT '',
    location TEXT NOT NULL DEFAULT '',
    elab_layer_id TEXT NOT NULL DEFAULT '',
    elab_layer_path TEXT NOT NULL DEFAULT '',
    elab_position TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'in stock',
    notes TEXT NOT NULL DEFAULT '',
    created_by TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    deleted_at TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_material_name ON material(name);

CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lab TEXT NOT NULL,
    item TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT 'other',
    record_kind TEXT,
    record_code TEXT,
    quantity TEXT NOT NULL DEFAULT '',
    supplier TEXT NOT NULL DEFAULT '',
    product_number TEXT NOT NULL DEFAULT '',
    details TEXT NOT NULL DEFAULT '',
    link TEXT NOT NULL DEFAULT '',
    notes TEXT NOT NULL DEFAULT '',
    urgent INTEGER NOT NULL DEFAULT 0,
    auto INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'requested',
    requested_by TEXT,
    requested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    ordered_by TEXT,
    ordered_at TIMESTAMP,
    received_by TEXT,
    received_at TIMESTAMP,
    closed_by TEXT,
    closed_at TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_orders_lab ON orders(lab, status);
CREATE INDEX IF NOT EXISTS idx_orders_record ON orders(record_code);

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

-- Where a lab's glycerol stocks and seed lots are copied in eLabJournal
-- (app/elab.py), chosen by its lab admin: the eLab address, the API token made
-- there, what is copied to which sample type, and the lab's permit and
-- biosafety level for them.
CREATE TABLE IF NOT EXISTS elab_settings (
    lab TEXT PRIMARY KEY COLLATE NOCASE,
    url TEXT NOT NULL,
    token TEXT NOT NULL,
    kinds TEXT NOT NULL,
    sample_types TEXT NOT NULL DEFAULT '{}',
    defaults TEXT NOT NULL DEFAULT '{}',
    set_by TEXT,
    set_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- What each glycerol stock, plant material, or seed lot of the Seed Bank
-- (record_kind 'seed'), last sent to eLabJournal's inventory: which eLab, the
-- sample it is there, a fingerprint of what was sent, and for one brought over
-- from eLab, the name it keeps there.
CREATE TABLE IF NOT EXISTS elab_links (
    record_kind TEXT NOT NULL,
    record_id TEXT NOT NULL,
    elab_url TEXT,
    sample_id INTEGER,
    elab_name TEXT,
    archived INTEGER NOT NULL DEFAULT 0,
    sent TEXT,
    synced TEXT,
    error TEXT,
    tried TEXT,
    tried_at REAL,
    synced_at TEXT,
    PRIMARY KEY (record_kind, record_id)
);

CREATE TABLE IF NOT EXISTS lab_codes (
    lab TEXT PRIMARY KEY,
    code TEXT UNIQUE NOT NULL,
    set_by TEXT,
    set_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""


# Glycerol stocks' biosafety, insert and markers, as the GMO register (and eLab's
# Glycerol Stock type) asks: added to databases from before them.
GLYCEROL_ADDED = ['permit', 'biosafety', 'host_system', 'plant_markers', 'yeast_markers', 'inserts', 'gene_ids',
                  'donor', 'harmful', 'harmful_notes',
                  # where it is kept in eLab's storage: the compartment, its path then, and the place in a box
                  'elab_layer_id', 'elab_layer_path', 'elab_position']


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
        if 'elab_name' not in {r['name'] for r in conn.execute('PRAGMA table_info(elab_links)')}:
            conn.execute('ALTER TABLE elab_links ADD COLUMN elab_name TEXT')
        have = {r['name'] for r in conn.execute('PRAGMA table_info(glycerol)')}
        for column in GLYCEROL_ADDED:
            if column not in have:
                conn.execute(f"ALTER TABLE glycerol ADD COLUMN {column} TEXT NOT NULL DEFAULT ''")
