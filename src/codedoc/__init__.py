"""codedoc - an AI Business Analyst that turns any code repository into an SRS."""

__version__ = "0.1.0"

from codedoc.api import GenerationResult, generate_srs  # noqa: E402
from codedoc.config import Settings  # noqa: E402

__all__ = ["generate_srs", "GenerationResult", "Settings", "__version__"]
