from openpyxl import Workbook

from database.db import connect_db


XLSX_FILE = "feedback_export.xlsx"


def export_feedback_to_xlsx():
    conn = connect_db()
    cursor = conn.cursor()

    cursor.execute("""
    SELECT
        id,
        created_at,
        manager_id,
        manager_username,
        manager_first_name,
        client_name,
        event_date,
        event_format,
        guests_count,
        client_reaction,
        objections,
        next_step,
        comment
    FROM feedback
    ORDER BY id DESC
    """)

    rows = cursor.fetchall()
    conn.close()

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Feedback"

    headers = [
        "ID",
        "Created At",
        "Manager ID",
        "Manager Username",
        "Manager First Name",
        "Client Name",
        "Event Date",
        "Event Format",
        "Guests Count",
        "Client Reaction",
        "Objections",
        "Next Step",
        "Comment",
    ]

    sheet.append(headers)

    for row in rows:
        sheet.append(row)

    workbook.save(XLSX_FILE)

    return XLSX_FILE
