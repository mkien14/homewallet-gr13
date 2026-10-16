def H(make_token, sub):
    return {"Authorization": f"Bearer {make_token(sub=sub)}"}


def test_me_creates_user_lazily(db_app, make_token):
    r = db_app.test_client().get("/api/me", headers=H(make_token, "sub-a"))
    body = r.get_json()
    assert r.status_code == 200
    assert body["user"]["email"] == "sub-a@test.local"
    assert body["household"] is None


def test_create_and_join(db_app, make_token):
    c = db_app.test_client()
    r = c.post("/api/households", json={"name": "Nhà A"}, headers=H(make_token, "sub-a"))
    assert r.status_code == 201 and r.get_json()["role"] == "owner"
    code = r.get_json()["invite_code"]

    r = c.post("/api/households/join", json={"invite_code": code}, headers=H(make_token, "sub-b"))
    assert r.status_code == 200
    assert r.get_json()["role"] == "member"
    assert "invite_code" not in r.get_json()  


def test_invalid_invite_code(db_app, make_token):
    r = db_app.test_client().post("/api/households/join", json={"invite_code": "ZZZZZZZZ"},
                                  headers=H(make_token, "sub-a"))
    assert r.status_code == 404


def test_cannot_have_two_households(db_app, make_token):
    c = db_app.test_client()
    h = H(make_token, "sub-a")
    assert c.post("/api/households", json={"name": "Nhà 1"}, headers=h).status_code == 201
    assert c.post("/api/households", json={"name": "Nhà 2"}, headers=h).status_code == 409


def test_cross_household_access_denied(db_app, make_token):
    """AC3: truy cập chéo hộ bị từ chối."""
    c = db_app.test_client()
    hid_a = c.post("/api/households", json={"name": "Nhà A"}, headers=H(make_token, "sub-a")).get_json()["id"]
    c.post("/api/households", json={"name": "Nhà B"}, headers=H(make_token, "sub-b"))
    r = c.get(f"/api/households/{hid_a}/members", headers=H(make_token, "sub-b"))
    assert r.status_code == 404
    assert c.get(f"/api/households/{hid_a}/members", headers=H(make_token, "sub-c")).status_code == 404


def test_member_cannot_remove_but_owner_can(db_app, make_token):
    c = db_app.test_client()
    hid = c.post("/api/households", json={"name": "Nhà A"}, headers=H(make_token, "sub-a")).get_json()
    c.post("/api/households/join", json={"invite_code": hid["invite_code"]}, headers=H(make_token, "sub-b"))
    members = c.get(f"/api/households/{hid['id']}/members", headers=H(make_token, "sub-a")).get_json()["members"]
    uid_a = next(m["id"] for m in members if m["role"] == "owner")
    uid_b = next(m["id"] for m in members if m["role"] == "member")

    assert c.delete(f"/api/households/{hid['id']}/members/{uid_a}", headers=H(make_token, "sub-b")).status_code == 403
    assert c.delete(f"/api/households/{hid['id']}/members/{uid_a}", headers=H(make_token, "sub-a")).status_code == 422
    assert c.delete(f"/api/households/{hid['id']}/members/{uid_b}", headers=H(make_token, "sub-a")).status_code == 204


def test_rotate_invite_code(db_app, make_token):
    c = db_app.test_client()
    h = c.post("/api/households", json={"name": "Nhà A"}, headers=H(make_token, "sub-a")).get_json()
    r = c.post(f"/api/households/{h['id']}/invite-code", headers=H(make_token, "sub-a"))
    assert r.status_code == 200 and r.get_json()["invite_code"] != h["invite_code"]
    r = c.post("/api/households/join", json={"invite_code": h["invite_code"]}, headers=H(make_token, "sub-b"))
    assert r.status_code == 404