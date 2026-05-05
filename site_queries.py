# site_queries.py
import sqlite3


def get_connection(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def section1(conn: sqlite3.Connection) -> dict:
    row = conn.execute(
        "SELECT COUNT(*) AS n FROM streets_dedup"
    ).fetchone()
    return {"total_streets": row["n"]}


def section2(conn):
    return {}


def section3(conn):
    return {}


def section4(conn):
    return {}


def section5(conn):
    return {}


def section6(conn):
    return {}


def section8(conn):
    return {}
