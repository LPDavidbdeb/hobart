import csv
import io
import json
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib.auth.models import User, Group
from django.views.generic import ListView, DetailView
from django.http import JsonResponse, HttpResponseBadRequest
from django.db import transaction, IntegrityError
from django.db.models import Q, Prefetch, Sum
from django.contrib.gis.db.models.functions import AsGeoJSON # Removed Union
from django.template.loader import render_to_string
from .models import EmployeeProfile
from organization.models import Territory
from .forms import TerritoryAssignmentForm, DirectorCreationForm, ManagerCreationForm, TechnicianCreationForm
from client.forms import CsvUploadForm # Corrected import
from .utils import create_employee
from address.forms import AddressSearchForm

# --- Permissions --- 
def is_admin_or_director(user):
    return user.is_superuser or user.groups.filter(name='Directors').exists()

# --- Generic Employee List View --- #
class BaseEmployeeListView(LoginRequiredMixin, UserPassesTestMixin, ListView):
    model = EmployeeProfile
    template_name = 'employees/employee_list_generic.html'
    context_object_name = 'object_list'
    role = None
    form_class = None
    page_title = "Employee List"

    def test_func(self):
        return self.request.user.is_superuser

    def get_queryset(self):
        # Fetch related user and address in a single query
        return EmployeeProfile.objects.filter(role=self.role).select_related('user', 'address').order_by('user__first_name')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = self.page_title
        context['role_name'] = self.role.label
        
        if 'form' not in kwargs and self.form_class:
            # --- THIS IS THE FIX ---
            # Determine the correct queryset for the 'reports_to' field
            superiors_queryset = EmployeeProfile.objects.none()
            if self.role == EmployeeProfile.Role.MANAGER:
                superiors_queryset = EmployeeProfile.objects.filter(role=EmployeeProfile.Role.DIRECTOR)
            elif self.role == EmployeeProfile.Role.TECHNICIAN:
                superiors_queryset = EmployeeProfile.objects.filter(role=EmployeeProfile.Role.MANAGER)
            
            # Pass the filtered queryset to the form
            context['form'] = self.form_class(superiors_queryset=superiors_queryset)
            
        return context

    def post(self, request, *args, **kwargs):
        # We need to pass the queryset to the form on POST as well
        superiors_queryset = EmployeeProfile.objects.none()
        if self.role == EmployeeProfile.Role.MANAGER:
            superiors_queryset = EmployeeProfile.objects.filter(role=EmployeeProfile.Role.DIRECTOR)
        elif self.role == EmployeeProfile.Role.TECHNICIAN:
            superiors_queryset = EmployeeProfile.objects.filter(role=EmployeeProfile.Role.MANAGER)

        form = self.form_class(request.POST, superiors_queryset=superiors_queryset)

        if form.is_valid():
            form.save()
            messages.success(request, f'{self.role.label} created successfully!')
            return redirect(request.path)
        else:
            self.object_list = self.get_queryset()
            context = self.get_context_data(form=form, form_errors=True)
            return self.render_to_response(context)

# --- Role-Specific List Views --- #
class DirectorListView(BaseEmployeeListView):
    role = EmployeeProfile.Role.DIRECTOR
    form_class = DirectorCreationForm
    page_title = "Director List"

class ManagerListView(BaseEmployeeListView):
    role = EmployeeProfile.Role.MANAGER
    form_class = ManagerCreationForm
    page_title = "Manager List"

class TechnicianListView(BaseEmployeeListView):
    role = EmployeeProfile.Role.TECHNICIAN
    form_class = TechnicianCreationForm
    page_title = "Technician List"

# --- Employee List View (All Employees) ---
class EmployeeListView(ListView):
    model = EmployeeProfile
    template_name = 'employees/employee_list.html'
    context_object_name = 'employees'
    # Fetch related user and address in a single query
    queryset = EmployeeProfile.objects.select_related('user', 'address').order_by('user__first_name', 'user__last_name')

