import gspread
from google.oauth2.service_account import Credentials
from config import GOOGLE_SHEETS_ID, GOOGLE_CREDENTIALS_FILE

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

def get_client():
    creds = Credentials.from_service_account_file(GOOGLE_CREDENTIALS_FILE, scopes=SCOPES)
    return gspread.authorize(creds)

def get_loyalty_sheet():
    client = get_client()
    return client.open_by_key(GOOGLE_SHEETS_ID).worksheet("Loyalty")

def get_purchases_sheet():
    client = get_client()
    return client.open_by_key(GOOGLE_SHEETS_ID).worksheet("Purchases")

def find_user_row(sheet, user_id: int):
    col = sheet.col_values(1)
    for i, val in enumerate(col):
        if val == str(user_id):
            return i + 1
    return None

def find_user_row_by_username(sheet, username: str):
    col = sheet.col_values(3)
    for i, val in enumerate(col):
        if val.lower().strip().lstrip("@") == username.lower().strip().lstrip("@"):
            return i + 1
    return None

def ensure_user_exists(user_id: int, name: str, username: str):
    sheet = get_loyalty_sheet()
    row = find_user_row(sheet, user_id)
    if row is None:
        sheet.append_row([str(user_id), name, username, 0])

def get_user_points(user_id: int):
    sheet = get_loyalty_sheet()
    row = find_user_row(sheet, user_id)
    if row is None:
        return None
    return int(sheet.cell(row, 4).value or 0)

def get_user_id_by_username(username: str):
    sheet = get_loyalty_sheet()
    row = find_user_row_by_username(sheet, username)
    if row is None:
        return None, None
    user_id = sheet.cell(row, 1).value
    name = sheet.cell(row, 2).value
    return user_id, name

def add_points(user_id: int, amount: int) -> int:
    sheet = get_loyalty_sheet()
    row = find_user_row(sheet, user_id)
    if row is None:
        return None
    current = int(sheet.cell(row, 4).value or 0)
    new_total = current + amount
    sheet.update_cell(row, 4, new_total)
    return new_total

def deduct_points(user_id: int, amount: int):
    sheet = get_loyalty_sheet()
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
    sheet = get_loyalty_sheet()
    rows = sheet.get_all_records()
    return [
        {
            "name": r.get("name", "Unknown"),
            "username": r.get("username", ""),
            "points": r.get("points", 0),
        }
        for r in rows
    ]

def get_unprocessed_purchases():
    sheet = get_purchases_sheet()
    all_rows = sheet.get_all_values()
    unprocessed = []
    for i, row in enumerate(all_rows):
        if i == 0:
            continue
        if len(row) >= 2 and row[0].strip():
            status = row[3] if len(row) > 3 else ""
            if status.lower().strip() != "processed":
                unprocessed.append({
                    "row_index": i + 1,
                    "username": row[0].strip(),
                    "amount": row[1].strip(),
                    "date": row[2].strip() if len(row) > 2 else "",
                })
    return unprocessed

def mark_purchase_processed(row_index: int, points_awarded: int):
    sheet = get_purchases_sheet()
    sheet.update_cell(row_index, 4, "Processed")
    sheet.update_cell(row_index, 5, str(points_awarded))
