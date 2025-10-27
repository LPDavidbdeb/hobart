from client.models import Client
from employees.models import EmployeeProfile
from .models import Address, AddressStatus

def run_address_validation_batch():
    """
    Runs a batch update on all Clients and Employees to set their address_status.
    Returns a dictionary with the final counts.
    """
    try:
        complete_status = AddressStatus.objects.get(name='COMPLETE')
        incomplete_status = AddressStatus.objects.get(name='INCOMPLETE')
        missing_status = AddressStatus.objects.get(name='MISSING')
    except AddressStatus.DoesNotExist:
        # This is a critical failure, so we raise an exception
        raise Exception("Required AddressStatus objects (COMPLETE, INCOMPLETE, MISSING) do not exist in the database.")

    # --- Process Clients ---
    clients_missing_count = Client.objects.filter(address__isnull=True).update(address_status=missing_status)
    
    clients_with_address = Client.objects.filter(address__isnull=False).select_related('address')
    clients_complete_count = 0
    clients_incomplete_count = 0
    for client in clients_with_address:
        if client.address.is_degenerate():
            client.address_status = incomplete_status
            clients_incomplete_count += 1
        else:
            client.address_status = complete_status
            clients_complete_count += 1
        client.save(update_fields=['address_status'])

    # --- Process Employees ---
    employees_missing_count = EmployeeProfile.objects.filter(address__isnull=True).update(address_status=missing_status)

    employees_with_address = EmployeeProfile.objects.filter(address__isnull=False).select_related('address')
    employees_complete_count = 0
    employees_incomplete_count = 0
    for employee in employees_with_address:
        if employee.address.is_degenerate():
            employee.address_status = incomplete_status
            employees_incomplete_count += 1
        else:
            employee.address_status = complete_status
            employees_complete_count += 1
        employee.save(update_fields=['address_status'])

    # Return a dictionary with the results
    return {
        "clients_complete": clients_complete_count,
        "clients_incomplete": clients_incomplete_count,
        "clients_missing": clients_missing_count,
        "employees_complete": employees_complete_count,
        "employees_incomplete": employees_incomplete_count,
        "employees_missing": employees_missing_count,
    }
