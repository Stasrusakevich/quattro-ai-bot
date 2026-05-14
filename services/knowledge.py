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
    ]

    content = []

    for filename in files:
        text = load_knowledge_file(filename)

        if text:
            content.append(text)

    return "\n\n".join(content)
