def test_api_menu_ok(client):
    r = client.get("/api/menu")
    assert r.status_code == 200
    assert r.is_json
    data = r.get_json()
    assert isinstance(data, list)
    assert len(data) >= 1
    assert "name" in data[0]


def test_api_reviews_ok(client):
    r = client.get("/api/reviews?limit=5")
    assert r.status_code == 200
    assert r.is_json
    data = r.get_json()
    assert isinstance(data, list)


def test_api_reviews_invalid_item_id_400(client):
    r = client.get("/api/reviews?item_id=abc")
    assert r.status_code == 400
    assert r.is_json
    assert "error" in r.get_json()


def test_api_stats_ok(client):
    r = client.get("/api/stats?limit=5")
    assert r.status_code == 200
    assert r.is_json
    data = r.get_json()
    assert isinstance(data, list)
    assert len(data) >= 1
    assert "review_count" in data[0]
    assert "avg_rating" in data[0]
