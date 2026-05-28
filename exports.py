from openpyxl import Workbook

from database.db import connect_db


FEEDBACK_XLSX_FILE = "feedback_export.xlsx"
EVENT_FEEDBACK_XLSX_FILE = "event_feedback_export.xlsx"


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
    sheet.title = "Meeting Feedback"

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

    workbook.save(FEEDBACK_XLSX_FILE)

    return FEEDBACK_XLSX_FILE


def export_event_feedback_to_xlsx():
    conn = connect_db()
    cursor = conn.cursor()

    cursor.execute("""
    SELECT
        id,
        created_at,
        executor_id,
        executor_username,
        executor_first_name,
        event_type,
        fact_guests,
        before_problems,
        during_problems,
        client_rating,
        what_went_well,
        what_to_improve,
        comment
    FROM event_feedback
    ORDER BY id DESC
    """)

    rows = cursor.fetchall()
    conn.close()

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Event Feedback"

    headers = [
        "ID",
        "Created At",
        "Executor ID",
        "Executor Username",
        "Executor First Name",
        "Event Type",
        "Fact Guests",
        "Before Problems",
        "During Problems",
        "Client Rating",
        "What Went Well",
        "What To Improve",
        "Comment",
    ]

    sheet.append(headers)

    for row in rows:
        sheet.append(row)

    workbook.save(EVENT_FEEDBACK_XLSX_FILE)

    return EVENT_FEEDBACK_XLSX_FILE
