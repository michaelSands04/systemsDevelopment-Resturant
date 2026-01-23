def test_login_success_redirects(client):
    r = client.post(
        "/login",
        data={"username": "testuser", "password": "Password123!"},
        follow_redirects=False
    )
    assert r.status_code in (302, 303)


def test_logout_redirects(client):
    client.post("/login", data={"username": "testuser", "password": "Password123!"}, follow_redirects=False)
    r = client.post("/logout", follow_redirects=False)
    assert r.status_code in (302, 303)


def test_reviews_post_requires_login(client):
    r = client.post(
        "/reviews",
        data={"item_id": "1", "rating": "5", "comment": "Nice"},
        follow_redirects=False
    )
    assert r.status_code in (302, 303)
    assert "/login" in r.headers.get("Location", "")