# --- Edit and Detail Views ---
@login_required
@user_passes_test(lambda u: u.is_superuser)
def edit_employee_view(request, pk):
    profile = get_object_or_404(EmployeeProfile, pk=pk)
    user_to_edit = profile.user
    if request.method == 'POST':
        # form = EditEmployeeForm(request.POST, instance=user_to_edit) # This form doesn't exist yet
        # if form.is_valid():
        #     form.save()
        #     messages.success(request, f"Successfully updated {user_to_edit.get_full_name()} and regenerated credentials.")
        #     if profile.role == EmployeeProfile.Role.MANAGER:
        #         return redirect('employees:manager_list')
        #     return redirect('employees:employee_list')
        pass # Placeholder
    else:
        # form = EditEmployeeForm(instance=user_to_edit)
        pass # Placeholder
    return render(request, 'employees/edit_employee.html', {'form': None, 'employee': profile})

class EmployeeDetailView(DetailView):
    model = EmployeeProfile
    template_name = 'employees/employee_detail.html'
    context_object_name = 'employee'

    def get_queryset(self):
        # Prefetch related data to optimize queries
        return super().get_queryset().select_related(
            'user', 'reports_to__user', 'address'
        ).prefetch_related(
            'responsible_fsas',
            Prefetch(
                'subordinates',
                queryset=EmployeeProfile.objects.select_related('user').prefetch_related(
                    'responsible_fsas',
                    Prefetch(
                        'subordinates',
                        queryset=EmployeeProfile.objects.select_related('user').prefetch_related('responsible_fsas')
                    )
                )
            )
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        employee = self.object

        # --- Breadcrumb Trail ---
        breadcrumbs = []
        current = employee.reports_to
        while current:
            breadcrumbs.append(current)
            current = current.reports_to
        context['breadcrumbs'] = reversed(breadcrumbs)

        # --- Supervisor Edit Logic ---
        if self.request.user.is_superuser:
            possible_supervisors = EmployeeProfile.objects.exclude(pk=employee.pk)
            if employee.role == EmployeeProfile.Role.TECHNICIAN:
                possible_supervisors = possible_supervisors.filter(role=EmployeeProfile.Role.MANAGER)
            elif employee.role == EmployeeProfile.Role.MANAGER:
                possible_supervisors = possible_supervisors.filter(role=EmployeeProfile.Role.DIRECTOR)
            else:
                possible_supervisors = possible_supervisors.none()
            context['supervisors'] = possible_supervisors.select_related('user').order_by('user__first_name')

        context['address_search_form'] = AddressSearchForm()
        return context

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        employee = self.object

        # --- Breadcrumb Trail ---
        breadcrumbs = []
        current = employee.reports_to
        while current:
            breadcrumbs.append(current)
            current = current.reports_to
        context['breadcrumbs'] = reversed(breadcrumbs)

        # --- Supervisor Edit Logic ---
        if self.request.user.is_superuser:
            possible_supervisors = EmployeeProfile.objects.exclude(pk=employee.pk)
            if employee.role == EmployeeProfile.Role.TECHNICIAN:
                possible_supervisors = possible_supervisors.filter(role=EmployeeProfile.Role.MANAGER)
            elif employee.role == EmployeeProfile.Role.MANAGER:
                possible_supervisors = possible_supervisors.filter(role=EmployeeProfile.Role.DIRECTOR)
            else:
                possible_supervisors = possible_supervisors.none()
            context['supervisors'] = possible_supervisors.select_related('user').order_by('user__first_name')

        context['address_search_form'] = AddressSearchForm()
        return context

# --- CSV Upload Views ---
@login_required
@user_passes_test(is_admin_or_director)
def upload_csv_view(request):
    form = CsvUploadForm(request.POST or None, request.FILES or None)
    if request.method == 'POST' and form.is_valid():
        csv_file = request.FILES['csv_file']
        if not csv_file.name.endswith('.csv'):
            messages.error(request, 'This is not a CSV file.')
            return redirect('employees:upload_csv')
        try:
            process_employee_csv(csv_file)
            messages.success(request, 'Employee data imported successfully!')
        except Exception as e:
            messages.error(f'An error occurred: {e}')
        return redirect('employees:upload_csv')
    return render(request, 'employees/upload_csv.html', {'form': form})

@login_required
@user_passes_test(lambda u: u.is_superuser)
def territory_assignment_upload(request):
    if request.method == 'POST':
        form = TerritoryAssignmentForm(request.POST, request.FILES)
        if form.is_valid():
            csv_file = request.FILES['csv_file']
            if not csv_file.name.endswith('.csv'):
                messages.error(request, "This is not a CSV file.")
                return redirect('employees:territory_assignment_upload')

            try:
                decoded_file = csv_file.read().decode('utf-8-sig')
                io_string = io.StringIO(decoded_file)
                reader = csv.reader(io_string)
                
                # Skip header row if it exists
                next(reader, None)

                assignments = []
                for row in reader:
                    if not row: continue
                    territory_code, employee_code = row
                    assignments.append((territory_code.strip(), employee_code.strip()))

                with transaction.atomic():
                    for territory_code, employee_code in assignments:
                        try:
                            territory = Territory.objects.get(code=territory_code)
                            manager = EmployeeProfile.objects.get(code=employee_code, role=EmployeeProfile.Role.MANAGER)
                            manager.territories.add(territory)
                        except Territory.DoesNotExist:
                            raise ValueError(f"Territory with code '{territory_code}' not found.")
                        except EmployeeProfile.DoesNotExist:
                            raise ValueError(f"Manager with code '{employee_code}' not found.")
                
                messages.success(request, f"{len(assignments)} territory assignments have been processed successfully.")

            except (UnicodeDecodeError, IntegrityError, ValueError) as e:
                messages.error(request, f"An error occurred: {e}")
            
            return redirect('employees:territory_assignment_upload')
    else:
        form = TerritoryAssignmentForm()
    
    return render(request, 'employees/territory_assignment_upload.html', {'form': form})

def process_employee_csv(file):
    decoded_file = file.read().decode('utf-8-sig')
    io_string = io.StringIO(decoded_file)
    reader = csv.reader(io_string, delimiter=',')
    ROLE_MAP = {
        'DIRECTOR': EmployeeProfile.Role.DIRECTOR,
        'MANAGER': EmployeeProfile.Role.MANAGER,
        'TECHNICIAN': EmployeeProfile.Role.TECHNICIAN,
        'DISPATCHER': EmployeeProfile.Role.DISPATCHER,
    }
    employee_to_supervisor_map = {}
    for i, row in enumerate(reader):
        line_num = i + 1
        if not row: continue
        if len(row) != 4: raise ValueError(f"Row {line_num} is malformed.")
        code, full_name, title, supervisor_code = [item.strip() for item in row]
        if len(code) > 20: raise ValueError(f"Error in row {line_num}: Code ''{code}'' is too long.")
        employee_role = ROLE_MAP.get(title.upper())
        if not employee_role: raise ValueError(f"Invalid role ''{title}'' in row {line_num}.")
        
        profile = EmployeeProfile.objects.filter(code=code).first()
        first, last = full_name.split(' ', 1)
        
        if profile:
            user = profile.user
            user.first_name = first
            user.last_name = last
            user.save(update_fields=['first_name', 'last_name'])
            profile.role = employee_role
            profile.save(update_fields=['role'])
        else:
            user_data = {
                'first_name': first,
                'last_name': last,
            }
            profile = create_employee(role=employee_role, code=code, **user_data)
            user = profile.user

        try:
            group_name = title.capitalize() + 's'
            if title.upper() == 'DISPATCHER': group_name = 'Dispatchers'
            if title.upper() == 'TECHNICIAN': group_name = 'Technicians'
            group = Group.objects.get(name=group_name)
            user.groups.clear()
            user.groups.add(group)
        except Group.DoesNotExist:
            raise Exception(f"Group ''{group_name}'' does not exist.")
        
        if supervisor_code and supervisor_code != 'Null':
            employee_to_supervisor_map[code] = supervisor_code

    for emp_code, sup_code in employee_to_supervisor_map.items():
        try:
            employee_profile = EmployeeProfile.objects.get(code=emp_code)
            supervisor_profile = EmployeeProfile.objects.get(code=sup_code)
            employee_profile.reports_to = supervisor_profile
            employee_profile.save()
        except EmployeeProfile.DoesNotExist:
            raise Exception(f"Hierarchy failed: Could not find profile for code {emp_code} or {sup_code}")

# --- APIs for AJAX functionality ---
@login_required
def employee_search_and_filter_api(request):
    query = request.GET.get('q', '')
    queryset = EmployeeProfile.objects.select_related('user').order_by('user__first_name', 'user__last_name')
    if query:
        queryset = queryset.filter(
            Q(user__first_name__icontains=query) |
            Q(user__last_name__icontains=query) |
            Q(user__username__icontains=query) |
            Q(code__icontains=query)
        )
    html = render_to_string('employees/_employee_table_rows.html', {'employees': queryset})
    return JsonResponse({'html': html})

@login_required
def update_employee_field_api(request):
    if not request.user.is_superuser: return JsonResponse({'status': 'error', 'message': 'Permission denied.'}, status=403)
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            pk, field, value = data.get('pk'), data.get('field'), data.get('value')
            profile = EmployeeProfile.objects.get(pk=pk)
            user = profile.user
            if field == 'first_name':
                user.first_name = value
                user.save(update_fields=['first_name'])
            elif field == 'last_name':
                user.last_name = value
                user.save(update_fields=['last_name'])
            elif field == 'reports_to':
                profile.reports_to = EmployeeProfile.objects.get(pk=value) if value else None
                profile.save(update_fields=['reports_to'])
            else:
                return JsonResponse({'status': 'error', 'message': 'Invalid field.'}, status=400)
            return JsonResponse({'status': 'success', 'message': f'{field} updated.'})
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)
    return JsonResponse({'status': 'error', 'message': 'Invalid request method.'}, status=405)

