# Tap Electric for Home Assistant

Unofficial Home Assistant integration that surfaces your live Tap Electric
charging sessions (including at public stations) as sensors.

> Community project, not affiliated with or endorsed by Tap Electric. For personal use.

> ⚠️ **100% vibe-coded, no guarantees.** Thrown together for personal use — expect
> rough edges, and use it at your own risk. No warranty, no support promised.

## Install (HACS)
1. HACS → three-dot menu → **Custom repositories**.
2. Add `https://github.com/WCAve/tap_electric_HA`, category **Integration**.
3. Install, then restart Home Assistant.

## Get an access token
The integration connects using an access token for your Tap account:

1. Go to **https://web.tapelectric.app** and sign in (enter the emailed code if asked).
2. Press **F12** → **Console** tab.
   (If it warns about pasting, type `allow pasting` and press Enter first.)
3. Paste this line and press Enter:

   ```js
   (async()=>{const d=await new Promise(r=>{const q=indexedDB.open("firebaseLocalStorageDb");q.onsuccess=()=>r(q.result)});const all=await new Promise(r=>{const q=d.transaction("firebaseLocalStorage","readonly").objectStore("firebaseLocalStorage").getAll();q.onsuccess=()=>r(q.result)});for(const row of all){const v=row.value||row;if(v&&v.stsTokenManager&&v.stsTokenManager.refreshToken){console.log(v.stsTokenManager.refreshToken);return"^ copy the token above";}}return"not found - are you signed in?";})()
   ```
4. Copy the long string it prints.

(Keep that token private — it's access to your account. It's long-lived; the
integration reuses it automatically. If you change your password or sign out
everywhere, repeat these steps for a new one.)

## Set up
1. Settings → Devices & Services → **Add Integration** → **Tap Electric**.
2. Paste the token.

## Entities
One **Tap Electric** device:
- **Charging** (binary sensor)
- **Charging status**, **Session energy** (kWh), **Charging power** (kW),
  **Session cost**, **Price per kWh**, **Charger**, **Operator**, **Location**,
  **Session start**

## Options
Integration → **Configure** → poll interval (default 60s).

## Notes
- Unofficial; relies on app behaviour that can change, so a Tap app update may
  occasionally require an update here.
- The only value tied to your account is the access token you paste at setup — it
  stays in your Home Assistant config. Other identifiers in the code are public,
  app-level values, not personal secrets.

## License
MIT — see [LICENSE](LICENSE). Provided as-is, without warranty of any kind.
