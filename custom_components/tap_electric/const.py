"""Constants for the Tap Electric integration."""
from __future__ import annotations

DOMAIN = "tap_electric"

# The identifiers below are public, app-level values (shipped in the Tap client),
# not personal secrets. The only account-specific value is the access token the
# user provides at setup, which is never stored in this repository. (GitHub secret
# scanning flags Google API keys by pattern, so its alert here is a false positive.)
FIREBASE_API_KEY = "AIzaSyDsIZ5gM2iTOtP1KVcgKN8-FYjOBoobUis"
TOKEN_URL = "https://securetoken.googleapis.com/v1/token"
API_BASE = "https://tap-electric-app-api.azurewebsites.net/api"
GATEWAY_KEY = "5l^01Wmxs5ux"
APP_VERSION = "1.175.0"
TENANT_ID = "tap"
USER_AGENT = "Dart/3.12 (dart:io)"

CONF_REFRESH_TOKEN = "refresh_token"
CONF_SCAN_INTERVAL = "scan_interval"
DEFAULT_SCAN_INTERVAL = 60  # seconds
