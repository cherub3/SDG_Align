"""Reads GEMINI_API_KEY from the environment or ./.env. Never prints it."""
import os
from pathlib import Path


def gemini_key():
    k = os.environ.get("GEMINI_API_KEY")
    if not k:
        from dotenv import dotenv_values
        k = (dotenv_values(Path(__file__).resolve().parent.parent / ".env") or {}).get("GEMINI_API_KEY")
    return k
