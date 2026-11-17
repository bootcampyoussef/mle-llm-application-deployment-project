"""Configure a safe, isolated environment for local tests."""

import os

os.environ.update(
    {
        "PYTHON_DOTENV_DISABLED": "1",
        "MODEL_PROVIDER": "dry",
        "GROQ_API_KEY": "",
        "GROQ_MODEL": "openai/gpt-oss-20b",
        "CACHE_TTL_SECONDS": "300",
        "MAX_CONCURRENT_REQUESTS": "4",
        "REQUEST_TIMEOUT_SECONDS": "30",
        "TRACE_SINK": "jsonl",
        "LANGFUSE_TRACING_ENABLED": "false",
        "LANGFUSE_PUBLIC_KEY": "",
        "LANGFUSE_SECRET_KEY": "",
    }
)
