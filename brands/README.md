# Brand icon

Icon files for submitting Tap Electric to the Home Assistant **brands** repo
(https://github.com/home-assistant/brands). That repo is what makes the icon
appear in Home Assistant and HACS instead of "icon not available".

To publish it:
1. Fork https://github.com/home-assistant/brands
2. Copy `custom_integrations/tap_electric/` from here into the fork at the same path:
   - `icon.png` (256×256)
   - `icon@2x.png` (512×512)
   (`logo.png` / `logo@2x.png` are optional; HA falls back to the icon.)
3. Open a PR. Once merged, the icon shows up automatically — no integration change needed.

Design: teal (#13C2C2) rounded square with a white charging bolt.
