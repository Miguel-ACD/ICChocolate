import time
from django.core.management.base import BaseCommand
from inventory.alerts import expire_stale_episodes
from inventory.alert_mail import mark_expired_leases, process_one_email


class Command(BaseCommand):
    help = "Process stale sensor episodes and persistent SMTP notifications."

    def handle(self, *args, **options):
        self.stdout.write("Trabajador de alertas iniciado.")
        while True:
            expire_stale_episodes()
            mark_expired_leases()
            while process_one_email():
                pass
            time.sleep(5)
