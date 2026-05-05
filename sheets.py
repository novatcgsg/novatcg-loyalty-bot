import gspread
from google.oauth2.service_account import Credentials
from config import GOOGLE_SHEETS_ID, GOOGLE_CREDENTIALS_FILE

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

def get_sheet():
    creds = Credentials.from_service_account_file(GOOGLE_CREDENTIALS_FILE, scopes=SCOPES)
    client = gspread.authorize(creds)
    sheet = client.open_by_key(GOOGLE_SHEETS_ID).sheet1
    return sheet

def find_user_row(sheet, user_id: int):
    col = sheet.col_values(1)
    for i, val in enumerate(col):
        if val == str(user_id):
            return i + 1
    return None

def ensure_user_exists(user_id: int, name: str, username: str):
    sheet = get_sheet()
    row = find_user_row(sheet, user_id)
    if row is None:
        sheet.append_row([str(user_id), name, username, 0])

def get_user_points(user_id: int):
    sheet = get_sheet()
    row = find_user_row(sheet, user_id)
    if row is None:
        return None
    return int(sheet.cell(row, 4).value or 0)

def add_points(user_id: int, amount: int) -> int:
    sheet = get_sheet()
    row = find_user_row(sheet, user_id)
    if row is None:
        return None
    current = int(sheet.cell(row, 4).value or 0)
    new_total = current + amount
    sheet.update_cell(row, 4, new_total)
    return new_total

def deduct_points(user_id: int, amount: int):
    sheet = get_sheet()
    row = find_user_row(sheet, user_id)
    if row is None:
        return None
    current = int(sheet.cell(row, 4).value or 0)
    if current < amount:
        return None
    new_total = current - amount
    sheet.update_cell(row, 4, new_total)
    return new_total

def redeem_points(user_id: int, amount: int) -> bool:
    result = deduct_points(user_id, amount)
    return result is not None

def get_all_users():
    sheet = get_sheet()
    rows = sheet.get_all_records()
    return [
        {
            "name": r.get("name", "Unknown"),
            "username": r.get("username", ""),
            "points": r.get("points", 0),
        }
        for r in rows
    ]