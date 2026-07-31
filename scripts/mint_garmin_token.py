"""Mint a Garmin OAuth token blob for the Streamlit dashboard.

Run this LOCALLY (from your own IP, not the shared Streamlit Cloud IP):

    # provide credentials via environment or a local .env file
    set GARMIN_EMAIL=you@example.com        # PowerShell: $env:GARMIN_EMAIL="you@example.com"
    set GARMIN_PASSWORD=your-password
    venv_garmin/Scripts/python.exe scripts/mint_garmin_token.py

Copy the printed blob into Streamlit Cloud -> Settings -> Secrets as:

    garmin_token_base64 = "<blob>"

The token grants ~1 year of account access; treat it like a password. Never commit it.
"""
import os
import sys

from dotenv import load_dotenv
from garminconnect import Garmin


def main():
    load_dotenv()
    email = os.getenv("GARMIN_EMAIL")
    password = os.getenv("GARMIN_PASSWORD")
    if not email or not password:
        print("ERROR: set GARMIN_EMAIL and GARMIN_PASSWORD (environment or .env).")
        return 1

    print(f"Logging in as {email} ...")
    client = Garmin(email, password)
    client.login()  # full SSO from this local machine's IP
    blob = client.garth.dumps()

    print("\n=== SUCCESS. Add this to Streamlit Cloud -> Settings -> Secrets ===\n")
    print('garmin_token_base64 = "PASTE_THE_LINE_BELOW"')
    print("\n" + blob + "\n")
    print("=== Keep it secret. Do not commit it. ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
