import time
from django.core.management.base import BaseCommand
from inventory.alerts import expire_stale_episodes
from inventory.alert_mail import mark_expired_leases, process_one_email
from inventory.retention import prune_sensor_readings


class Command(BaseCommand):
    help = "Process stale sensor episodes and persistent SMTP notifications."

    def handle(self, *args, **options):
        self.stdout.write("Trabajador de alertas iniciado.")
        next_cleanup = 0
        while True:
            if time.monotonic() >= next_cleanup:
                removed = prune_sensor_readings()
                self.stdout.write(f"Lecturas antiguas eliminadas: {removed}.")
                next_cleanup = time.monotonic() + 24 * 60 * 60
            expire_stale_episodes()
            mark_expired_leases()
            while process_one_email():
                pass
            time.sleep(5)
