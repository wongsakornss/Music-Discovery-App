from dataclasses import dataclass
from typing import Optional, List

@dataclass
class Track:
    title: str
    artist: str
    url: Optional[str] = None
    mbid: Optional[str] = None  # MusicBrainz ID

@dataclass
class Artist:
    name: str
    url: Optional[str] = None
    mbid: Optional[str] = None

@dataclass
class User:
    id: int
    username: str

@dataclass
class Playlist:
    id: int
    user_id: int
    name: str
    description: str = ""
    is_public: bool = False
    share_token: Optional[str] = None

@dataclass
class PlaylistTrack:
    id: int
    playlist_id: int
    title: str
    artist: str
    url: Optional[str] = None
    mbid: Optional[str] = None
    position: int = 0

class PlaylistManager:
    """High-level playlist orchestration."""
    def __init__(self, repo):
        self.repo = repo  # StorageRepository

    # --- Playlists ---
    def create_playlist(self, user_id: int, name: str, description: str = "", is_public: bool = False) -> int:
        return self.repo.create_playlist(user_id, name, description, is_public)

    def list_playlists(self, user_id: int) -> List[dict]:
        return self.repo.list_playlists(user_id)

    def get_playlist(self, playlist_id: int, user_id: int) -> Optional[dict]:
        return self.repo.get_playlist(playlist_id, user_id)

    def update_playlist_meta(self, playlist_id: int, user_id: int, *, name: str, description: str, is_public: bool):
        self.repo.update_playlist_meta(playlist_id, user_id, name, description, is_public)

    def share_link(self, playlist_id: int, user_id: int) -> str:
        return self.repo.ensure_share_token(playlist_id, user_id)

    def get_public_playlist_by_token(self, token: str) -> Optional[dict]:
        return self.repo.get_public_playlist_by_token(token)

    # --- Tracks in a playlist ---
    def add_track(self, playlist_id: int, track: Track):
        self.repo.insert_playlist_track(playlist_id, track)

    def remove_track(self, playlist_id: int, track_id: int, user_id: int):
        self.repo.delete_playlist_track(playlist_id, track_id, user_id)

    def list_tracks(self, playlist_id: int, user_id: Optional[int] = None):
        return self.repo.fetch_playlist_tracks(playlist_id, user_id)

    def move_track(self, playlist_id: int, track_id: int, direction: str, user_id: int):
        """direction: 'up' or 'down'"""
        self.repo.reorder_track(playlist_id, track_id, direction, user_id)

    def clear(self, playlist_id: int, user_id: int):
        self.repo.clear_playlist_tracks(playlist_id, user_id)

    # --- Top 10 export (CSV) kept for convenience ---
    def top10(self, playlist_id: int, user_id: int):
        return self.repo.fetch_playlist_tracks(playlist_id, user_id, limit=10)
