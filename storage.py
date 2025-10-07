import csv
import os
import secrets
from datetime import datetime, timedelta
from typing import List, Optional
from sqlalchemy import create_engine, text, event
from sqlalchemy.engine import Engine
from models import Track

class StorageRepository:
    def __init__(self, db_url: str = "sqlite:///music.db"):
        self.engine: Engine = create_engine(db_url, future=True)

        if self.engine.url.get_backend_name() == "sqlite":
            @event.listens_for(self.engine, "connect")
            def set_sqlite_pragma(dbapi_connection, connection_record):
                cursor = dbapi_connection.cursor()
                cursor.execute("PRAGMA foreign_keys = ON")
                cursor.close()

        self._init_db()

    # -------- helpers --------
    def _table_exists(self, conn, table: str) -> bool:
        row = conn.exec_driver_sql(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=:t",
            {"t": table},
        ).fetchone()
        return bool(row)

    def _table_has_column(self, conn, table: str, col: str) -> bool:
        if not self._table_exists(conn, table):
            return False
        cols = conn.exec_driver_sql(f"PRAGMA table_info({table})").fetchall()
        names = [c[1] for c in cols]
        return col in names

    # -------- schema init + migrations --------
    def _init_db(self):
        with self.engine.begin() as conn:
            conn.exec_driver_sql("PRAGMA foreign_keys = ON")

            # users
            conn.exec_driver_sql("""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
            """)

            # legacy single-list table (will migrate)
            conn.exec_driver_sql("""
                CREATE TABLE IF NOT EXISTS playlist (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    title TEXT NOT NULL,
                    artist TEXT NOT NULL,
                    url TEXT,
                    mbid TEXT,
                    added_at TEXT NOT NULL,
                    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
                );
            """)

            # user_pref
            conn.exec_driver_sql("""
                CREATE TABLE IF NOT EXISTS user_pref (
                    user_id INTEGER PRIMARY KEY,
                    default_genre TEXT,
                    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
                );
            """)

            # --- NEW: playlists (meta) ---
            conn.exec_driver_sql("""
                CREATE TABLE IF NOT EXISTS playlists (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    description TEXT DEFAULT '',
                    is_public INTEGER NOT NULL DEFAULT 0,
                    share_token TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(share_token),
                    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
                );
            """)

            # --- NEW: playlist_tracks (ordered) ---
            conn.exec_driver_sql("""
                CREATE TABLE IF NOT EXISTS playlist_tracks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    playlist_id INTEGER NOT NULL,
                    title TEXT NOT NULL,
                    artist TEXT NOT NULL,
                    url TEXT,
                    mbid TEXT,
                    position INTEGER NOT NULL,
                    added_at TEXT NOT NULL,
                    FOREIGN KEY(playlist_id) REFERENCES playlists(id) ON DELETE CASCADE
                );
            """)

            # --- NEW: user_tokens (for Spotify OAuth) ---
            conn.exec_driver_sql("""
                CREATE TABLE IF NOT EXISTS user_tokens (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    provider TEXT NOT NULL, -- 'spotify'
                    access_token TEXT NOT NULL,
                    refresh_token TEXT,
                    expires_at TEXT,
                    UNIQUE(user_id, provider),
                    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
                );
            """)

            # --- MIGRATION: move legacy "playlist" rows into new playlists/playlist_tracks ---
            # If user has tracks in old "playlist" but has no playlists yet, create default one.
            has_any_new = conn.exec_driver_sql("SELECT COUNT(1) FROM playlists").fetchone()[0] > 0
            legacy_rows = conn.exec_driver_sql("SELECT id, user_id, title, artist, url, mbid, added_at FROM playlist").fetchall()
            if legacy_rows and not has_any_new:
                # create one default playlist per user who has legacy rows
                users_with_legacy = [r[1] for r in legacy_rows]
                unique_users = sorted(set(users_with_legacy))
                for uid in unique_users:
                    now = datetime.utcnow().isoformat()
                    cur = conn.execute(
                        text("""
                            INSERT INTO playlists (user_id, name, description, is_public, created_at, updated_at)
                            VALUES (:uid, :name, :desc, :pub, :c, :u)
                        """),
                        {"uid": uid, "name": "My Playlist", "desc": "", "pub": 0, "c": now, "u": now},
                    )
                    new_pid = cur.lastrowid
                    # pull legacy items for this user and insert with ordering
                    items = [r for r in legacy_rows if r[1] == uid]
                    pos = 0
                    for _, _, title, artist, url_, mbid, added_at in items:
                        conn.execute(
                            text("""
                                INSERT INTO playlist_tracks (playlist_id, title, artist, url, mbid, position, added_at)
                                VALUES (:pid, :title, :artist, :url, :mbid, :pos, :added)
                            """),
                            {"pid": new_pid, "title": title, "artist": artist, "url": url_, "mbid": mbid,
                             "pos": pos, "added": added_at or now}
                        )
                        pos += 1

            # leave the old 'playlist' table as is for backward compatibility; new code uses playlists/playlist_tracks

    # ---------- Users ----------
    def create_user(self, username: str, password_hash: str) -> int:
        with self.engine.begin() as conn:
            cur = conn.execute(
                text("INSERT INTO users (username, password_hash, created_at) VALUES (:u, :p, :ts)"),
                {"u": username, "p": password_hash, "ts": datetime.utcnow().isoformat()},
            )
            user_id = cur.lastrowid
            conn.execute(
                text("INSERT INTO user_pref (user_id, default_genre) VALUES (:id, :g)"),
                {"id": user_id, "g": os.getenv("DEFAULT_GENRE", "pop")},
            )
            return user_id

    def get_user_by_username(self, username: str) -> Optional[dict]:
        with self.engine.begin() as conn:
            row = conn.execute(
                text("SELECT id, username, password_hash FROM users WHERE username=:u"),
                {"u": username},
            ).fetchone()
            return dict(row._mapping) if row else None

    def get_user_by_id(self, user_id: int) -> Optional[dict]:
        with self.engine.begin() as conn:
            row = conn.execute(
                text("SELECT id, username, password_hash FROM users WHERE id=:i"),
                {"i": user_id},
            ).fetchone()
            return dict(row._mapping) if row else None

    # ---------- Playlists ----------
    def create_playlist(self, user_id: int, name: str, description: str, is_public: bool) -> int:
        now = datetime.utcnow().isoformat()
        with self.engine.begin() as conn:
            cur = conn.execute(
                text("""
                    INSERT INTO playlists (user_id, name, description, is_public, created_at, updated_at)
                    VALUES (:uid, :name, :desc, :pub, :c, :u)
                """),
                {"uid": user_id, "name": name, "desc": description, "pub": 1 if is_public else 0, "c": now, "u": now},
            )
            return cur.lastrowid
        
    def delete_playlist(self, playlist_id: int, user_id: int) -> bool:
        with self.engine.begin() as conn:
            # ยืนยันความเป็นเจ้าของ
            row = conn.execute(
                text("SELECT 1 FROM playlists WHERE id=:pid AND user_id=:uid"),
                {"pid": playlist_id, "uid": user_id}
            ).fetchone()
            if not row:
                raise PermissionError("Permission denied for this playlist")
    
            # ลบตัวเพลย์ลิสต์ (playlist_tracks จะโดนลบอัตโนมัติด้วย ON DELETE CASCADE)
            res = conn.execute(
                text("DELETE FROM playlists WHERE id=:pid AND user_id=:uid"),
                {"pid": playlist_id, "uid": user_id}
            )
            return res.rowcount > 0

    def list_playlists(self, user_id: int) -> List[dict]:
        with self.engine.begin() as conn:
            rows = conn.execute(
                text("SELECT id, user_id, name, description, is_public, share_token, created_at, updated_at FROM playlists WHERE user_id=:uid ORDER BY updated_at DESC"),
                {"uid": user_id},
            ).fetchall()
            return [dict(r._mapping) for r in rows]

    def get_playlist(self, playlist_id: int, user_id: int) -> Optional[dict]:
        with self.engine.begin() as conn:
            row = conn.execute(
                text("SELECT id, user_id, name, description, is_public, share_token FROM playlists WHERE id=:pid AND user_id=:uid"),
                {"pid": playlist_id, "uid": user_id},
            ).fetchone()
            return dict(row._mapping) if row else None

    def update_playlist_meta(self, playlist_id: int, user_id: int, name: str, description: str, is_public: bool):
        with self.engine.begin() as conn:
            conn.execute(
                text("""
                    UPDATE playlists SET name=:n, description=:d, is_public=:p, updated_at=:u
                    WHERE id=:pid AND user_id=:uid
                """),
                {"n": name, "d": description, "p": 1 if is_public else 0, "u": datetime.utcnow().isoformat(),
                 "pid": playlist_id, "uid": user_id},
            )

    def ensure_share_token(self, playlist_id: int, user_id: int) -> str:
        with self.engine.begin() as conn:
            row = conn.execute(
                text("SELECT share_token FROM playlists WHERE id=:pid AND user_id=:uid"),
                {"pid": playlist_id, "uid": user_id},
            ).fetchone()
            token = row[0] if row and row[0] else secrets.token_urlsafe(10)
            conn.execute(
                text("UPDATE playlists SET share_token=:t, is_public=1, updated_at=:u WHERE id=:pid AND user_id=:uid"),
                {"t": token, "u": datetime.utcnow().isoformat(), "pid": playlist_id, "uid": user_id},
            )
            return token

    def get_public_playlist_by_token(self, token: str) -> Optional[dict]:
        with self.engine.begin() as conn:
            row = conn.execute(
                text("SELECT id, user_id, name, description, is_public, share_token FROM playlists WHERE share_token=:t AND is_public=1"),
                {"t": token},
            ).fetchone()
            return dict(row._mapping) if row else None

    # ---------- Playlist Tracks ----------
    def insert_playlist_track(self, playlist_id: int, track: Track):
        with self.engine.begin() as conn:
            # find current max position
            pos_row = conn.execute(
                text("SELECT COALESCE(MAX(position), -1) FROM playlist_tracks WHERE playlist_id=:pid"),
                {"pid": playlist_id},
            ).fetchone()
            next_pos = (pos_row[0] if pos_row[0] is not None else 0) + 1
            conn.execute(
                text("""
                    INSERT INTO playlist_tracks (playlist_id, title, artist, url, mbid, position, added_at)
                    VALUES (:pid, :title, :artist, :url, :mbid, :pos, :added)
                """),
                {"pid": playlist_id, "title": track.title, "artist": track.artist, "url": track.url,
                 "mbid": track.mbid, "pos": next_pos, "added": datetime.utcnow().isoformat()}
            )
            conn.execute(text("UPDATE playlists SET updated_at=:u WHERE id=:pid"), {"u": datetime.utcnow().isoformat(), "pid": playlist_id})

    def _assert_owner(self, conn, playlist_id: int, user_id: int):
        row = conn.execute(text("SELECT 1 FROM playlists WHERE id=:pid AND user_id=:uid"), {"pid": playlist_id, "uid": user_id}).fetchone()
        if not row:
            raise PermissionError("Permission denied for this playlist")

    def delete_playlist_track(self, playlist_id: int, track_id: int, user_id: int):
        with self.engine.begin() as conn:
            self._assert_owner(conn, playlist_id, user_id)
            conn.execute(text("DELETE FROM playlist_tracks WHERE id=:tid AND playlist_id=:pid"),
                         {"tid": track_id, "pid": playlist_id})

    def fetch_playlist_tracks(self, playlist_id: int, user_id: Optional[int] = None, limit: Optional[int] = None) -> List[dict]:
        with self.engine.begin() as conn:
            if user_id is not None:
                self._assert_owner(conn, playlist_id, user_id)
            q = "SELECT id, title, artist, url, mbid, position, added_at FROM playlist_tracks WHERE playlist_id=:pid ORDER BY position ASC"
            if limit:
                q += " LIMIT :limit"
            rows = conn.execute(text(q), {"pid": playlist_id, "limit": limit} if limit else {"pid": playlist_id}).fetchall()
            return [dict(r._mapping) for r in rows]

    def reorder_track(self, playlist_id: int, track_id: int, direction: str, user_id: int):
        with self.engine.begin() as conn:
            self._assert_owner(conn, playlist_id, user_id)
            row = conn.execute(
                text("SELECT id, position FROM playlist_tracks WHERE id=:tid AND playlist_id=:pid"),
                {"tid": track_id, "pid": playlist_id},
            ).fetchone()
            if not row:
                return
            current_pos = row[1]
            if direction == "up":
                neighbor = conn.execute(
                    text("SELECT id, position FROM playlist_tracks WHERE playlist_id=:pid AND position<:p ORDER BY position DESC LIMIT 1"),
                    {"pid": playlist_id, "p": current_pos},
                ).fetchone()
            else:
                neighbor = conn.execute(
                    text("SELECT id, position FROM playlist_tracks WHERE playlist_id=:pid AND position>:p ORDER BY position ASC LIMIT 1"),
                    {"pid": playlist_id, "p": current_pos},
                ).fetchone()
            if not neighbor:
                return
            nid, npos = neighbor
            # swap positions
            conn.execute(text("UPDATE playlist_tracks SET position=:np WHERE id=:tid"), {"np": npos, "tid": row[0]})
            conn.execute(text("UPDATE playlist_tracks SET position=:cp WHERE id=:nid"), {"cp": current_pos, "nid": nid})

    def clear_playlist_tracks(self, playlist_id: int, user_id: int):
        with self.engine.begin() as conn:
            self._assert_owner(conn, playlist_id, user_id)
            conn.execute(text("DELETE FROM playlist_tracks WHERE playlist_id=:pid"), {"pid": playlist_id})

    # ---------- Preferences ----------
    def get_default_genre(self, user_id: int) -> str:
        with self.engine.begin() as conn:
            row = conn.execute(text("SELECT default_genre FROM user_pref WHERE user_id=:uid"), {"uid": user_id}).fetchone()
            if row and row[0]:
                return row[0]
            default_g = os.getenv("DEFAULT_GENRE", "pop")
            conn.execute(text("INSERT OR IGNORE INTO user_pref (user_id, default_genre) VALUES (:uid, :g)"),
                         {"uid": user_id, "g": default_g})
            return default_g

    def set_default_genre(self, user_id: int, genre: str):
        with self.engine.begin() as conn:
            conn.execute(text("UPDATE user_pref SET default_genre=:g WHERE user_id=:uid"),
                         {"g": genre, "uid": user_id})

    # ---------- CSV export (top10 of specific playlist) ----------
    def export_playlist_csv(self, playlist_id: int, user_id: int, path: str = "playlist_top10.csv") -> str:
        rows = self.fetch_playlist_tracks(playlist_id, user_id, limit=10)
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["id", "title", "artist", "url", "mbid", "position", "added_at"])
            writer.writeheader()
            for r in rows:
                writer.writerow(r)
        return path

    # ---------- OAuth token storage ----------
    def upsert_user_token(self, user_id: int, provider: str, access_token: str, refresh_token: Optional[str], expires_at: Optional[str]):
        with self.engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO user_tokens (user_id, provider, access_token, refresh_token, expires_at)
                VALUES (:uid, :p, :at, :rt, :ea)
                ON CONFLICT(user_id, provider) DO UPDATE SET
                    access_token=excluded.access_token,
                    refresh_token=excluded.refresh_token,
                    expires_at=excluded.expires_at
            """), {"uid": user_id, "p": provider, "at": access_token, "rt": refresh_token, "ea": expires_at})

    def get_user_token(self, user_id: int, provider: str) -> Optional[dict]:
        with self.engine.begin() as conn:
            row = conn.execute(text("SELECT access_token, refresh_token, expires_at FROM user_tokens WHERE user_id=:uid AND provider=:p"),
                               {"uid": user_id, "p": provider}).fetchone()
            return dict(row._mapping) if row else None

    # ---- NEW: รวมเพลย์ลิสต์พร้อมจำนวนเพลง (ลด N+1) ----
    def list_playlists_with_counts(self, user_id: int) -> List[dict]:
        with self.engine.begin() as conn:
            rows = conn.execute(text("""
                SELECT p.id, p.user_id, p.name, p.description, p.is_public, p.share_token,
                    p.created_at, p.updated_at,
                    COUNT(t.id) AS track_count
                FROM playlists p
                LEFT JOIN playlist_tracks t ON t.playlist_id = p.id
                WHERE p.user_id = :uid
                GROUP BY p.id
                ORDER BY p.updated_at DESC
            """), {"uid": user_id}).fetchall()
            return [dict(r._mapping) for r in rows]

    # ---- NEW: สถิติโดยรวมของผู้ใช้ ----
    def get_user_music_stats(self, user_id: int) -> dict:
        with self.engine.begin() as conn:
            totals = conn.execute(text("""
                SELECT COUNT(t.id) AS total_tracks,
                    COUNT(DISTINCT t.artist) AS unique_artists
                FROM playlists p
                LEFT JOIN playlist_tracks t ON t.playlist_id = p.id
                WHERE p.user_id = :uid
            """), {"uid": user_id}).fetchone()
            vis = conn.execute(text("""
                SELECT
                SUM(CASE WHEN is_public = 1 THEN 1 ELSE 0 END) AS public_pl,
                SUM(CASE WHEN is_public = 0 THEN 1 ELSE 0 END) AS private_pl
                FROM playlists WHERE user_id = :uid
            """), {"uid": user_id}).fetchone()

            return {
                "total_tracks": (totals[0] or 0) if totals else 0,
                "unique_artists": (totals[1] or 0) if totals else 0,
                "public_playlists": (vis[0] or 0) if vis else 0,
                "private_playlists": (vis[1] or 0) if vis else 0,
            }