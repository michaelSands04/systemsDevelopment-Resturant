def test_home_ok(client):
    r = client.get("/")
    assert r.status_code == 200

def test_menu_ok(client):
    r = client.get("/menu")
    
    assert r.status_code in (200, 302)

def test_reviews_ok(client):
    r = client.get("/reviews")
    assert r.status_code in (200, 302)
