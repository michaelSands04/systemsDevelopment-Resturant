def _login(client, username, password):
    return client.post(
        "/login",
        data={"username": username, "password": password},
        follow_redirects=True,
    )

def _add_to_cart(client, item_id=1):
    return client.post(f"/cart/add/{item_id}", follow_redirects=True)

def test_checkout_creates_order_and_visible_in_my_orders(client):
    # login as normal user
    r = _login(client, "testuser", "Password123!")
    assert r.status_code == 200

    # add something to cart
    r = _add_to_cart(client, 1)
    assert r.status_code == 200

    # place order 
    r = client.post("/checkout", follow_redirects=True)
    assert r.status_code == 200

    # my orders page should show an order 
    r = client.get("/orders")
    assert r.status_code == 200
    body = (r.data or b"").lower()
    assert b"order" in body  

def test_my_orders_requires_login(client):
    r = client.get("/orders", follow_redirects=False)
    # either redirect to login or show warning
    assert r.status_code in (302, 401, 403)

def test_admin_orders_requires_admin(client):
    # logged out: should redirect / block
    r = client.get("/admin/orders", follow_redirects=False)
    assert r.status_code in (302, 401, 403)

    # logged in as normal user: still blocked
    _login(client, "testuser", "Password123!")
    r = client.get("/admin/orders", follow_redirects=False)
    assert r.status_code in (302, 401, 403)

def test_admin_can_view_admin_orders_page(client):
    _login(client, "admin", "AdminPass123!")
    r = client.get("/admin/orders")
    assert r.status_code == 200
    assert b"orders" in (r.data or b"").lower()
