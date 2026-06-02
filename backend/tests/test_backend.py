"""Smoke test for the Unorthodox Writer backend.

Run with (from backend/):
    python3 tests/test_backend.py
    or
    pytest tests/test_backend.py -v
"""

import json
import time
import sys
import os

# Ensure backend is on the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import httpx

BASE = "http://127.0.0.1:8000"

passed = 0
failed = 0


def log(prefix: str, msg: str):
    print(f"  [{prefix}] {msg}")


def ok(msg: str):
    global passed
    passed += 1
    log("PASS", msg)


def fail(msg: str):
    global failed
    failed += 1
    log("FAIL", msg)


def expect_status(r: httpx.Response, expected: int, label: str) -> dict | None:
    if r.status_code == expected:
        ok(f"{label} → {expected}")
        try:
            return r.json()
        except Exception:
            return None
    else:
        fail(f"{label} → expected {expected}, got {r.status_code}: {r.text[:200]}")
        return None


def run_tests():
    client = httpx.Client(timeout=30)
    token = None
    story_id = None

    print("\n=== Auth Tests ===")

    # Use a unique username for each test run to ensure register succeeds
    ts = int(time.time())
    username = f"testuser_{ts}"
    email = f"test_{ts}@example.com"

    # 1. Register
    r = client.post(f"{BASE}/api/auth/register", json={
        "username": username,
        "email": email,
        "password": "secret123",
    })
    data = expect_status(r, 201, "POST /api/auth/register")
    if data:
        token = data.get("access_token")
        assert data["username"] == username
        assert data["tier"] == "free"
        ok("Register returned correct user data + token")

    if not token:
        fail("No token — cannot proceed with auth-required tests")
        return

    headers = {"Authorization": f"Bearer {token}"}

    # 2. Login
    r = client.post(f"{BASE}/api/auth/login", json={
        "username": username,
        "password": "secret123",
    })
    data = expect_status(r, 200, "POST /api/auth/login")
    if data:
        token = data["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        ok("Login successful, refreshed token")

    # 3. Me
    r = client.get(f"{BASE}/api/auth/me", headers=headers)
    data = expect_status(r, 200, "GET /api/auth/me")
    if data:
        assert data["username"] == username

    # 4. Login fail
    r = client.post(f"{BASE}/api/auth/login", json={
        "username": username,
        "password": "wrongpass",
    })
    expect_status(r, 401, "POST /api/auth/login (bad pw)")

    # 5. Duplicate register
    r = client.post(f"{BASE}/api/auth/register", json={
        "username": username,
        "email": f"diff_{ts}@example.com",
        "password": "secret123",
    })
    expect_status(r, 400, "POST /api/auth/register (dup username)")

    print("\n=== Story Tests ===")

    # 6. Create story
    r = client.post(f"{BASE}/api/stories", headers=headers, json={
        "prompt": "A dragon discovers a library.",
        "genre": "fantasy",
        "style": "whimsical",
        "max_words": 200,
        "pov": "first-person",
    })
    data = expect_status(r, 201, "POST /api/stories")
    if data:
        story_id = data["id"]
        assert data["status"] == "generating"
        ok(f"Story created: {story_id}")

    # 7. List stories
    r = client.get(f"{BASE}/api/stories", headers=headers)
    data = expect_status(r, 200, "GET /api/stories")
    if data:
        assert isinstance(data, list)
        assert len(data) >= 1
        ok(f"Listed {len(data)} stories")

    # 8. Get single story
    if story_id:
        r = client.get(f"{BASE}/api/stories/{story_id}", headers=headers)
        data = expect_status(r, 200, "GET /api/stories/{id}")
        if data:
            assert data["id"] == story_id

    # 9. Story not found
    r = client.get(f"{BASE}/api/stories/nonexistent", headers=headers)
    expect_status(r, 404, "GET /api/stories/nonexistent")

    # 10. Tier status
    r = client.get(f"{BASE}/api/tiers/status", headers=headers)
    data = expect_status(r, 200, "GET /api/tiers/status")
    if data:
        assert data["tier"] == "free"
        assert data["daily_limit"] == 5
        assert data["max_saved"] == 3
        ok("Tier status correct")

    # 11. Tier enforcement — too many words
    r = client.post(f"{BASE}/api/stories", headers=headers, json={
        "prompt": "Test.",
        "max_words": 9999,  # over 500 free limit
    })
    expect_status(r, 402, "POST /api/stories (word limit exceeded)")

    print("\n=== SSE Stream Test ===")
    if story_id:
        print(f"  Streaming story {story_id}...")
        r = client.get(f"{BASE}/api/stories/{story_id}/stream", headers=headers)
        if r.status_code == 200:
            ok("SSE stream connected (200)")
            chunks = 0
            complete = False
            error = False
            # httpx reads the full stream
            for line in r.text.splitlines():
                if line.startswith("data:"):
                    try:
                        event = json.loads(line[5:].strip())
                        t = event.get("type")
                        if t == "progress":
                            print(f"    [progress] stage={event.get('stage')} msg={event.get('message')}")
                        elif t == "chunk":
                            chunks += 1
                            print(f"    [chunk] text={event.get('text', '')[:50]}...")
                        elif t == "complete":
                            complete = True
                            print(f"    [complete] word_count={event.get('word_count')}")
                        elif t == "error":
                            error = True
                            print(f"    [error] {event.get('message')}")
                    except json.JSONDecodeError:
                        pass
            ok(f"SSE done — chunks: {chunks}, complete: {complete}, error: {error}")

            # Verify the story was marked complete
            r2 = client.get(f"{BASE}/api/stories/{story_id}", headers=headers)
            if r2.status_code == 200:
                data2 = r2.json()
                if data2["status"] == "complete":
                    ok("Story status updated to 'complete' after SSE")
                else:
                    fail(f"Story status is {data2['status']}, expected 'complete'")
        else:
            fail(f"SSE failed: {r.status_code}")

    # 12. Unauthenticated
    print("\n=== Auth Required Tests ===")
    r = client.get(f"{BASE}/api/stories")
    expect_status(r, 401, "GET /api/stories (no auth)")
    r = client.get(f"{BASE}/api/tiers/status")
    expect_status(r, 401, "GET /api/tiers/status (no auth)")

    print("\n=== Health ===")
    r = client.get(f"{BASE}/api/health")
    expect_status(r, 200, "GET /api/health")

    # Summary
    print(f"\n{'='*40}")
    print(f"Results: {passed} passed, {failed} failed")
    print(f"{'='*40}")

    client.close()
    return failed == 0


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