@login_required
def client_counts_api(request):
    employee_id = request.GET.get('employee_id')
    if not employee_id:
        return HttpResponseBadRequest("Missing 'employee_id' parameter.")

    try:
        employee = EmployeeProfile.objects.get(pk=employee_id)
    except (EmployeeProfile.DoesNotExist, ValueError):
        return HttpResponseBadRequest(f"Invalid employee_id: {employee_id}")

    data = {"total_clients": 0, "breakdown": []}

    if employee.role == EmployeeProfile.Role.TECHNICIAN:
        fsas = employee.responsible_fsas.all()
        for fsa in fsas:
            data['breakdown'].append({"label": fsa.code, "value": fsa.client_count, "id": fsa.pk})
        data['total_clients'] = sum(item['value'] for item in data['breakdown'])

    elif employee.role == EmployeeProfile.Role.MANAGER:
        subordinates = employee.subordinates.filter(role=EmployeeProfile.Role.TECHNICIAN).annotate(
            total_clients_for_tech=Sum('responsible_fsas__client_count')
        ).select_related('user')
        for sub in subordinates:
            data['breakdown'].append({
                "label": sub.user.get_full_name(),
                "value": sub.total_clients_for_tech or 0,
                "id": sub.pk
            })
        data['total_clients'] = sum(item['value'] for item in data['breakdown'])

    elif employee.role == EmployeeProfile.Role.DIRECTOR:
        subordinates = employee.subordinates.filter(role=EmployeeProfile.Role.MANAGER).annotate(
            total_clients_for_manager=Sum('subordinates__responsible_fsas__client_count')
        ).select_related('user')
        for sub in subordinates:
            data['breakdown'].append({
                "label": sub.user.get_full_name(),
                "value": sub.total_clients_for_manager or 0,
                "id": sub.pk
            })
        data['total_clients'] = sum(item['value'] for item in data['breakdown'])

    return JsonResponse(data)

