import sys, json
sys.stdout.reconfigure(encoding='utf-8')
import httpx

base = "http://127.0.0.1:8080"
c = httpx.Client(timeout=15)

def test(name, fn):
    try:
        result = fn()
        print(f"  [PASS] {name}: {result}")
        return result
    except Exception as e:
        print(f"  [FAIL] {name}: {e}")
        return None

print("=" * 60)
print("NAMI - COMPREHENSIVE API TEST SUITE")
print("=" * 60)

# 1. Frontend
print("\n--- 1. Frontend Serving ---")
test("GET / returns HTML", lambda: c.get(f"{base}/").status_code == 200)

# 2. Users & Auth
print("\n--- 2. Users & Auth ---")
users = test("GET /api/users", lambda: c.get(f"{base}/api/users").json())

test("POST /api/auth/register (TestUser)", lambda: c.post(
    f"{base}/api/auth/register",
    json={"username": "TestUser", "password": "test", "avatar": "⚡"}
).json())

users2 = test("GET /api/users (after register)", lambda: c.get(f"{base}/api/users").json())
test_user_id = None
if users2:
    for u in users2:
        if u.get("username") == "TestUser":
            test_user_id = u["id"]

test("POST /api/auth/login (TestUser)", lambda: c.post(
    f"{base}/api/auth/login",
    json={"username": "TestUser", "password": "test"}
).json())

test("POST /api/auth/register (duplicate)", lambda: c.post(
    f"{base}/api/auth/register",
    json={"username": "TestUser", "password": "x"}
).status_code == 400)

test("GET /api/auth/me (header)", lambda: c.get(
    f"{base}/api/auth/me",
    headers={"X-User-ID": test_user_id or "default"}
).json())

# 3. History Isolation
print("\n--- 3. History Isolation ---")
uid_a = test_user_id or "default"
uid_b = "default"

test(f"Save progress for {uid_a}", lambda: c.post(
    f"{base}/api/history/progress",
    json={"user_id": uid_a, "anime_title": "One Piece", "season": "Saison 1", "ep_id": "5", "position_sec": 600, "duration_sec": 1400},
    headers={"X-User-ID": uid_a}
).json())

hist_a = test(f"GET /api/history for {uid_a}", lambda: c.get(
    f"{base}/api/history", headers={"X-User-ID": uid_a}
).json())

hist_b = test(f"GET /api/history for {uid_b}", lambda: c.get(
    f"{base}/api/history", headers={"X-User-ID": uid_b}
).json())

isolation_ok = hist_a and "One Piece" in hist_a and (not hist_b or "One Piece" not in hist_b)
print(f"  [{'PASS' if isolation_ok else 'FAIL'}] History isolation between users: {isolation_ok}")

# 4. Toggle watched
print("\n--- 4. Toggle Watched ---")
test("Toggle watched ep", lambda: c.post(
    f"{base}/api/history/toggle-watched",
    json={"user_id": uid_a, "anime_title": "One Piece", "season": "Saison 1", "ep_id": "5", "watched": True},
    headers={"X-User-ID": uid_a}
).json())

# 5. Mark season
print("\n--- 5. Mark Season ---")
test("Mark season watched", lambda: c.post(
    f"{base}/api/history/mark-season",
    json={"user_id": uid_a, "anime_title": "One Piece", "season": "Saison 1", "ep_ids": ["1","2","3","4","5"], "watched": True},
    headers={"X-User-ID": uid_a}
).json())

# 6. Search catalog
print("\n--- 6. Catalog Search ---")
test("Search empty (full catalog)", lambda: len(c.get(f"{base}/api/search?q=&source=all").json().get("results", [])))
test("Search 'Naruto'", lambda: c.get(f"{base}/api/search?q=Naruto&source=all").json().get("total"))

# 7. Catalog status
print("\n--- 7. Catalog Status ---")
test("GET /api/catalog/status", lambda: c.get(f"{base}/api/catalog/status").json())

# 8. Settings
print("\n--- 8. Settings ---")
test("GET /api/settings", lambda: c.get(f"{base}/api/settings").json())
test("POST /api/settings", lambda: c.post(
    f"{base}/api/settings",
    json={"root_folder": "/downloads", "default_provider": "all", "download_quality": "1080p"}
).json())

# 9. Downloads
print("\n--- 9. Downloads ---")
test("GET /api/downloads", lambda: c.get(f"{base}/api/downloads").json())

# 10. Submodule APIs
print("\n--- 10. Submodule APIs ---")
test("AnimeSama /status (port 5000)", lambda: c.get("http://127.0.0.1:5000/status").json())
try:
    r_va = c.get("http://127.0.0.1:8000/")
    test("VoirAnime / (port 8000)", lambda: r_va.json())
except:
    print("  [FAIL] VoirAnime / (port 8000): Not reachable")

print("\n" + "=" * 60)
print("ALL TESTS COMPLETE")
print("=" * 60)
