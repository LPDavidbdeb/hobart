# employees/models.py

from django.db import models
from django.conf import settings
from django.urls import reverse
from address.models import Address, AddressStatus, FSA, PostalCode
from organization.models import Territory


class EmployeeProfile(models.Model):
    """Extends the built-in User model to include employee-specific data."""

    class Role(models.TextChoices):
        DIRECTOR = 'DIRECTOR', 'Director'
        MANAGER = 'MANAGER', 'Manager'
        TECHNICIAN = 'TECHNICIAN', 'Technician'
        DISPATCHER = 'DISPATCHER', 'Dispatcher'

    # Add the objects manager explicitly for type hinting/linter
    objects = models.Manager()

    # --- Core Information ---
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='profile'
    )
    role = models.CharField(max_length=20, choices=Role.choices)

    # --- Employee Code (Unique Identifier) ---
    code = models.CharField(max_length=20, unique=True, null=True, blank=True, db_index=True)

    # --- Hierarchy (Adjacency List) ---
    reports_to = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='subordinates'
    )

    # --- Geographic Responsibilities & Location ---
    territories = models.ManyToManyField(
        Territory,
        blank=True,
        related_name='employees',
        help_text="Legacy field for manager-level territory assignments."
    )
    responsible_fsas = models.ManyToManyField(
        FSA,
        blank=True,
        related_name='technicians',
        help_text="FSAs a Technician is directly responsible for."
    )
    postal_code = models.ForeignKey(
        PostalCode,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="The employee's home postal code. Used as a starting point for location and distance calculations."
    )

    # --- Address ---
    address = models.ForeignKey(Address, on_delete=models.SET_NULL, null=True, blank=True, related_name='employee_profiles')
    address_status = models.ForeignKey(
        AddressStatus,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='employee_profiles'
    )

    def __str__(self):
        full_name = self.user.get_full_name()
        return f"{full_name or self.user.username} ({self.get_role_display()})"

    def get_absolute_url(self):
        return reverse('employees:employee_detail', kwargs={'pk': self.pk})

class TechnicianFSAStaging(models.Model):
    """A temporary holding area for technician-FSA assignments from a CSV upload."""
    class Status(models.TextChoices):
        PENDING = 'PENDING', 'Pending'
        PROCESSED = 'PROCESSED', 'Processed'
        ERROR = 'ERROR', 'Error'
        IGNORED = 'IGNORED', 'Ignored'

    fsa_code = models.CharField(max_length=3, help_text="FSA code from the CSV.")
    technician_code = models.CharField(max_length=20, help_text="Technician code from the CSV.")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING, db_index=True)
    error_message = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Technician FSA Staging Record"
        verbose_name_plural = "Technician FSA Staging Records"
        ordering = ['created_at']

    def __str__(self):
        return f"{self.technician_code} - {self.fsa_code} ({self.status})"
