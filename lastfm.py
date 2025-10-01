from __future__ import annotations
import os
import requests
from typing import List, Dict
from dotenv import load_dotenv
from functools import lru_cache

load_dotenv()

LASTFM_API_KEY = os.getenv("LASTFM_API_KEY", "")
LASTFM_BASE = "https://ws.audioscrobbler.com/2.0/"

def _pick_image(images: list, preferred=("extralarge","mega","large","medium")) -> str | None:
    by_size = {img.get("size"): img.get("#text") for img in images or []}
    for s in preferred:
        if by_size.get(s):
            return by_size[s]
    for img in images or []:
        if img.get("#text"):
            return img["#text"]
    return None

class LastFMClient:
    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or LASTFM_API_KEY
        if not self.api_key:
            raise RuntimeError("Missing LASTFM_API_KEY. Put it in .env")

    def _get(self, params: Dict) -> Dict:
        p = {
            "api_key": self.api_key,
            "format": "json",
        }
        p.update(params)
        r = requests.get(LASTFM_BASE, params=p, timeout=15)
        r.raise_for_status()
        data = r.json()
        # หาก Last.fm ส่ง error format กลับมา
        if isinstance(data, dict) and data.get("error"):
            raise RuntimeError(f"Last.fm error {data.get('error')}: {data.get('message')}")
        return data

    def top_tracks_by_tag(self, tag: str, limit: int = 20) -> List[Dict]:
        data = self._get({"method": "tag.getTopTracks", "tag": tag, "limit": limit})
        tracks = data.get("tracks", {}).get("track", [])
        return [
            {
                "title": t.get("name"),
                "artist": t.get("artist", {}).get("name"),
                "url": t.get("url"),
                "mbid": t.get("mbid")
            } for t in tracks
        ]

    def top_tracks_by_artist(self, artist: str, limit: int = 20) -> List[Dict]:
        data = self._get({"method": "artist.getTopTracks", "artist": artist, "limit": limit})
        tracks = data.get("toptracks", {}).get("track", [])
        return [
            {
                "title": t.get("name"),
                "artist": artist,
                "url": t.get("url"),
                "mbid": t.get("mbid")
            } for t in tracks
        ]

    @lru_cache(maxsize=512)
    def similar_artists(self, artist: str, limit: int = 12, autocorrect: int = 1) -> List[Dict]:
        """
        คืนรูปแบบ:
        [{"name","url","mbid","match"(0..1),"image"}]
        """
        data = self._get({
            "method": "artist.getSimilar",
            "artist": artist,
            "limit": limit,
            "autocorrect": autocorrect
        })
        artists = data.get("similarartists", {}).get("artist", [])
        result = []
        for a in artists:
            result.append({
                "name": a.get("name"),
                "url": a.get("url"),
                "mbid": a.get("mbid"),
                "match": float(a.get("match", 0.0)),
                "image": _pick_image(a.get("image", [])),
            })
        return result
