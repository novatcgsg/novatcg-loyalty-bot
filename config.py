import os
import json

# Telegram Bot Token
BOT_TOKEN = os.environ.get("BOT_TOKEN")

# Admin Telegram User IDs
ADMIN_IDS = [7627085639]

# Google Sheets ID
GOOGLE_SHEETS_ID = os.environ.get("GOOGLE_SHEETS_ID")

# Google Credentials (from environment variable)
GOOGLE_CREDENTIALS_FILE = "credentials.json"

# Write credentials.json from environment variable if it exists
creds_json = os.environ.get("GOOGLE_CREDENTIALS")
if creds_json:
    with open("credentials.json", "w") as f:
        f.write(creds_json)
