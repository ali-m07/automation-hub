"""Service factory functions for Automation Hub."""

from automation_hub.services.psd_processor import PSDProcessor
from automation_hub.services.email_service import EmailService
from automation_hub.services.job_processor import JobProcessor

# Singleton instances (initialized on first access)
_psd_processor: PSDProcessor | None = None
_email_service: EmailService | None = None
_job_processor: JobProcessor | None = None


def get_psd_processor() -> PSDProcessor:
    """Get or create PSD processor instance."""
    global _psd_processor
    if _psd_processor is None:
        _psd_processor = PSDProcessor()
    return _psd_processor


def get_email_service() -> EmailService:
    """Get or create email service instance."""
    global _email_service
    if _email_service is None:
        _email_service = EmailService()
    return _email_service


def get_job_processor() -> JobProcessor:
    """Get or create job processor instance."""
    global _job_processor
    if _job_processor is None:
        _job_processor = JobProcessor(get_psd_processor())
    return _job_processor


__all__ = [
    "PSDProcessor",
    "EmailService",
    "JobProcessor",
    "get_psd_processor",
    "get_email_service",
    "get_job_processor",
]
