"""Fixture: SQL injection (seeded) + a clean parameterized query (control)."""
import sqlite3


def get_user(conn, username):
    # SEEDED BUG [SQLI-1]: username interpolated directly into SQL.
    cur = conn.cursor()
    cur.execute(f"SELECT * FROM users WHERE name = '{username}'")
    return cur.fetchone()


def get_user_safe(conn, username):
    # CLEAN CONTROL: parameterized — must NOT be flagged.
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE name = ?", (username,))
    return cur.fetchone()
