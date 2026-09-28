"""Create missing database objects without deleting existing local data."""

import sqlite3

from common import DB_PATH, SCHEMA_PATH


def initialize_database(db_path=DB_PATH):
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))


if __name__ == "__main__":
    initialize_database()
    print(f"Banco pronto (dados existentes preservados): {DB_PATH}")
