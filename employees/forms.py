# employees/forms.py

from django import forms
from django.contrib.auth.models import User
from .models import EmployeeProfile
from .utils import create_employee

class EditEmployeeForm(forms.ModelForm):
    first_name = forms.CharField(max_length=100, required=True)
    last_name = forms.CharField(max_length=100, required=True)
    code = forms.CharField(max_length=20, required=False, help_text="Employee code for legacy system integration.")

    class Meta:
        model = EmployeeProfile
        fields = ['code']

    def __init__(self, *args, **kwargs):
        # The user instance is passed in from the view
        self.user = kwargs.pop('user_instance', None)
        super().__init__(*args, **kwargs)
        
        if self.user:
            self.fields['first_name'].initial = self.user.first_name
            self.fields['last_name'].initial = self.user.last_name
        
        if self.instance and self.instance.pk:
            self.fields['code'].initial = self.instance.code

    def save(self, commit=True):
        # Save the EmployeeProfile instance
        profile = super().save(commit=False)
        
        # Save the related User instance
        if self.user:
            self.user.first_name = self.cleaned_data['first_name']
            self.user.last_name = self.cleaned_data['last_name']
            if commit:
                self.user.save()

        if commit:
            profile.save()
            
        return profile

class TerritoryAssignmentForm(forms.Form):
    csv_file = forms.FileField(label='Upload Territory Assignment CSV')

class BaseEmployeeCreationForm(forms.Form):
    first_name = forms.CharField(max_length=100)
    last_name = forms.CharField(max_length=100)
    reports_to = forms.ModelChoiceField(queryset=EmployeeProfile.objects.none(), required=False)

    def __init__(self, *args, **kwargs):
        superiors_queryset = kwargs.pop('superiors_queryset', EmployeeProfile.objects.none())
        super().__init__(*args, **kwargs)
        self.fields['reports_to'].queryset = superiors_queryset

    def save(self, role):
        user_data = {
            'first_name': self.cleaned_data['first_name'],
            'last_name': self.cleaned_data['last_name'],
        }
        profile = create_employee(role=role, **user_data)
        profile.reports_to = self.cleaned_data.get('reports_to')
        profile.save()
        return profile

class DirectorCreationForm(BaseEmployeeCreationForm):
    def save(self, role=EmployeeProfile.Role.DIRECTOR):
        return super().save(role)

class ManagerCreationForm(BaseEmployeeCreationForm):
    def save(self, role=EmployeeProfile.Role.MANAGER):
        return super().save(role)

class TechnicianCreationForm(BaseEmployeeCreationForm):
    def save(self, role=EmployeeProfile.Role.TECHNICIAN):
        return super().save(role)
