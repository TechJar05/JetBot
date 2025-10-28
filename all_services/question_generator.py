import json
from typing import List, Any
from django.conf import settings
from openai import OpenAI

# -------------------------
# OpenAI client wrapper
# -------------------------
from openai import OpenAI
from django.conf import settings
from typing import Any

def get_openai_client() -> OpenAI:
    api_key = getattr(settings, "OPENAI_API_KEY", None)
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not configured in Django settings.")
    return OpenAI(api_key=api_key)


def generate_chat_completion(
    prompt: str,
    model: str = "gpt-4o-mini",
    max_tokens: int = 800,
    temperature: float = 0.5,
    response_format: dict | None = None,
    **kwargs: Any
) -> str:
    """
    Call OpenAI Chat Completions and return the assistant text.
    """
    client = get_openai_client()

    try:
        params = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
            "temperature": temperature,
        }

        # ✅ Add response_format correctly
        if response_format:
            params["response_format"] = response_format

        # ✅ Merge any other extra args safely
        params.update(kwargs)

        resp = client.chat.completions.create(**params)

        return resp.choices[0].message.content.strip()

    except Exception as exc:
        raise RuntimeError(f"OpenAI API error: {str(exc)}") from exc





def generate_interview_questions(jd_text: str, difficulty: str) -> List[str]:
    """
    Generate 5 structured interview questions from a JD and difficulty level:
    - 1 introductory question
    - 3 technical questions (based on JD + difficulty)
    - 1 behavioral/closing question

    Returns a Python list of questions.
    """
    prompt = f"""
    You are an AI interview assistant. Based on the following job description, 
    generate 5 interview questions for a {difficulty} level candidate.

    Job Description:
    {jd_text}

    The questions should follow this exact structure:
    1. One introductory question (to start the conversation).
    2. Three technical questions directly based on the job description and difficulty level.
    3. One behavioral or closing question.

    Return ONLY a JSON list of 5 strings in this order, e.g.:
    [
      "Introductory Question",
      "Technical Question 1",
      "Technical Question 2",
      "Technical Question 3",
      "Behavioral Question"
    ]
    """

    raw_output = generate_chat_completion(prompt, model="gpt-3.5-turbo", max_tokens=600)

    # Try parsing JSON first
    try:
        questions = json.loads(raw_output)
        if isinstance(questions, list) and len(questions) == 5:
            return [str(q).strip() for q in questions]
    except json.JSONDecodeError:
        pass

    # Fallback: extract lines
    return [line.strip(" -0123456789.") for line in raw_output.splitlines() if line.strip()]
