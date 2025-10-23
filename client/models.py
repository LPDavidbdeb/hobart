from django.db import models

# --- Dimension Models ---

class CodeDimension(models.Model):
    """An abstract base class for simple code/description dimension models."""
    code = models.CharField(max_length=50, unique=True, db_index=True, help_text="The unique code for this item.")
    description = models.CharField(max_length=255, blank=True, help_text="The description for this code.")

    class Meta:
        abstract = True
        ordering = ['description', 'code']

    def __str__(self):
        return f"{self.description} ({self.code})" if self.description else self.code

class IndustryCode(CodeDimension):
    pass

class CustomerTypeCode(CodeDimension):
    pass

class IndustrySubCode(CodeDimension):
    pass

class Territory(CodeDimension):
    """Represents a sales or service territory."""
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


class Client(models.Model):
    """Represents an individual client site or store."""
    account_number = models.CharField(max_length=50, unique=True, db_index=True, help_text="The unique account number for the client site.")
    name = models.CharField(max_length=255, help_text="The specific name of the client site.") # New field
    address1 = models.CharField(max_length=255, blank=True)
    address2 = models.CharField(max_length=255, blank=True)
    postal_code = models.CharField(max_length=20, blank=True)

    # --- Relationships ---
    client_group = models.ForeignKey(ClientGroup, on_delete=models.PROTECT, related_name='clients', help_text="The parent company for this client.")
    territory = models.ForeignKey(Territory, on_delete=models.SET_NULL, null=True, blank=True, related_name='clients')
    industry_code = models.ForeignKey(IndustryCode, on_delete=models.SET_NULL, null=True, blank=True, related_name='clients')
    customer_type_code = models.ForeignKey(CustomerTypeCode, on_delete=models.SET_NULL, null=True, blank=True, related_name='clients')
    industry_sub_code = models.ForeignKey(IndustrySubCode, on_delete=models.SET_NULL, null=True, blank=True, related_name='clients')

    class Meta:
        ordering = ['name', 'account_number']
        indexes = [
            models.Index(fields=['address1']), # Index for address search
        ]

    def __str__(self):
        return self.name
