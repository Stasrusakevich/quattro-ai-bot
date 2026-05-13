def load_prompt(filename):
    with open(f"prompts/{filename}", "r", encoding="utf-8") as file:
        return file.read()
