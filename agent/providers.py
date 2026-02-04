"""
Provider configuration for LLM and embedding models.
"""

import os
from typing import Optional
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.models.openai import OpenAIModel
import openai
from openai import AsyncOpenAI
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def get_embedding_client() -> openai.AsyncOpenAI:
    """
    Get embedding client configuration based on environment variables.
    """

    base_url = os.getenv("EMBEDDING_BASE_URL", "https://api.openai.com/v1")
    api_key = os.getenv("EMBEDDING_API_KEY", "")

    return AsyncOpenAI(
        base_url = base_url,
        api_key = api_key
    )

def get_embedding_model() -> str:
    """
    Get embedding model name from environment
    """
    return os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")