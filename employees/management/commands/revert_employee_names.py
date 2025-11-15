import os
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.contrib.auth.models import User
from employees.models import EmployeeProfile

class Command(BaseCommand):
    help = 'Reverts specific employee User names based on a hardcoded list of previous incorrect updates.'

    def handle(self, *args, **options):
        # List of (EmployeeProfile_PK, original_first_name, original_last_name)
        # This list is derived directly from the output you provided.
        revert_data = [
            (38, "Robert Donald", "Bishop"), # RB1, Patrick Bunguay -> Robert Donald Bishop
            (40, "Patrick", "Bungay"),     # PB4, Patrick Gogan -> Patrick Bungay
            (42, "PATRICK", "GOGAN"),      # PG2, Wayne Martin -> PATRICK GOGAN
            (44, "Wayne", "Martin"),       # WM1, Cole Morgan -> Wayne Martin
            (45, "Nicholas", "Michaud"),   # NM1, Paul Newton -> Nicholas Michaud
            (46, "COLE", "MORGAN"),        # CM2, Ian Tarrant -> COLE MORGAN
            (47, "PAUL", "NEWTON"),        # PN1, Jamie Tattrie -> PAUL NEWTON
            (48, "Ian", "Tarrant"),        # IT1, Chris Thibodeau -> Ian Tarrant
            (49, "JAMIE", "TATTRIE"),      # JT2, Geroge Yuriy Volyev -> JAMIE TATTRIE
            (50, "Chris", "Thibodeau"),    # CT2, Jason Weshaver -> Chris Thibodeau
            (51, "YURIY GEORGE", "VOLYEV"),# GV1, Peter Wheeler -> YURIY GEORGE VOLYEV
        ]

        self.stdout.write(self.style.HTTP_INFO("Starting database name reversion..."))

        with transaction.atomic():
            for ep_pk, original_first, original_last in revert_data:
                try:
                    employee_profile = EmployeeProfile.objects.get(pk=ep_pk)
                    user = employee_profile.user
                    
                    self.stdout.write(f"Reverting User (PK: {user.pk}, current name: {user.first_name} {user.last_name}) "
                                      f"associated with EmployeeProfile (PK: {ep_pk}) to '{original_first} {original_last}'...")
                    
                    user.first_name = original_first
                    user.last_name = original_last
                    user.save(update_fields=['first_name', 'last_name'])
                    self.stdout.write(self.style.SUCCESS(f"  Successfully reverted User {user.pk} name to '{user.first_name} {user.last_name}'."))
                except EmployeeProfile.DoesNotExist:
                    self.stdout.write(self.style.ERROR(f"Error: EmployeeProfile with PK {ep_pk} not found. Skipping."))
                except User.DoesNotExist:
                    self.stdout.write(self.style.ERROR(f"Error: User associated with EmployeeProfile PK {ep_pk} not found. Skipping."))
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f"An unexpected error occurred for EmployeeProfile PK {ep_pk}: {e}"))

        self.stdout.write(self.style.HTTP_INFO("\nDatabase name reversion complete."))
