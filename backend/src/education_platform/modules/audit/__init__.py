"""Audit trail: every access to student data is recorded, including refused ones."""

from education_platform.modules.audit.service import AuditAction, record_event

__all__ = ["AuditAction", "record_event"]
