from models import Track

def test_storage_crud(tmp_db_path):
    from storage import StorageRepository
    repo = StorageRepository(f"sqlite:///{tmp_db_path}")

    uid = repo.create_user("u1", "pw")
    pid = repo.create_playlist(uid, "P1", "d", False)

    # insert track
    repo.insert_playlist_track(pid, Track(title="A", artist="X", url="", mbid="1"))
    repo.insert_playlist_track(pid, Track(title="B", artist="X", url="", mbid="2"))

    tracks = repo.fetch_playlist_tracks(pid, user_id=uid)
    assert len(tracks) == 2
    assert tracks[0]["title"] == "A"
    assert tracks[1]["title"] == "B"

    # reorder (down then up)
    repo.reorder_track(pid, tracks[0]["id"], "down", user_id=uid)
    tracks2 = repo.fetch_playlist_tracks(pid, user_id=uid)
    assert tracks2[0]["title"] == "B"

    repo.reorder_track(pid, tracks2[0]["id"], "up", user_id=uid)
    tracks3 = repo.fetch_playlist_tracks(pid, user_id=uid)
    assert tracks3[0]["title"] == "A"

    # share token
    token = repo.ensure_share_token(pid, uid)
    assert token

    # delete playlist
    ok = repo.delete_playlist(pid, uid)
    assert ok
