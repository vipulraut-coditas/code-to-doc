"""codedoc - an AI agent that turns any code repository into software documentation
(SRS, user manual, API documentation, technical documentation, design document)."""

__version__ = "0.1.0"

from codedoc.api import GeneratedDocument, GenerationResult, generate_docs  # noqa: E402
from codedoc.config import Settings  # noqa: E402
from codedoc.doctypes import DOC_TYPES  # noqa: E402

__all__ = ["generate_docs", "GenerationResult", "GeneratedDocument", "DOC_TYPES", "Settings", "__version__"]
