# employees/models.py

from django.db import models
from django.conf import settings  # Best practice to refer to the User model


class Territory(models.Model):
    """Represents a geographical or logical territory."""
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)

    def __str__(self):
        return self.name


class EmployeeProfile(models.Model):
    """Extends the built-in User model to include employee-specific data."""

    class Role(models.TextChoices):
        DIRECTOR = 'DIRECTOR', 'Director'
        MANAGER = 'MANAGER', 'Manager'
        TECHNICIAN = 'TECHNICIAN', 'Technician'
        DISPATCHER = 'DISPATCHER', 'Dispatcher'

    # --- Core Information ---
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='profile'
    )
    role = models.CharField(max_length=20, choices=Role.choices)

    # --- Employee Code (Unique Identifier) ---
    code = models.CharField(max_length=20, unique=True, null=True, blank=True, db_index=True) # Added index

    # --- Hierarchy (Adjacency List) ---
    reports_to = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='subordinates'
    )

    # --- Matrix Relationship (Territories) ---
    territories = models.ManyToManyField(Territory, blank=True, related_name='employees')

    def __str__(self):
        full_name = self.user.get_full_name()
        return f"{full_name or self.user.username} ({self.get_role_display()})"
