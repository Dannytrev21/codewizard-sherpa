CREATE TABLE IF NOT EXISTS checkpoint_chain (
    sequence       INTEGER PRIMARY KEY AUTOINCREMENT,
    transition_id  TEXT    NOT NULL UNIQUE,
    prior_head     TEXT    NOT NULL,
    next_head      TEXT    NOT NULL,
    event_bytes    BLOB    NOT NULL,
    written_at     TEXT    NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS ix_chain_next_head ON checkpoint_chain(next_head);
