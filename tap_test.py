#!/usr/bin/env python3
"""Quick local check that your Tap access token works.

Reuses your token to fetch and print your current session. Nothing leaves your
machine.

Usage:
    pip install requests
    python tap_test.py
"""
import getpass
import sys

try:
    import requests
except ImportError:
    sys.exit("Run:  pip install requests")

# Public app-level key (not a personal secret).
FIREBASE_KEY = "AIzaSyDsIZ5gM2iTOtP1KVcgKN8-FYjOBoobUis"
API_BASE = "https://tap-electric-app-api.azurewebsites.net/api"
GATEWAY_KEY = "5l^01Wmxs5ux"
BASE_HEADERS = {
    "x-api-key": GATEWAY_KEY,
    "x-app-version": "1.175.0",
    "x-tenant-id": "tap",
    "user-agent": "Dart/3.12 (dart:io)",
}


def main():
    rt = getpass.getpass("Paste your Tap refresh token (hidden): ").strip()

    print("\n[1/2] Trading refresh token for an idToken (securetoken)...")
    r = requests.post(
        "https://securetoken.googleapis.com/v1/token",
        params={"key": FIREBASE_KEY},
        data={"grant_type": "refresh_token", "refresh_token": rt},
        timeout=20,
    )
    if r.status_code != 200:
        print("  Refresh failed:", r.status_code, r.text[:200])
        print("  -> token wrong/expired/revoked, or it was a partial 2FA token.")
        sys.exit(1)
    id_token = r.json()["id_token"]
    print("  OK.")

    print("[2/2] Fetching /api/4.0/home ...")
    headers = dict(BASE_HEADERS)
    headers["authorization"] = "Bearer " + id_token
    r = requests.get(API_BASE + "/4.0/home", headers=headers, timeout=20)
    print("  status:", r.status_code)
    if r.status_code != 200:
        print("  body:", r.text[:300])
        sys.exit(1)
    home = r.json()

    sessions = home.get("active_sessions") or []
    print("\nActive sessions:", len(sessions))
    for s in sessions:
        ld = s.get("location_details", {})
        print("  -------------------------------------------")
        print("   status :", s.get("status"))
        print("   energy :", s.get("energy_kwh"), "kWh")
        print("   power  :", s.get("speed_kw"), "kW")
        print("   cost   : EUR", round((s.get("current_costs") or 0) / 100, 2))
        print("   charger:", ld.get("charger_name"), "/", ld.get("operator_name"))
        print("   where  :", ld.get("address"), ld.get("city"))
    if not sessions:
        print("  (none right now - auth works; sensors fill in when you charge)")

    print("\nValidation complete - use this same refresh token in the HA integration.")


if __name__ == "__main__":
    main()
