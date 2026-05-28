"""SQLAlchemy ORM models.

All models must be imported here so Alembic's `target_metadata = Base.metadata`
sees every table.
"""

from app.models.ai import (
    AIComplexity,
    AIConversation,
    AIDataAccessMode,
    AIMessage,
    AIMessageRole,
    AIProvider,
    AISettings,
    AITone,
)
from app.models.analysis import AbnormalType, AnalysisRecord, AnalysisValue
from app.models.base import Base
from app.models.account_wipe import AccountWipeCode
from app.models.email_verification import EmailVerification
from app.models.invite import InviteCode
from app.models.support import (
    SupportTicket,
    TicketAttachment,
    TicketComment,
    TicketStatus,
    TicketType,
)
from app.models.system_setting import SystemSetting
from app.models.patient_profile import (
    Allergy,
    AllergySeverity,
    ChronicCondition,
    FamilyHistory,
    PatientProfile,
    WeightHistory,
)
from app.models.telegram import TelegramBinding, TelegramBindingCode
from app.models.user import User, UserRole, UserStatus
from app.models.user_session import UserSession

__all__ = [
    "AbnormalType",
    "AccountWipeCode",
    "AIComplexity",
    "AIConversation",
    "AIDataAccessMode",
    "AIMessage",
    "AIMessageRole",
    "AIProvider",
    "AISettings",
    "AITone",
    "Allergy",
    "AllergySeverity",
    "AnalysisRecord",
    "AnalysisValue",
    "Base",
    "ChronicCondition",
    "EmailVerification",
    "FamilyHistory",
    "InviteCode",
    "PatientProfile",
    "SupportTicket",
    "SystemSetting",
    "TelegramBinding",
    "TelegramBindingCode",
    "TicketAttachment",
    "TicketComment",
    "TicketStatus",
    "TicketType",
    "User",
    "UserRole",
    "UserSession",
    "UserStatus",
    "WeightHistory",
]
