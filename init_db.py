"""Seed prices.db with a small set of destination cities and ticket prices."""

import sqlite3

DB_PATH = "prices.db"

PRICES = [
    ("london", 799),
    ("paris", 899),
    ("tokyo", 1400),
    ("berlin", 499),
    ("new york", 599),
    ("sydney", 1800),
    ("dubai", 1200),
    ("rome", 949),
    ("barcelona", 879),
    ("singapore", 1550),
]


def main():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS prices (
                city  TEXT PRIMARY KEY,
                price INTEGER NOT NULL
            )
            """
        )
        conn.executemany(
            "INSERT OR REPLACE INTO prices (city, price) VALUES (?, ?)",
            PRICES,
        )
    print(f"Seeded {len(PRICES)} cities into {DB_PATH}")


if __name__ == "__main__":
    main()