@login_required
def employee_fsa_geometry_api(request, pk):
    try:
        employee = get_object_or_404(EmployeeProfile, pk=pk)

        if employee.role != EmployeeProfile.Role.TECHNICIAN:
            return JsonResponse({'error': 'Employee is not a technician'}, status=400)

        # Fetch all valid simplified FSA boundaries for this technician
        # No Union operation here
        valid_fsas = employee.responsible_fsas.filter(simplified_boundary__isnull=False)
        
        if not valid_fsas.exists():
            return JsonResponse({'type': 'FeatureCollection', 'features': []})

        features = []
        for fsa in valid_fsas:
            # Convert each simplified_boundary to GeoJSON
            if fsa.simplified_boundary:
                features.append({
                    'type': 'Feature',
                    'geometry': json.loads(fsa.simplified_boundary.json),
                    'properties': {
                        'code': fsa.code,
                        'client_count': fsa.client_count,
                        'employee_name': employee.user.get_full_name()
                    }
                })

        return JsonResponse({
            'type': 'FeatureCollection',
            'features': features
        })

    except (EmployeeProfile.DoesNotExist, ValueError):
        return HttpResponseBadRequest(f"Invalid employee_id: {pk}")
    except Exception as e:
        # Catch potential database errors and return a clean error
        return JsonResponse({'error': f'An error occurred during geometry processing: {str(e)}'}, status=500)
