from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Address, AddressStatus

@receiver(post_save, sender=Address)
def update_related_address_statuses(sender, instance, **kwargs):
    """
    Listens for an Address to be saved and updates the status on all related
    Client and EmployeeProfile objects.
    """
    # Determine the correct status for the saved address
    if instance.is_degenerate():
        status_name = "INCOMPLETE"
    else:
        status_name = "COMPLETE"
    
    try:
        # Get the actual AddressStatus object from the database
        status_obj = AddressStatus.objects.get(name=status_name)
    except AddressStatus.DoesNotExist:
        # This should not happen if the initial data is loaded, but is a safe fallback.
        return

    # Update all related clients
    # The related_name on the Address model's ForeignKey is 'clients'
    instance.clients.all().update(address_status=status_obj)

    # Update all related employee profiles
    # The related_name is 'employee_profiles'
    instance.employee_profiles.all().update(address_status=status_obj)
