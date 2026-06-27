import os

import google.generativeai as genai

GEMINI_MODEL = "gemini-1.5-pro"


def generate_variant(segment_text: str, system_prompt: str) -> str:
    genai.configure(api_key=os.environ["GEMINI_API_KEY"])
    model = genai.GenerativeModel(
        model_name=GEMINI_MODEL,
        system_instruction=system_prompt,
    )
    response = model.generate_content(segment_text)
    return response.text


def generate_embedding(text: str) -> list[float]:
    genai.configure(api_key=os.environ["GEMINI_API_KEY"])
    result = genai.embed_content(
        model="models/text-embedding-004",
        content=text,
    )
    return result["embedding"]
