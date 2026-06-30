import os
import time
from openai import OpenAI

NIM_MODEL = "meta/llama-3.3-70b-instruct"
NIM_BASE_URL = "https://integrate.api.nvidia.com/v1"
NIM_EMBEDDING_MODEL = "nvidia/nv-embedqa-e5-v5"

_client = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(
            base_url=os.environ.get("NIM_BASE_URL", NIM_BASE_URL),
            api_key=os.environ["NIM_API_KEY"],
        )
    return _client


def generate_variant(segment_text: str, system_prompt: str) -> str:
    client = _get_client()
    model = os.environ.get("NIM_MODEL", NIM_MODEL)
    last_error = None
    for attempt in range(3):
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": segment_text},
                ],
                temperature=0.8,
                max_tokens=1024,
            )
            return response.choices[0].message.content
        except Exception as e:
            last_error = e
            wait = 2 ** attempt
            print(f"NIM API error (attempt {attempt + 1}/3): {e}, retrying in {wait}s")
            time.sleep(wait)
    raise RuntimeError(f"NIM variant generation failed after 3 retries: {last_error}")


def generate_embedding(text: str) -> list[float]:
    client = _get_client()
    embedding_model = os.environ.get("NIM_EMBEDDING_MODEL", NIM_EMBEDDING_MODEL)
    last_error = None
    for attempt in range(3):
        try:
            result = client.embeddings.create(
                model=embedding_model,
                input=text,
                encoding_format="float",
            )
            return result.data[0].embedding
        except Exception as e:
            last_error = e
            wait = 2 ** attempt
            print(f"NIM embedding API error (attempt {attempt + 1}/3): {e}, retrying in {wait}s")
            time.sleep(wait)
    raise RuntimeError(f"NIM embedding failed after 3 retries: {last_error}")
