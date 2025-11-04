# employees/forms.py

from django import forms
from django.contrib.auth.models import User
from .models import EmployeeProfile
from .utils import create_employee

class TerritoryAssignmentForm(forms.Form):
    csv_file = forms.FileField(
        label='Select a CSV file',
        help_text='The file must have two columns: Territory Code and Manager\'s Employee Code.'
    )

class BaseEmployeeCreationForm(forms.ModelForm):
    first_name = forms.CharField(max_length=150, required=True)
    last_name = forms.CharField(max_length=150, required=True)
    reports_to = forms.ModelChoiceField(
        queryset=EmployeeProfile.objects.none(), # We will set this in the view
        required=False,
        label="Reports To",
        help_text="Select the direct superior for this employee."
    )

    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'reports_to']

    def __init__(self, *args, **kwargs):
        # Pop the custom queryset argument before the superclass gets it
        superiors_queryset = kwargs.pop('superiors_queryset', None)
        super().__init__(*args, **kwargs)
        if superiors_queryset is not None:
            self.fields['reports_to'].queryset = superiors_queryset

    def save(self, commit=True):
        if not commit:
            raise NotImplementedError("commit=False is not supported for this form.")

        employee_profile = create_employee(
            role=self.role,
            first_name=self.cleaned_data['first_name'],
            last_name=self.cleaned_data['last_name']
        )
        
        # Assign the superior after the profile is created
        reports_to_profile = self.cleaned_data.get('reports_to')
        if reports_to_profile:
            employee_profile.reports_to = reports_to_profile
            employee_profile.save()

        return employee_profile.user

class DirectorCreationForm(BaseEmployeeCreationForm):
    role = EmployeeProfile.Role.DIRECTOR

class ManagerCreationForm(BaseEmployeeCreationForm):
    role = EmployeeProfile.Role.MANAGER

class TechnicianCreationForm(BaseEmployeeCreationForm):
    role = EmployeeProfile.Role.TECHNICIAN
