"""Regression tests for the per-connection `synchronous` pragma on the image
cache and the video library.

`synchronous` is a per-connection setting, unlike `journal_mode`. Setting it
once (the image cache did, in `_init_db`) only covers that one connection; every
other one commits at the default FULL, which is an fsync per commit. Measured on
a loaded array, same file, same moment: 152.7 ms per commit at FULL, 0.1 ms at
NORMAL. Same fix as the music database (test_music_db_synchronous_pragma.py).

NORMAL is only SQLite's documented-safe trade under WAL, so it must not be
applied to a connection that landed on a rollback journal.
"""

from __future__ import annotations

from pathlib import Path

from core.image_cache import ImageCache
from database.video_database import VideoDatabase

SYNCHRONOUS_NORMAL = 1
SYNCHRONOUS_FULL = 2


def _pragma(conn, name):
    return conn.execute(f"PRAGMA {name}").fetchone()[0]


def test_image_cache_connections_are_normal_under_wal(tmp_path: Path) -> None:
    cache = ImageCache(tmp_path / "cache")
    # not the connection _init_db used: a fresh one, as every request gets
    for _ in range(2):
        conn = cache._connect()
        try:
            assert str(_pragma(conn, "journal_mode")).lower() == "wal"
            assert _pragma(conn, "synchronous") == SYNCHRONOUS_NORMAL
        finally:
            conn.close()


def test_image_cache_stays_full_without_wal(tmp_path: Path) -> None:
    cache = ImageCache(tmp_path / "cache")
    conn = cache._connect()
    conn.execute("PRAGMA journal_mode = DELETE")
    conn.close()

    conn = cache._connect()
    try:
        assert str(_pragma(conn, "journal_mode")).lower() != "wal"
        assert _pragma(conn, "synchronous") == SYNCHRONOUS_FULL
    finally:
        conn.close()


def test_video_database_connections_are_normal_under_wal(tmp_path: Path) -> None:
    db = VideoDatabase(str(tmp_path / "video.db"))
    conn = db._get_connection()
    try:
        assert str(_pragma(conn, "journal_mode")).lower() == "wal"
        assert _pragma(conn, "synchronous") == SYNCHRONOUS_NORMAL
    finally:
        conn.close()
