from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from analytics.models import AuditLog


class Command(BaseCommand):
    help = 'Delete audit logs older than retention period (default: 365 days).'

    def add_arguments(self, parser):
        parser.add_argument(
            '--days',
            type=int,
            default=365,
            help='Retention in days. Logs older than this are deleted.',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show how many logs would be deleted without deleting.',
        )

    def handle(self, *args, **options):
        days = options['days']
        dry_run = options['dry_run']

        if days <= 0:
            self.stdout.write(self.style.ERROR('--days must be a positive integer.'))
            return

        cutoff = timezone.now() - timedelta(days=days)
        queryset = AuditLog.objects.filter(timestamp__lt=cutoff)
        count = queryset.count()

        if dry_run:
            self.stdout.write(self.style.WARNING(
                f'[DRY RUN] {count} audit log(s) older than {days} days would be deleted.'
            ))
            return

        deleted, _ = queryset.delete()
        self.stdout.write(self.style.SUCCESS(
            f'Deleted {deleted} audit log(s) older than {days} days.'
        ))
