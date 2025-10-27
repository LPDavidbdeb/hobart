from django.db import models
from address.models import Address, AddressStatus # Import AddressStatus
from organization.models import Territory, CodeDimension

# --- Dimension Models ---

class IndustryCode(CodeDimension):
    pass

class CustomerTypeCode(CodeDimension):
    pass

class IndustrySubCode(CodeDimension):
    pass

# --- Main Client Models ---

class ClientGroup(models.Model):
    """Represents a parent company or client group (e.g., DOUGLAS HOME)."""
    code = models.CharField(max_length=10, unique=True, db_index=True, help_text="The unique code for the client group (e.g., AC, AP).")
    name = models.CharField(max_length=255, db_index=True, help_text="The full name of the client group.")

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name

class ClientManager(models.Manager):
    def for_manager(self, manager_profile):
        """Returns a queryset of clients that fall within a manager's assigned territories."""
        # Get all FSAs from all territories assigned to the manager
        manager_fsas = manager_profile.territories.values_list('fsas__code', flat=True).distinct()
        
        # Use the standardized address field and its postal_code to filter clients.
        # This is the final, robust implementation.
        return self.get_queryset().filter(
            address__postal_code__startswith__in=list(manager_fsas)
        )

class Client(models.Model):
    """Represents an individual client site or store."""
    account_number = models.CharField(max_length=50, unique=True, db_index=True, help_text="The unique account number for the client site.")
    name = models.CharField(max_length=255, help_text="The specific name of the client site.")

    # --- Legacy Address Fields (for temporary import) ---
    address1 = models.CharField(max_length=255, blank=True)
    address2 = models.CharField(max_length=255, blank=True)
    postal_code = models.CharField(max_length=20, blank=True)
    
    # --- Standardized Address (the goal) ---
    address = models.ForeignKey(Address, on_delete=models.SET_NULL, null=True, blank=True, related_name='clients')
    address_status = models.ForeignKey(
        AddressStatus,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='clients'
    )

    # --- Relationships ---
    client_group = models.ForeignKey(ClientGroup, on_delete=models.PROTECT, related_name='clients', help_text="The parent company for this client.")
    territory = models.ForeignKey(Territory, on_delete=models.SET_NULL, null=True, blank=True, related_name='clients')
    industry_code = models.ForeignKey(IndustryCode, on_delete=models.SET_NULL, null=True, blank=True, related_name='clients')
    customer_type_code = models.ForeignKey(CustomerTypeCode, on_delete=models.SET_NULL, null=True, blank=True, related_name='clients')
    industry_sub_code = models.ForeignKey(IndustrySubCode, on_delete=models.SET_NULL, null=True, blank=True, related_name='clients')

    # --- Managers ---
    objects = ClientManager() # Use the custom manager

    class Meta:
        ordering = ['name', 'account_number']

    def __str__(self):
        return self.name
