from django import forms
from django.contrib.auth.models import User
from .models import EmployeeProfile
from .utils import create_employee, regenerate_employee_credentials

class CsvUploadForm(forms.Form):
    csv_file = forms.FileField(
        label='Select a CSV file',
        help_text='IMPORTANT: The file must NOT have a header row. It must be comma-separated. Column order: Code, Full Name, Title, Supervisor Code. Valid Titles: DIRECTOR, MANAGER, TECHNICIAN, DISPATCHER.'
    )

class BaseEmployeeCreationForm(forms.Form):
    """A base form for creating new employees, to be inherited by role-specific forms."""
    first_name = forms.CharField(max_length=150, required=True)
    last_name = forms.CharField(max_length=150, required=True)

    def get_user_data(self):
        return {
            'first_name': self.cleaned_data['first_name'],
            'last_name': self.cleaned_data['last_name'],
        }

class DirectorCreationForm(BaseEmployeeCreationForm):
    def save(self):
        return create_employee(role=EmployeeProfile.Role.DIRECTOR, **self.get_user_data())

class ManagerCreationForm(BaseEmployeeCreationForm):
    reports_to = forms.ModelChoiceField(
        queryset=EmployeeProfile.objects.filter(role=EmployeeProfile.Role.DIRECTOR),
        required=True
    )

    def save(self):
        profile = create_employee(role=EmployeeProfile.Role.MANAGER, **self.get_user_data())
        profile.reports_to = self.cleaned_data.get('reports_to')
        profile.save()
        return profile

class TechnicianCreationForm(BaseEmployeeCreationForm):
    reports_to = forms.ModelChoiceField(
        queryset=EmployeeProfile.objects.filter(role=EmployeeProfile.Role.MANAGER),
        required=True
    )

    def save(self):
        profile = create_employee(role=EmployeeProfile.Role.TECHNICIAN, **self.get_user_data())
        profile.reports_to = self.cleaned_data.get('reports_to')
        profile.save()
        return profile

class EditEmployeeForm(forms.ModelForm):
    """A form for editing an employee's first and last name and regenerating credentials."""
    first_name = forms.CharField(max_length=150, required=True)
    last_name = forms.CharField(max_length=150, required=True)

    class Meta:
        model = User
        fields = ['first_name', 'last_name']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.fields['first_name'].initial = self.instance.first_name
            self.fields['last_name'].initial = self.instance.last_name

    def save(self, commit=True):
        user = super().save(commit=False)
        if commit:
            user.save()
            if hasattr(user, 'profile'):
                regenerate_employee_credentials(user.profile)
        return user
