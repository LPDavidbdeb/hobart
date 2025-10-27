# employees/admin.py

from django.contrib import admin
from .models import EmployeeProfile


@admin.register(EmployeeProfile)
class EmployeeProfileAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'role', 'reports_to')
    list_filter = ('role', 'territories')
    search_fields = ('user__username', 'user__first_name', 'user__last_name')
    raw_id_fields = ('user', 'reports_to')  # Makes selecting users/managers easier
