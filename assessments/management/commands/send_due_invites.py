"""Send the scheduled assessment emails that are due. Run by a Render Cron Job."""
from django.core.management.base import BaseCommand

from assessments.scheduled_sending import send_due_runs


class Command(BaseCommand):
    help = "Send scheduled assessment invitation emails whose time has come."

    def handle(self, *args, **options):
        summary = send_due_runs()
        self.stdout.write(f"sent {len(summary.sent)}, failed {len(summary.failed)}")
