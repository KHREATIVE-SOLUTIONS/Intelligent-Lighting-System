"""
Operator Credential Model
=========================

The single operator password that unlocks the appliance. One venue, one
credential, one row.
"""

from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime

from app.db.database import Base

# The credential table holds exactly one row, written at this id. Fixing the id
# keeps "reset then set a new password" identical on SQLite (which reuses the
# free rowid) and PostgreSQL (whose sequence would otherwise march on).
SINGLETON_ID = 1


class OperatorCredential(Base):
    """The venue's operator password, stored as a scrypt hash."""

    __tablename__ = "operator_credential"

    id = Column(Integer, primary_key=True, index=True)

    # scrypt$n$r$p$salt_b64$hash_b64 - see app.core.security
    password_hash = Column(String(255), nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_login_at = Column(DateTime, nullable=True)

    def __repr__(self):
        return f"<OperatorCredential(id={self.id}, updated_at={self.updated_at})>"
