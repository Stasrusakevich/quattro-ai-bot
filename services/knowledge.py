import os


KNOWLEDGE_DIR = "knowledge"


def load_knowledge_file(filename):
    path = os.path.join(KNOWLEDGE_DIR, filename)

    if not os.path.exists(path):
        return ""

    with open(path, "r", encoding="utf-8") as file:
        return file.read()


def load_all_knowledge():
    files = [
        "about.md",
        "services.md",
        "events.md",
        "faq.md",
        "rules.md",
        "sales_scripts.md",
        "objections.md",
        "client_replies.md",
        "sales_real_data.md",
        "event_checklists.md",
        "manager_tasks.md",
        "event_roles.md",
        "internal_rules.md",
        "client_types.md",
        "venue_features.md",
        "task_templates.md",
        "followups.md",
        "brief_template.md",
        "lead_qualification.md",
        "checklist_templates.md",
    ]

    content = []

    for filename in files:
        text = load_knowledge_file(filename)

        if text:
            content.append(f"\n\n# FILE: {filename}\n\n{text}")

    return "\n\n".join(content)


def get_loaded_knowledge_files():
    files = os.listdir(KNOWLEDGE_DIR)

    return [
        file for file in files
        if file.endswith(".md")
    ]
