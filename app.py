import os
import time

from requests import session
os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"
from typing import Optional
from urllib.parse import urlencode
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, flash, send_file, jsonify
from dotenv import load_dotenv
from models import Track, Artist, PlaylistManager
from storage import StorageRepository
from lastfm import LastFMClient
from flask_login import LoginManager, login_user, login_required, logout_user, current_user, UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from requests_oauthlib import OAuth2Session

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "dev")
app.jinja_env.globals['os'] = os

db_url = os.getenv("DATABASE_URL", "sqlite:///music.db")
repo = StorageRepository(db_url)
playlist = PlaylistManager(repo)
lastfm_client = LastFMClient()


# --- Auth setup ---
login_manager = LoginManager(app)
login_manager.login_view = "login"

class AuthUser(UserMixin):
    def __init__(self, user_id: int, username: str):
        self.id = str(user_id)
        self.username = username

@login_manager.user_loader
def load_user(user_id: str):
    rec = repo.get_user_by_id(int(user_id))
    if not rec: return None
    return AuthUser(rec["id"], rec["username"])

# ----------------- Auth routes -----------------
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        if not username or not password:
            flash("กรอกชื่อผู้ใช้และรหัสผ่าน")
            return redirect(url_for("register"))
        if repo.get_user_by_username(username):
            flash("มีชื่อผู้ใช้นี้แล้ว")
            return redirect(url_for("register"))
        uid = repo.create_user(username, generate_password_hash(password))
        login_user(AuthUser(uid, username))
        flash("สมัครสมาชิกสำเร็จ")
        return redirect(url_for("index"))
    return render_template("login_register/register.html") if template_exists("login_register/register.html") else render_template("register.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        rec = repo.get_user_by_username(username)
        if not rec or not check_password_hash(rec["password_hash"], password):
            flash("เข้าสู่ระบบไม่สำเร็จ")
            return redirect(url_for("login"))
        login_user(AuthUser(rec["id"], rec["username"]))
        flash("เข้าสู่ระบบแล้ว")
        return redirect(url_for("index"))
    return render_template("login_register/login.html") if template_exists("login_register/login.html") else render_template("login.html")

@app.route("/logout")
@login_required
def logout():
    logout_user()
    flash("ออกจากระบบแล้ว")
    return redirect(url_for("index"))

# ----------------- Helpers -----------------
from flask import current_app
def template_exists(path: str) -> bool:
    try:
        current_app.jinja_env.get_template(path)
        return True
    except Exception:
        return False

# ----------------- Home / Search -----------------
@app.route("/")
@login_required
def index():
    default_genre = repo.get_default_genre(int(current_user.id))
    user_playlists = playlist.list_playlists(int(current_user.id))
    return render_template("index.html", tags=TAG_CARDS,default_genre=default_genre, user_playlists=user_playlists)

@app.route("/search", methods=["GET"])
@login_required
def search():
    q = request.args.get("q", "").strip()
    mode = request.args.get("mode", "genre")
    user_playlists = repo.list_playlists(current_user.id)
    if not q:
        flash("โปรดกรอกคำค้นหา")
        return redirect(url_for("index"))
    try:
        if mode == "artist":
            results = lastfm_client.top_tracks_by_artist(q, limit=30)
        else:
            results = lastfm_client.top_tracks_by_tag(q, limit=30)
        return render_template("search_results.html", q=q, mode=mode, results=results, user_playlists=user_playlists)
    except Exception as e:
        flash(f"เกิดข้อผิดพลาดในการค้นหา: {e}")
        return redirect(url_for("index"))

# ----------------- Artist view -----------------
@app.route("/artist")
@login_required
def artist_view():
    # รับพารามิเตอร์และ sanitize
    name = (request.args.get("name") or "").strip()
    limit = request.args.get("limit", default=12, type=int)
    match_threshold = request.args.get("min_match", default=0.15, type=float)  # ปรับได้ผ่าน query

    if not name:
        flash("ไม่พบชื่อศิลปิน")
        return redirect(url_for("index"))

    try:
        # แนะนำเปิด autocorrect=1 ให้ Last.fm ช่วยสะกด
        similar = lastfm_client.similar_artists(name, limit=limit, autocorrect=1)
        # กรองศิลปินที่คะแนน match ต่ำเกินไปออก (0..1)
        similar = [a for a in similar if float(a.get("match", 0.0)) >= match_threshold]

        top_tracks = lastfm_client.top_tracks_by_artist(name, limit=limit)

        if not similar and not top_tracks:
            flash("ไม่พบข้อมูลศิลปิน/เพลงที่เกี่ยวข้องจาก Last.fm")
            return redirect(url_for("index"))

        return render_template(
            "artist.html",
            name=name,
            similar=similar,
            top_tracks=top_tracks
        )
    except Exception as e:
        # คุณจะเห็น error ชัดขึ้นใน console; หน้าเว็บแจ้งสั้นๆพอ
        current_app.logger.exception("artist_view failed")
        flash(f"โหลดข้อมูลศิลปินไม่ได้: {e}")
        return redirect(url_for("index"))

# ----------------- Playlists (multi) -----------------
@app.route("/playlists")
@login_required
def playlists_view():
    items = playlist.list_playlists(int(current_user.id))
    return render_template("playlists.html", items=items)

@app.route("/playlist/new", methods=["POST"])
@login_required
def playlist_new():
    name = (request.form.get("name") or "New Playlist").strip()
    desc = (request.form.get("description") or "").strip()
    is_public = bool(request.form.get("is_public"))
    pid = playlist.create_playlist(int(current_user.id), name, desc, is_public)
    flash("สร้างเพลย์ลิสต์แล้ว")
    return redirect(url_for("playlist_detail", playlist_id=pid))

@app.route("/playlist/<int:playlist_id>")
@login_required
def playlist_detail(playlist_id: int):
    pl = playlist.get_playlist(playlist_id, int(current_user.id))
    if not pl:
        flash("ไม่พบเพลย์ลิสต์")
        return redirect(url_for("playlists_view"))
    tracks = playlist.list_tracks(playlist_id, int(current_user.id))
    return render_template("playlist_detail.html", pl=pl, tracks=tracks)

@app.route("/playlist/<int:playlist_id>/edit", methods=["POST"])
@login_required
def playlist_edit(playlist_id: int):
    name = (request.form.get("name") or "").strip()
    desc = (request.form.get("description") or "").strip()
    is_public = True if request.form.get("is_public") == "on" else False
    playlist.update_playlist_meta(playlist_id, int(current_user.id), name=name, description=desc, is_public=is_public)
    flash("บันทึกข้อมูลเพลย์ลิสต์แล้ว")
    return redirect(url_for("playlist_detail", playlist_id=playlist_id))

@app.post("/playlist/<int:playlist_id>/delete")
@login_required
def playlist_delete(playlist_id: int):
    try:
        ok = repo.delete_playlist(playlist_id, int(current_user.id))
        if ok:
            flash("ลบเพลย์ลิสต์เรียบร้อย")
        else:
            flash("ไม่พบเพลย์ลิสต์นี้หรือถูกลบไปแล้ว")
    except PermissionError:
        flash("คุณไม่มีสิทธิ์ลบเพลย์ลิสต์นี้")
    except Exception as e:
        current_app.logger.exception("delete playlist failed")
        flash(f"ลบเพลย์ลิสต์ไม่สำเร็จ: {e}")
    return redirect(url_for("playlists_view"))


@app.route("/playlist/<int:playlist_id>/share")
@login_required
def playlist_share(playlist_id: int):
    token = playlist.share_link(playlist_id, int(current_user.id))
    base = os.getenv("APP_BASE_URL", request.host_url.rstrip("/"))
    share_url = f"{base}/p/{token}"
    flash("สร้างลิงก์แชร์แล้ว คัดลอกลิงก์ด้านล่างได้เลย")
    return render_template("share.html", share_url=share_url)

@app.route("/p/<token>")
def public_playlist(token: str):
    # ใช้ repo (StorageRepository) แทน playlist
    pl = repo.get_public_playlist_by_token(token)
    if not pl or not pl.get("is_public"):
        flash("ไม่พบเพลย์ลิสต์สาธารณะ หรือเพลย์ลิสต์ถูกปิดแล้ว")
        return redirect(url_for("index"))

    # public view ไม่ต้องตรวจ owner => ไม่ต้องส่ง user_id
    tracks = repo.fetch_playlist_tracks(pl["id"])

    # ลิงก์แบบเต็มเพื่อคัดลอกง่าย (_external=True)
    share_url = url_for("public_playlist", token=token, _external=True)

    return render_template("playlist_public.html", pl=pl, tracks=tracks, share_url=share_url)

# ---- Track ops in a specific playlist ----
@app.route("/playlist/<int:playlist_id>/add", methods=["POST"])
@login_required
def playlist_add(playlist_id: int):
    try:
        data = request.get_json(silent=True) or request.form
        title = (data.get("title") or "").strip()
        artist = (data.get("artist") or "").strip()
        url_ = (data.get("url") or None)
        mbid = (data.get("mbid") or None)
        if not title or not artist:
            flash("เพิ่มเพลงไม่สำเร็จ: ข้อมูลไม่ครบ")
            return redirect(request.referrer or url_for("playlist_detail", playlist_id=playlist_id))
        playlist.add_track(playlist_id, Track(title=title, artist=artist, url=url_, mbid=mbid))
        flash("เพิ่มเพลงเข้ารายการแล้ว")
        return redirect(request.referrer or url_for("playlist_detail", playlist_id=playlist_id))
        if playlist_id <= 0:
            flash("โปรดเลือกเพลย์ลิสต์ให้ถูกต้อง")
        return redirect(url_for("playlists_view"))
    except Exception as e:
        app.logger.exception("playlist_add failed")
        flash(f"เพิ่มเพลงไม่สำเร็จ: {e}")
        return redirect(request.referrer or url_for("playlist_detail", playlist_id=playlist_id))

@app.route("/playlist/<int:playlist_id>/remove/<int:track_id>")
@login_required
def playlist_remove(playlist_id: int, track_id: int):
    playlist.remove_track(playlist_id, track_id, int(current_user.id))
    flash("ลบเพลงออกจากรายการแล้ว")
    return redirect(url_for("playlist_detail", playlist_id=playlist_id))

@app.route("/playlist/<int:playlist_id>/move/<int:track_id>/<direction>")
@login_required
def playlist_move(playlist_id: int, track_id: int, direction: str):
    if direction not in ("up", "down"):
        flash("ทิศทางไม่ถูกต้อง")
        return redirect(url_for("playlist_detail", playlist_id=playlist_id))
    playlist.move_track(playlist_id, track_id, direction, int(current_user.id))
    return redirect(url_for("playlist_detail", playlist_id=playlist_id))

@app.route("/playlist/<int:playlist_id>/clear")
@login_required
def playlist_clear(playlist_id: int):
    playlist.clear(playlist_id, int(current_user.id))
    flash("ล้างรายการแล้ว")
    return redirect(url_for("playlist_detail", playlist_id=playlist_id))

@app.route("/export/csv/<int:playlist_id>")
@login_required
def export_csv(playlist_id: int):
    path = repo.export_playlist_csv(playlist_id, int(current_user.id))
    return send_file(path, as_attachment=True, download_name=os.path.basename(path))

# ----------------- User Profile -----------------
@app.route("/profile/<username>")
@login_required
def profile(username: str):
    user = repo.get_user_by_username(username)
    if not user:
        flash("ไม่พบบัญชีผู้ใช้")
        return redirect(url_for("index"))

    # ดึงเพลย์ลิสต์พร้อมจำนวนเพลงในครั้งเดียว
    playlists = repo.list_playlists_with_counts(user["id"])
    stats = repo.get_user_music_stats(user["id"])
    total_tracks = stats["total_tracks"]

    return render_template(
        "profile.html",
        username=username,
        playlists=playlists,
        total_tracks=total_tracks,
        stats=stats
    )

# ----------------- Mood-based Recommendation -----------------
MOOD_TAGS = {
    # map คีย์เวิร์ด -> last.fm tag
    "อ่านหนังสือ": "chill",
    "อ่าน": "chill",
    "ชิล": "chill",
    "ชิลล์": "chill",
    "พักผ่อน": "ambient",
    "นอน": "sleep",
    "ออกกำลังกาย": "workout",
    "วิ่ง": "running",
    "โฟกัส": "focus",
    "ทำงาน": "work",
    "เศร้า": "sad",
    "สนุก": "party",
    "ขับรถ": "driving",
}
def resolve_mood_tag(text: str) -> str:
    t = text.lower()
    for k, v in MOOD_TAGS.items():
        if k in t:
            return v
    # fallback: ใช้คำที่ผู้ใช้กรอกเป็น tag โดยตรง
    return text.strip() or "chill"

@app.route("/mood", methods=["GET", "POST"])
@login_required
def mood():
    user_playlists = repo.list_playlists(current_user.id)
    if request.method == "POST":
        mood_text = (request.form.get("mood") or "").strip()
        tag = resolve_mood_tag(mood_text)
        try:
            results = lastfm_client.top_tracks_by_tag(tag, limit=30)
            return render_template("mood.html", mood_text=mood_text, tag=tag, results=results, user_playlists=user_playlists)
        except Exception as e:
            flash(f"แนะนำเพลงตามอารมณ์ไม่สำเร็จ: {e}")
            return redirect(url_for("mood"))
    return render_template("mood.html", mood_text=None, tag=None, results=None, user_playlists=user_playlists)

# ----------------- Spotify Export -----------------
SPOTIFY_AUTH_BASE = "https://accounts.spotify.com/authorize"
SPOTIFY_TOKEN_URL = "https://accounts.spotify.com/api/token"
SPOTIFY_API_BASE = "https://api.spotify.com/v1"

def _save_spotify_token(user_id: int, token: dict):
    """บันทึก access/refresh token ทุกครั้งที่รีเฟรชสำเร็จ"""
    expires_at = None
    if token.get("expires_at"):
        # เก็บเป็น ISO UTC (naive) เหมือนเดิม
        expires_at = datetime.utcfromtimestamp(token["expires_at"]).isoformat()
    repo.upsert_user_token(
        user_id,
        "spotify",
        token.get("access_token"),
        token.get("refresh_token"),  # บางครั้ง Spotify จะ “หมุน” refresh token ใหม่มาให้
        expires_at
    )
    
def spotify_session(token: dict | None = None):
    client_id = os.getenv("SPOTIFY_CLIENT_ID")
    client_secret = os.getenv("SPOTIFY_CLIENT_SECRET")
    redirect_uri = os.getenv("SPOTIFY_REDIRECT_URI")
    scope = "playlist-modify-public playlist-modify-private"

    # auto_refresh: ให้ OAuth2Session ต่ออายุ token อัตโนมัติเมื่อหมดอายุตาม expires_at
    extra = {"client_id": client_id, "client_secret": client_secret}
    return OAuth2Session(
        client_id=client_id,
        redirect_uri=redirect_uri,
        scope=scope,
        token=token,
        auto_refresh_url=SPOTIFY_TOKEN_URL,
        auto_refresh_kwargs=extra,
        token_updater=lambda t: _save_spotify_token(int(current_user.id), t),
    )

@app.route("/spotify/login")
@login_required
def spotify_login():
    sess = spotify_session()
    auth_url, state = sess.authorization_url(
        SPOTIFY_AUTH_BASE,
        show_dialog="true"  # บังคับหน้าต่างอนุญาต
    )
    session["spotify_oauth_state"] = state
    return redirect(auth_url)

@app.route("/spotify/callback")
@login_required
def spotify_callback():
    client_id = os.getenv("SPOTIFY_CLIENT_ID")
    client_secret = os.getenv("SPOTIFY_CLIENT_SECRET")

    # ตรวจ state ป้องกัน CSRF
    state = request.args.get("state")
    if not state or state != session.get("spotify_oauth_state"):
        flash("Invalid OAuth state")
        return redirect(url_for("playlists_view"))

    sess = spotify_session()
    # NOTE: requests-oauthlib จะจัดการ code ให้จาก authorization_response
    token = sess.fetch_token(
        SPOTIFY_TOKEN_URL,
        authorization_response=request.url,
        client_id=client_id,
        client_secret=client_secret,
        include_client_id=True,  # ชัดเจนว่าใช้ client_credentials ใน body
    )

    _save_spotify_token(int(current_user.id), token)

    flash("เชื่อมต่อ Spotify สำเร็จ")
    return redirect(url_for("playlists_view"))  

def _get_spotify_session_for_user(user_id: int) -> OAuth2Session | None:
    tok = repo.get_user_token(user_id, "spotify")
    if not tok:
        return None
    # สร้าง dict token ให้ครบสำหรับ OAuth2Session
    token = {
        "access_token": tok["access_token"],
        "refresh_token": tok.get("refresh_token"),
        # ถ้ามี expires_at (ISO) แปลงกลับเป็น timestamp ให้ oauthlib ใช้ auto refresh
        "expires_at": (
            datetime.fromisoformat(tok["expires_at"]).timestamp()
            if tok.get("expires_at") else None
        ),
        "token_type": "Bearer",
    }
    return spotify_session(token=token)

def _sp_get(sess: OAuth2Session, path: str, **kwargs):
    r = sess.get(f"{SPOTIFY_API_BASE}{path}", timeout=15, **kwargs)
    r.raise_for_status()
    return r.json()

def _sp_post(sess: OAuth2Session, path: str, json=None, **kwargs):
    r = sess.post(
        f"{SPOTIFY_API_BASE}{path}",
        json=json,
        timeout=15,
        **kwargs
    )
    # จัดการ 429 (rate limit) แบบง่ายๆ
    if r.status_code == 429:
        retry_after = int(r.headers.get("Retry-After", "1"))
        time.sleep(retry_after)
        r = sess.post(f"{SPOTIFY_API_BASE}{path}", json=json, timeout=15, **kwargs)
    r.raise_for_status()
    return r.json() if r.text else {}

def _spotify_get_user_id_sess(sess: OAuth2Session) -> str:
    me = _sp_get(sess, "/me")
    return me["id"]

def _spotify_create_playlist_sess(sess: OAuth2Session, user_spotify_id: str,
                                  name: str, description: str, public: bool) -> str:
    payload = {"name": name, "description": description, "public": public}
    created = _sp_post(sess, f"/users/{user_spotify_id}/playlists", json=payload)
    return created["id"]

def _spotify_search_track_uri_sess(sess: OAuth2Session, title: str, artist: str) -> Optional[str]:
    q = f"track:{title} artist:{artist}"
    data = _sp_get(sess, "/search", params={"q": q, "type": "track", "limit": 1})
    items = data.get("tracks", {}).get("items", [])
    if not items:
        return None
    return items[0]["uri"]

@app.route("/playlist/<int:playlist_id>/export/spotify")
@login_required
def export_spotify(playlist_id: int):
    sess = _get_spotify_session_for_user(int(current_user.id))
    if not sess:
        flash("กรุณาเชื่อมต่อ Spotify ก่อน")
        return redirect(url_for("spotify_login"))

    # เตรียมข้อมูลเพลย์ลิสต์
    pl = playlist.get_playlist(playlist_id, int(current_user.id))
    if not pl:
        flash("ไม่พบเพลย์ลิสต์")
        return redirect(url_for("playlists_view"))
    tracks = playlist.list_tracks(playlist_id, int(current_user.id))
    if not tracks:
        flash("เพลย์ลิสต์ว่าง")
        return redirect(url_for("playlist_detail", playlist_id=playlist_id))

    # สร้างเพลย์ลิสต์บน Spotify
    try:
        user_spotify_id = _spotify_get_user_id_sess(sess)
        sp_pl_id = _spotify_create_playlist_sess(
            sess, user_spotify_id, pl["name"], pl["description"], bool(pl["is_public"])
        )
    except Exception as e:
        flash(f"สร้างเพลย์ลิสต์บน Spotify ไม่สำเร็จ: {e}")
        return redirect(url_for("playlist_detail", playlist_id=playlist_id))

    # ค้นหา URIs ของเพลงทีละรายการ
    uris = []
    for t in tracks:
        uri = _spotify_search_track_uri_sess(sess, t["title"], t["artist"])
        if uri:
            uris.append(uri)
    if not uris:
        flash("หาเพลงบน Spotify ไม่เจอ")
        return redirect(url_for("playlist_detail", playlist_id=playlist_id))

    # เพิ่มเพลงทีละก้อน (สูงสุด 100/ครั้ง)
    try:
        for i in range(0, len(uris), 100):
            chunk = uris[i:i+100]
            _sp_post(sess, f"/playlists/{sp_pl_id}/tracks", json={"uris": chunk})
    except Exception as e:
        flash(f"เพิ่มเพลงลงเพลย์ลิสต์บน Spotify ไม่สำเร็จ: {e}")
        return redirect(url_for("playlist_detail", playlist_id=playlist_id))

    flash("ส่งออกเพลย์ลิสต์ไป Spotify สำเร็จ")
    return redirect(url_for("playlist_detail", playlist_id=playlist_id))

@app.route("/prefs/genre", methods=["POST"])
@login_required
def set_genre():
    g = request.form.get("genre", "pop").strip()
    repo.set_default_genre(int(current_user.id), g)   # หรือบันทึกใน DB/session ตามที่คุณใช้
    flash("บันทึกค่าเริ่มต้นของแนวเพลงแล้ว")
    return redirect(url_for("index"))

# --- Tag presets สำหรับหน้า Home ---
TAG_CARDS = [
    # slug, display_name, caption (optional)
    {"slug": "k-pop",       "name": "k-pop",       "caption": "Including Boa, 2NE1 and Big Bang"},
    {"slug": "pop",         "name": "pop",         "caption": "Including Michael Jackson, Madonna and The Beatles"},
    {"slug": "korean",      "name": "korean",      "caption": "Including Boa, Big Bang และ 소녀시대"},
    {"slug": "rnb",         "name": "rnb",         "caption": "Including Rihanna, Beyoncé and Alicia Keys"},
    {"slug": "electronic",  "name": "electronic",  "caption": "Including Daft Punk, The Prodigy and Depeche Mode"},
    {"slug": "thai",        "name": "thai",        "caption": "Including Tata Young, Lisa and Bodyslam"},
    {"slug": "swedish",     "name": "swedish",     "caption": "Including In Flames, The Knife and Lykke Li"},
    {"slug": "babymonster", "name": "babymonster", "caption": "Including Baby Monster, Baby Monster and Chiquita"},
    {"slug": "indie pop",   "name": "indie pop",   "caption": "Including Belle and Sebastian, MGMT and The Shins"},
    {"slug": "izone",       "name": "izone",       "caption": "Including IZ*ONE, LEE CHAE YEON and KWON EUNBI"},
    {"slug": "folk",        "name": "folk",        "caption": "Including Bob Dylan, Johnny Cash and Iron & Wine"},
    {"slug": "hip-hop",     "name": "hip-hop",     "caption": "Including Eminem, Kanye West and Gorillaz"},
]

@app.get("/tag/<string:tag>")
@login_required
def tag_view(tag: str):
    tracks = lastfm_client.top_tracks_by_tag(tag, limit=24)
    user_playlists = repo.list_playlists(int(current_user.id))
    return render_template("tag.html", tag=tag, tracks=tracks, user_playlists=user_playlists)

if __name__ == "__main__":
    app.run(ssl_context="adhoc")  # dev-only self-signed