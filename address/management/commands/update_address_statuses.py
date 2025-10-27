from django.core.management.base import BaseCommand
from django.db.models import F
from client.models import Client
from employees.models import EmployeeProfile
from address.models import Address, AddressStatus

class Command(BaseCommand):
    help = 'One-time command to populate the address_status field for all existing Clients and Employees.'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS("--- Starting Batch Address Status Update ---"))

        try:
            complete_status = AddressStatus.objects.get(name='COMPLETE')
            incomplete_status = AddressStatus.objects.get(name='INCOMPLETE')
            missing_status = AddressStatus.objects.get(name='MISSING')
        except AddressStatus.DoesNotExist as e:
            self.stdout.write(self.style.ERROR(f"Critical Error: Could not find required AddressStatus objects. Please ensure they are created. Details: {e}"))
            return

        # --- Update Clients ---
        self.stdout.write("Processing Clients...")
        clients_missing_address = Client.objects.filter(address__isnull=True)
        clients_missing_address.update(address_status=missing_status)
        self.stdout.write(f"  - {clients_missing_address.count()} clients set to MISSING.")

        clients_with_address = Client.objects.filter(address__isnull=False).select_related('address')
        complete_clients = 0
        incomplete_clients = 0
        for client in clients_with_address:
            if client.address.is_degenerate():
                client.address_status = incomplete_status
                incomplete_clients += 1
            else:
                client.address_status = complete_status
                complete_clients += 1
            client.save(update_fields=['address_status'])
        
        self.stdout.write(f"  - {complete_clients} clients set to COMPLETE.")
        self.stdout.write(f"  - {incomplete_clients} clients set to INCOMPLETE.")

        # --- Update Employees ---
        self.stdout.write("\nProcessing Employees...")
        employees_missing_address = EmployeeProfile.objects.filter(address__isnull=True)
        employees_missing_address.update(address_status=missing_status)
        self.stdout.write(f"  - {employees_missing_address.count()} employees set to MISSING.")

        employees_with_address = EmployeeProfile.objects.filter(address__isnull=False).select_related('address')
        complete_employees = 0
        incomplete_employees = 0
        for employee in employees_with_address:
            if employee.address.is_degenerate():
                employee.address_status = incomplete_status
                incomplete_employees += 1
            else:
                employee.address_status = complete_status
                complete_employees += 1
            employee.save(update_fields=['address_status'])

        self.stdout.write(f"  - {complete_employees} employees set to COMPLETE.")
        self.stdout.write(f"  - {incomplete_employees} employees set to INCOMPLETE.")

        self.stdout.write(self.style.SUCCESS("\n--- Batch Update Complete ---"))
