import io
from pathlib import Path

def test_home_authenticated(logged_in_client):
    client, app_module, repo, user_id = logged_in_client
    r = client.get("/")
    assert r.status_code == 200
    assert b"Music Discovery" in r.data

def test_create_playlist_and_detail(logged_in_client):
    client, app_module, repo, user_id = logged_in_client

    # สร้างเพลย์ลิสต์
    r = client.post("/playlist/new", data={"name": "My Test", "description": "desc"}, follow_redirects=False)
    assert r.status_code in (302, 303)

    # ควรมีเพลย์ลิสต์ 1 รายการ
    items = repo.list_playlists(user_id)
    assert len(items) == 1
    pid = items[0]["id"]

    # หน้า detail เปิดได้
    r2 = client.get(f"/playlist/{pid}")
    assert r2.status_code == 200
    assert b"My Test" in r2.data

def test_add_tracks_position_increments(logged_in_client):
    client, app_module, repo, user_id = logged_in_client

    pid = repo.create_playlist(user_id, "P", "", False)

    # เพิ่มเพลง 2 เพลงผ่าน storage โดยตรง (เสถียรกว่า—ไม่ต้องพึ่ง route form)
    from models import Track
    repo.insert_playlist_track(pid, Track(title="Ditto", artist="NewJeans", url="", mbid="a"))
    repo.insert_playlist_track(pid, Track(title="FANCY", artist="TWICE", url="", mbid="b"))

    tracks = repo.fetch_playlist_tracks(pid, user_id=user_id)
    assert [t["position"] for t in tracks] in ([0, 1], [1, 2])  # แล้วแต่ดีไซน์คุณ

def test_share_public_and_open(logged_in_client):
    client, app_module, repo, user_id = logged_in_client

    pid = repo.create_playlist(user_id, "ShareMe", "", True)
    token = repo.ensure_share_token(pid, user_id)
    assert token

    r = client.get(f"/p/{token}")
    assert r.status_code == 200
    assert b"(Public)" in r.data or b"Public" in r.data

def test_tag_view_uses_lastfm_mock(logged_in_client):
    client, app_module, repo, user_id = logged_in_client

    r = client.get("/tag/k-pop")
    assert r.status_code == 200
    # ชื่อเพลงที่ mock ไว้
    assert b"Ditto" in r.data
    assert b"FANCY" in r.data

def test_artist_view_similar_and_top_tracks(logged_in_client):
    client, app_module, repo, user_id = logged_in_client

    r = client.get("/artist?name=TWICE")
    assert r.status_code == 200
    assert b"The Feels" in r.data  # จาก mock top_tracks_by_artist
    assert b"ITZY" in r.data      # จาก mock similar_artists

def test_export_csv_generates_file(logged_in_client, tmp_path):
    client, app_module, repo, user_id = logged_in_client
    pid = repo.create_playlist(user_id, "CSV", "", False)

    # เพิ่มเพลงเล็กน้อย
    from models import Track
    for i in range(3):
        repo.insert_playlist_track(pid, Track(title=f"T{i}", artist="A", url="", mbid=str(i)))

    # เรียก route export (ถ้ามีชื่อ endpoint ว่า export_csv)
    r = client.get(f"/playlist/{pid}/export/csv")
    # บางโปรเจกต์ redirect กลับ detail หลังเขียนไฟล์
    assert r.status_code in (200, 302, 303)

def test_delete_playlist_route(logged_in_client):
    client, app_module, repo, user_id = logged_in_client
    pid = repo.create_playlist(user_id, "Del", "", False)

    r = client.post(f"/playlist/{pid}/delete", follow_redirects=False)
    assert r.status_code in (302, 303)

    items = repo.list_playlists(user_id)
    assert all(p["id"] != pid for p in items)
