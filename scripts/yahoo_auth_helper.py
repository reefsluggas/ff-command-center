"""
One-time Yahoo OAuth setup. Run this ONCE on your own computer:

    pip install requests
    python yahoo_auth_helper.py

It will:
  1. Ask for your Yahoo app's Client ID and Client Secret
     (create the app at https://developer.yahoo.com/apps/create/ --
      API Permissions: Fantasy Sports, Read. Redirect URI: leave blank /
      choose "Installed Application" so out-of-band codes work.)
  2. Give you a URL to open in any browser -- log in, approve, and Yahoo
     shows you a short code.
  3. Exchange that code and print your REFRESH TOKEN.

Then add three repo secrets on GitHub (Settings > Secrets > Actions):
    YAHOO_CLIENT_ID, YAHOO_CLIENT_SECRET, YAHOO_REFRESH_TOKEN

The refresh token does not expire with normal use; the Action uses it to
mint a fresh access token on every run. Your Yahoo password is never
stored anywhere.
"""

import requests

TOKEN_URL = "https://api.login.yahoo.com/oauth2/get_token"
AUTH_URL = "https://api.login.yahoo.com/oauth2/request_auth"


def main():
    cid = input("Yahoo Client ID: ").strip()
    csec = input("Yahoo Client Secret: ").strip()

    url = f"{AUTH_URL}?client_id={cid}&redirect_uri=oob&response_type=code"
    print("\nOpen this URL in a browser, log in, approve, and copy the code:\n")
    print(url + "\n")
    code = input("Paste the code here: ").strip()

    resp = requests.post(TOKEN_URL, data={
        "client_id": cid,
        "client_secret": csec,
        "redirect_uri": "oob",
        "code": code,
        "grant_type": "authorization_code",
    }, timeout=30)
    resp.raise_for_status()
    tok = resp.json()
    print("\nSUCCESS. Add these three repo secrets on GitHub:\n")
    print(f"  YAHOO_CLIENT_ID     = {cid}")
    print(f"  YAHOO_CLIENT_SECRET = {csec}")
    print(f"  YAHOO_REFRESH_TOKEN = {tok['refresh_token']}")


if __name__ == "__main__":
    main()
