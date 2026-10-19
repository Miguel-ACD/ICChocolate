import time
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Reserved worker process for future OCR and monitoring jobs."

    def handle(self, *args, **options):
        self.stdout.write("Worker preparado para futuras tareas; no procesa datos en esta entrega.")
        while True:
            time.sleep(60)
