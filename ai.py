from config import TEXT_MODEL, MAX_HISTORY_MESSAGES
from prompts import BASE_SYSTEM_PROMPT, MODES
from memory import load_knowledge

user_histories = {}
user_modes = {}


def get_user_history(user_id):
    if user_id not in user_histories:
        user_histories[user_id] = []
    return user_histories[user_id]


def clear_user_history(user_id):
    user_histories[user_id] = []


def get_user_mode(user_id):
    return user_modes.get(user_id, "default")


def set_user_mode(user_id, mode):
    user_modes[user_id] = mode


def build_system_prompt(user_id):
    knowledge = load_knowledge()
    mode = get_user_mode(user_id)
    mode_prompt = MODES.get(mode, MODES["default"])

    return f"""
{BASE_SYSTEM_PROMPT}

{mode_prompt}

База знаний Quattro Space:
{knowledge}
"""


def ask_ai(client, user_id, user_text):
    history = get_user_history(user_id)

    messages = [
        {
            "role": "system",
            "content": build_system_prompt(user_id)
        }
    ]

    messages.extend(history)

    messages.append({
        "role": "user",
        "content": user_text
    })

    response = client.chat.completions.create(
        model=TEXT_MODEL,
        messages=messages,
        temperature=0.4
    )

    answer = response.choices[0].message.content

    history.append({
        "role": "user",
        "content": user_text
    })

    history.append({
        "role": "assistant",
        "content": answer
    })

    user_histories[user_id] = history[-MAX_HISTORY_MESSAGES:]

    return answer


def split_long_message(text, limit=3900):
    if len(text) <= limit:
        return [text]

    parts = []

    while len(text) > limit:
        cut = text.rfind("\n", 0, limit)

        if cut == -1:
            cut = limit

        parts.append(text[:cut])
        text = text[cut:].strip()

    if text:
        parts.append(text)

    return parts
