from groq import Groq
from config import GROQ_API_KEY

client = Groq(api_key=GROQ_API_KEY)


def generate_ai_response(text):
    chat_completion = client.chat.completions.create(
        messages=[
            {
                "role": "system",
                "content": "Ты AI Assistant компании Quattro Space."
            },
            {
                "role": "user",
                "content": text
            }
        ],
        model="llama-3.1-8b-instant"
    )

    return chat_completion.choices[0].message.content
