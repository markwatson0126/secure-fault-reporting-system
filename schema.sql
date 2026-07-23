CREATE TABLE IF NOT EXISTS buildings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL COLLATE NOCASE UNIQUE,
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1))
);

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT NOT NULL COLLATE NOCASE UNIQUE,
    password_hash TEXT NOT NULL,
    first_name TEXT NOT NULL,
    last_name TEXT NOT NULL,
    building_id INTEGER NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('user', 'admin')),
    FOREIGN KEY (building_id) REFERENCES buildings(id)
);

CREATE TABLE IF NOT EXISTS allowed_email_domains (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    building_id INTEGER NOT NULL,
    domain TEXT NOT NULL COLLATE NOCASE,
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    created_by_user_id INTEGER,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deactivated_by_user_id INTEGER,
    deactivated_at TEXT,
    FOREIGN KEY (building_id) REFERENCES buildings(id),
    FOREIGN KEY (created_by_user_id) REFERENCES users(id),
    FOREIGN KEY (deactivated_by_user_id) REFERENCES users(id),
    UNIQUE (building_id, domain)
);

CREATE TABLE IF NOT EXISTS faults (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    building_id INTEGER NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('Open', 'Closed')),
    submitted_by INTEGER NOT NULL,
    closed_by INTEGER,
    date_created TEXT DEFAULT CURRENT_TIMESTAMP,
    date_closed TEXT,
    FOREIGN KEY (building_id) REFERENCES buildings(id),
    FOREIGN KEY (submitted_by) REFERENCES users(id),
    FOREIGN KEY (closed_by) REFERENCES users(id)
);
