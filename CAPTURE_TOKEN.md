# Getting an access token

The integration connects using an access token for your Tap account. To get yours:

1. Go to **https://web.tapelectric.app** and sign in (enter the emailed code if asked).
2. Press **F12** → **Console** tab.
   (If it warns about pasting, type `allow pasting` and press Enter first.)
3. Paste this line and press Enter:

    (async()=>{const d=await new Promise(r=>{const q=indexedDB.open("firebaseLocalStorageDb");q.onsuccess=()=>r(q.result)});const all=await new Promise(r=>{const q=d.transaction("firebaseLocalStorage","readonly").objectStore("firebaseLocalStorage").getAll();q.onsuccess=()=>r(q.result)});for(const row of all){const v=row.value||row;if(v&&v.stsTokenManager&&v.stsTokenManager.refreshToken){console.log(v.stsTokenManager.refreshToken);return"^ copy the token above";}}return"not found - are you signed in?";})()

4. Copy the string it prints.
5. In Home Assistant: **Settings → Devices & Services → Add Integration →
   Tap Electric**, and paste it.

Notes:
- The token is long-lived; the integration reuses it automatically.
- Keep it private — it's access to your account.
- Changed your password or signed out everywhere? Repeat these steps for a new one.
