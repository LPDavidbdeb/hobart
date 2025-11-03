# In organization/management/commands/fix_statistical_tree.py

from django.core.management.base import BaseCommand
from django.db import connection, transaction
from organization.models import NestedTerritory
import time


class Command(BaseCommand):
    help = "Fixes the 'statistical' tree by reparenting CSDs to their correct CD using their ID codes."

    @transaction.atomic
    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE("-> Step 1: Updating CSD parent_id's using code-based join..."))
        start_time = time.time()

        # This query is based on the PDF (Table 4.2 and 4.4).
        sql = """
              UPDATE organization_nestedterritory AS csd
              SET parent_id = cd.id FROM organization_nestedterritory AS cd
              WHERE
                  csd.tree_name = 'statistical' \
                AND
                  cd.tree_name = 'statistical' \
                AND \
                  csd.type = 'CITY' \
                AND -- This is our CSD (type=CITY)
                  cd.type = 'REGION' \
                AND -- This is our CD (type=REGION)

              -- This is the logic from the PDF:
              -- Join where the CD's code (e.g., '2465')
              -- matches the first 4 characters of the CSD's code (e.g., '2465005')
                  cd.code = LEFT (csd.code \
                  , 4); \
              """

        with connection.cursor() as cursor:
            cursor.execute(sql)
            updated_count = cursor.rowcount

        end_time = time.time()
        self.stdout.write(self.style.SUCCESS(
            f"-> Step 1 Complete: {updated_count} CSDs were reparented in {end_time - start_time:.2f} seconds."
        ))

        # The rebuild is handled by the main build_tree command