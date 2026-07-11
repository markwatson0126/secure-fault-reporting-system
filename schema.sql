-- Drop tables if they exist (for reinitialisation)
DROP TABLE IF EXISTS faults;
DROP TABLE IF EXISTS users;

-- Users table
CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    first_name TEXT NOT NULL,
    last_name TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('user', 'admin'))
);

-- Faults table
CREATE TABLE faults (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    location TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('Open', 'Closed')),
    submitted_by INTEGER NOT NULL,
    closed_by INTEGER,
    date_created TEXT DEFAULT CURRENT_TIMESTAMP,
    date_closed TEXT,
    FOREIGN KEY (submitted_by) REFERENCES users(id),
    FOREIGN KEY (closed_by) REFERENCES users(id)
);
