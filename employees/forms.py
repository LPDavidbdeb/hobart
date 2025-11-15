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
        fields = ['code', 'reports_to'] # Include reports_to here

    def __init__(self, *args, **kwargs):
        # The user instance is passed in from the view
        self.user = kwargs.pop('user_instance', None)
        super().__init__(*args, **kwargs)
        
        if self.user:
            self.fields['first_name'].initial = self.user.first_name
            self.fields['last_name'].initial = self.user.last_name
        
        if self.instance and self.instance.pk:
            self.fields['code'].initial = self.instance.code

            # Determine queryset for reports_to based on current employee's role
            if self.instance.role == EmployeeProfile.Role.TECHNICIAN:
                self.fields['reports_to'].queryset = EmployeeProfile.objects.filter(role=EmployeeProfile.Role.MANAGER).select_related('user').order_by('user__first_name', 'user__last_name')
                self.fields['reports_to'].label = "Reports To (Manager)"
                self.fields['reports_to'].required = False # Make it optional
            elif self.instance.role == EmployeeProfile.Role.MANAGER:
                self.fields['reports_to'].queryset = EmployeeProfile.objects.filter(role=EmployeeProfile.Role.DIRECTOR).select_related('user').order_by('user__first_name', 'user__last_name')
                self.fields['reports_to'].label = "Reports To (Director)"
                self.fields['reports_to'].required = False # Make it optional
            else:
                # For roles like DIRECTOR or DISPATCHER, they don't report to anyone in this hierarchy
                # So, remove the reports_to field
                if 'reports_to' in self.fields:
                    del self.fields['reports_to']
        else:
            # If no instance (e.g., form for creation, though this is EditEmployeeForm)
            # or if instance is not yet saved, remove reports_to as it's for existing hierarchy
            if 'reports_to' in self.fields:
                del self.fields['reports_to']


    def save(self, commit=True):
        # Save the EmployeeProfile instance
        # ModelForm handles 'code' and 'reports_to' if they are present in self.fields and cleaned_data
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
