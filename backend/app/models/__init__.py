# FIX: Removed circular import - models/__init__.py should NOT import from
# app.models.exam inside app.models.exam itself.
# The correct pattern is to import Base first, then all models in dependency order.

from app.core.database import Base  # noqa: F401

# Import models in correct dependency order (no circular refs)
from app.models.user import User  # noqa: F401
from app.models.exam import Exam  # noqa: F401
from app.models.question import Question, Option  # noqa: F401
from app.models.attempt import ExamAttempt, Response  # noqa: F401
from app.models.cheat_log import CheatLog  # noqa: F401
from app.models.proctoring_settings import ProctoringSettings  # noqa: F401

__all__ = [
    "Base",
    "User",
    "Exam",
    "Question",
    "Option",
    "ExamAttempt",
    "Response",
    "CheatLog",
    "ProctoringSettings",
]