import re
from unidecode import unidecode
from django.contrib.auth.models import User
from .models import EmployeeProfile

def generate_unique_employee_email(first_name: str, last_name: str, user_to_exclude: User = None) -> str:
    """
    Generates a unique employee email based on the first and last name.
    Handles accented characters correctly. Example: Dave Doré -> dave.dore@hobart.ca
    Can exclude a specific user from the uniqueness check, which is useful for updates.
    """
    if not first_name or not last_name:
        return ""

    clean_first_name = re.sub(r'[^a-zA-Z]', '', unidecode(first_name)).lower()
    clean_last_name = re.sub(r'[^a-zA-Z]', '', unidecode(last_name)).lower()

    base_email = f"{clean_first_name}.{clean_last_name}@hobart.ca"
    email = base_email
    counter = 1
    queryset = User.objects.all()
    if user_to_exclude:
        queryset = queryset.exclude(pk=user_to_exclude.pk)

    while queryset.filter(email=email).exists():
        email = f"{clean_first_name}.{clean_last_name}{counter}@hobart.ca"
        counter += 1
    return email

def generate_unique_username(first_name: str, last_name: str, user_to_exclude: User = None) -> str:
    """
    Generates a unique username based on the first name and last name.
    Can exclude a specific user from the uniqueness check.
    """
    if not first_name or not last_name:
        return None

    base_username = f"{first_name[0].lower()}{last_name.lower().replace(' ', '')[:8]}"
    username = base_username
    counter = 1
    queryset = User.objects.all()
    if user_to_exclude:
        queryset = queryset.exclude(pk=user_to_exclude.pk)

    while queryset.filter(username=username).exists():
        username = f"{base_username}{counter}"
        counter += 1
    return username

def generate_employee_code(first_name: str, last_name: str, profile_to_exclude: EmployeeProfile = None) -> str:
    """
    Generates a unique employee code based on the first letters of the first and last name.
    Can exclude a specific profile from the uniqueness check.
    """
    if not first_name or not last_name:
        return None

    base_code = (first_name[0] + last_name[0]).upper()
    
    queryset = EmployeeProfile.objects.filter(code__startswith=base_code)
    if profile_to_exclude:
        queryset = queryset.exclude(pk=profile_to_exclude.pk)

    existing_codes_count = queryset.count()
    new_number = existing_codes_count + 1
    final_code = f"{base_code}{new_number}"
    
    return final_code

def create_employee(role: EmployeeProfile.Role, code: str = None, **user_data) -> EmployeeProfile:
    """
    The single source of truth for creating a new employee.
    Accepts an optional 'code'. If not provided, one will be generated.
    """
    first_name = user_data.get('first_name')
    last_name = user_data.get('last_name')

    if not user_data.get('username'):
        user_data['username'] = generate_unique_username(first_name, last_name)
    
    if not user_data.get('email'):
        user_data['email'] = generate_unique_employee_email(first_name, last_name)

    user = User.objects.create(**user_data)
    user.set_unusable_password()
    user.save()

    # TODO: Trigger the password reset email flow for the new user.

    # Use the provided code or generate a new one
    if not code:
        code = generate_employee_code(first_name, last_name)

    profile = EmployeeProfile.objects.create(user=user, role=role, code=code)

    return profile

def regenerate_employee_credentials(profile: EmployeeProfile):
    """
    Updates a user's username, email, and code based on their current first/last name.
    """
    user = profile.user
    first_name = user.first_name
    last_name = user.last_name

    user.username = generate_unique_username(first_name, last_name, user_to_exclude=user)
    user.email = generate_unique_employee_email(first_name, last_name, user_to_exclude=user)
    profile.code = generate_employee_code(first_name, last_name, profile_to_exclude=profile)

    user.save()
    profile.save()
