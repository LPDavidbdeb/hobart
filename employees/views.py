import csv
import io
import json
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib.auth.models import Group
from django.views.generic import ListView, DetailView
from django.http import JsonResponse, HttpResponseBadRequest
from django.db import transaction, IntegrityError
from django.db.models import Q, Prefetch
from django.template.loader import render_to_string
from .models import EmployeeProfile
from organization.models import Territory
from .forms import TerritoryAssignmentForm, DirectorCreationForm, ManagerCreationForm, TechnicianCreationForm, EditEmployeeForm
from client.forms import CsvUploadForm # Corrected import
from .utils import create_employee
from address.forms import AddressSearchForm
from client.models import Client
from address.models import FSA, PostalCode
from django.conf import settings
from django.contrib.gis.geos import Point
from django.utils import timezone
from DAO.adresses_DAO import GoogleMapsClient

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
        # Fetch related user, address, and postal code in a single query
        return EmployeeProfile.objects.filter(role=self.role).select_related('user', 'postal_code', 'address_status').order_by('user__first_name')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = self.page_title
        context['role_name'] = self.role.label if self.role else ''
        
        if 'form' not in kwargs and self.form_class:
            # Determine the correct queryset for the 'reports_to' field
            superiors_queryset = EmployeeProfile.objects.none()
            if self.role == EmployeeProfile.Role.MANAGER:
                superiors_queryset = EmployeeProfile.objects.filter(role=EmployeeProfile.Role.DIRECTOR)
            elif self.role == EmployeeProfile.Role.TECHNICIAN:
                superiors_queryset = EmployeeProfile.objects.filter(role=EmployeeProfile.Role.MANAGER)
            
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

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Provide a list of all technicians for the successor dropdown in the delete modal
        context['all_technicians'] = EmployeeProfile.objects.filter(role=EmployeeProfile.Role.TECHNICIAN).select_related('user').order_by('user__first_name')
        return context

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
    if request.method == 'POST':
        form = EditEmployeeForm(request.POST, instance=profile, user_instance=profile.user)
        if form.is_valid():
            form.save()
            messages.success(request, f"Successfully updated {profile.user.get_full_name()}.")
            return redirect(profile.get_absolute_url())
    else:
        form = EditEmployeeForm(instance=profile, user_instance=profile.user)
        
    return render(request, 'employees/edit_employee.html', {'form': form, 'employee': profile})

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

        # --- Data for Promotion Modal ---
        if employee.role == EmployeeProfile.Role.TECHNICIAN:
            # Successors are other technicians
            context['successor_technicians'] = EmployeeProfile.objects.filter(
                role=EmployeeProfile.Role.TECHNICIAN
            ).exclude(pk=employee.pk).select_related('user').order_by('user__first_name')
            # Managers that can be replaced
            context['replaceable_managers'] = EmployeeProfile.objects.filter(
                role=EmployeeProfile.Role.MANAGER
            ).select_related('user').order_by('user__first_name')

        # --- Add other context variables ---
        context['address_search_form'] = AddressSearchForm()
        context['GOOGLE_MAPS_API_KEY'] = settings.GOOGLE_MAPS_API_KEY
        
        return context

# --- Promotion and Deletion Views ---
@login_required
@user_passes_test(is_admin_or_director)
@transaction.atomic
def promote_technician(request, pk):
    if request.method != 'POST':
        return HttpResponseBadRequest("Invalid request method.")

    technician_to_promote = get_object_or_404(EmployeeProfile, pk=pk, role=EmployeeProfile.Role.TECHNICIAN)
    action = request.POST.get('promotion_action')

    try:
        if action == 'assign_successor':
            successor_id = request.POST.get('successor_technician')
            successor = get_object_or_404(EmployeeProfile, pk=successor_id, role=EmployeeProfile.Role.TECHNICIAN)
            
            # Transfer FSAs
            fsas_to_transfer = list(technician_to_promote.responsible_fsas.all())
            successor.responsible_fsas.add(*fsas_to_transfer)
            technician_to_promote.responsible_fsas.clear()
            
            # Promote the technician
            technician_to_promote.role = EmployeeProfile.Role.MANAGER
            technician_to_promote.save()
            
            messages.success(request, f"{technician_to_promote.user.get_full_name()} has been promoted to Manager. Their {len(fsas_to_transfer)} FSAs were transferred to {successor.user.get_full_name()}.")

        elif action == 'replace_manager':
            manager_to_replace_id = request.POST.get('replaced_manager')
            manager_to_replace = get_object_or_404(EmployeeProfile, pk=manager_to_replace_id, role=EmployeeProfile.Role.MANAGER)
            
            # Promote the technician
            technician_to_promote.role = EmployeeProfile.Role.MANAGER
            technician_to_promote.reports_to = manager_to_replace.reports_to
            technician_to_promote.save()

            # Transfer subordinates
            subordinates_to_transfer = list(manager_to_replace.subordinates.all())
            for sub in subordinates_to_transfer:
                sub.reports_to = technician_to_promote
                sub.save()

            # Transfer territories
            territories_to_transfer = list(manager_to_replace.territories.all())
            technician_to_promote.territories.add(*territories_to_transfer)
            
            # Deactivate the old manager
            manager_to_replace.user.is_active = False
            manager_to_replace.user.save()
            # Optional: Clear their responsibilities
            manager_to_replace.subordinates.clear()
            manager_to_replace.territories.clear()
            
            messages.success(request, f"{technician_to_promote.user.get_full_name()} has been promoted and has replaced {manager_to_replace.user.get_full_name()}.")

        else:
            messages.error(request, "Invalid promotion action specified.")
            return redirect(technician_to_promote.get_absolute_url())

    except Exception as e:
        messages.error(request, f"An error occurred during the promotion: {e}")
        # The transaction.atomic decorator will automatically roll back changes.
        return redirect(technician_to_promote.get_absolute_url())

    return redirect(technician_to_promote.get_absolute_url())

@login_required
@user_passes_test(is_admin_or_director)
@transaction.atomic
def delete_technician(request, pk):
    if request.method != 'POST':
        return HttpResponseBadRequest("Invalid request method.")

    technician_to_delete = get_object_or_404(EmployeeProfile, pk=pk, role=EmployeeProfile.Role.TECHNICIAN)
    
    try:
        # Scenario 1: Direct delete if no FSAs
        if not technician_to_delete.responsible_fsas.exists():
            user_full_name = technician_to_delete.user.get_full_name()
            technician_to_delete.user.delete() # This will cascade and delete the profile
            messages.success(request, f"Technician '{user_full_name}' had no assigned FSAs and has been deleted.")
        
        # Scenario 2: Delete with successor
        else:
            successor_id = request.POST.get('successor_technician')
            if not successor_id:
                messages.error(request, "A successor was not specified for a technician with active FSAs.")
                return redirect('employees:technician_list')

            successor = get_object_or_404(EmployeeProfile, pk=successor_id, role=EmployeeProfile.Role.TECHNICIAN)
            
            # Transfer FSAs
            fsas_to_transfer = list(technician_to_delete.responsible_fsas.all())
            successor.responsible_fsas.add(*fsas_to_transfer)
            
            # Delete the old technician
            user_full_name = technician_to_delete.user.get_full_name()
            technician_to_delete.user.delete()
            
            messages.success(request, f"Technician '{user_full_name}' has been deleted. Their {len(fsas_to_transfer)} FSAs were transferred to {successor.user.get_full_name()}.")

    except Exception as e:
        messages.error(request, f"An error occurred during the deletion: {e}")
        # The transaction.atomic decorator will automatically roll back changes.
    
    return redirect('employees:technician_list')

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
def employee_role_search_api(request):
    role = request.GET.get('role', '').upper()
    query = request.GET.get('q', '')

    if not role:
        return HttpResponseBadRequest("Role parameter is required.")

    valid_roles = [r[0] for r in EmployeeProfile.Role.choices]
    if role not in valid_roles:
        return HttpResponseBadRequest(f"Invalid role specified. Must be one of: {', '.join(valid_roles)}")

    queryset = EmployeeProfile.objects.filter(role=role).select_related('user', 'postal_code', 'address_status').order_by('user__first_name')

    if query:
        queryset = queryset.filter(
            Q(user__first_name__icontains=query) |
            Q(user__last_name__icontains=query) |
            Q(code__icontains=query)
        )

    context = {
        'object_list': queryset,
        'role_name': role,
        'request': request
    }
    if role == 'TECHNICIAN':
        context['all_technicians'] = EmployeeProfile.objects.filter(role=EmployeeProfile.Role.TECHNICIAN).select_related('user')

    html = render_to_string('employees/_employee_table_rows.html', context)
    return JsonResponse({'html': html})

@login_required
def employee_search_filter_api(request):
    search_query = request.GET.get('search_query', '')
    role_filter = request.GET.get('role_filter', '')

    employees = EmployeeProfile.objects.select_related('user', 'reports_to__user').order_by('user__first_name', 'user__last_name')

    if search_query:
        employees = employees.filter(
            Q(user__first_name__icontains=search_query) |
            Q(user__last_name__icontains=search_query) |
            Q(user__email__icontains=search_query) |
            Q(code__icontains=search_query)
        )

    if role_filter:
        # Ensure the role_filter matches one of the EmployeeProfile.Role choices
        valid_roles = [role.value for role in EmployeeProfile.Role]
        if role_filter in valid_roles:
            employees = employees.filter(role=role_filter)
        else:
            return JsonResponse({'error': 'Invalid role filter'}, status=400)

    # Prepare data for JSON response
    employee_data = []
    for employee in employees:
        employee_data.append({
            'id': employee.id,
            'full_name': employee.user.get_full_name(),
            'role': employee.get_role_display(),
            'code': employee.code,
            'reports_to': employee.reports_to.user.get_full_name() if employee.reports_to else 'N/A',
            'detail_url': reverse('employees:employee_detail', args=[employee.id]),
            'edit_url': reverse('employees:edit_employee', args=[employee.id]),
        })

    return JsonResponse({'employees': employee_data})

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
        data['total_clients'] = sum(fsa.client_count for fsa in fsas)

    elif employee.role == EmployeeProfile.Role.MANAGER:
        subordinates = employee.subordinates.filter(role=EmployeeProfile.Role.TECHNICIAN).prefetch_related('responsible_fsas')
        total = 0
        for sub in subordinates:
            total += sum(fsa.client_count for fsa in sub.responsible_fsas.all())
        data['total_clients'] = total

    elif employee.role == EmployeeProfile.Role.DIRECTOR:
        managers = employee.subordinates.filter(role=EmployeeProfile.Role.MANAGER).prefetch_related('subordinates__responsible_fsas')
        total = 0
        for manager in managers:
            for tech in manager.subordinates.all():
                total += sum(fsa.client_count for fsa in tech.responsible_fsas.all())
        data['total_clients'] = total

    return JsonResponse(data)

@login_required
def employee_fsa_geometry_api(request, pk):
    try:
        employee = get_object_or_404(EmployeeProfile, pk=pk)

        if employee.role != EmployeeProfile.Role.TECHNICIAN:
            return JsonResponse({'error': 'Employee is not a technician'}, status=400)

        # Fetch all valid simplified FSA boundaries for this technician
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
                        'technician_id': employee.pk, # Add technician ID for coloring
                        'technician_name': employee.user.get_full_name()
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

@login_required
def manager_fsa_geometry_api(request, pk):
    try:
        employee = get_object_or_404(EmployeeProfile, pk=pk)

        if employee.role not in [EmployeeProfile.Role.MANAGER, EmployeeProfile.Role.DIRECTOR]:
            return JsonResponse({'error': 'Employee is not a manager or director'}, status=400)

        # Collect all subordinate technicians
        subordinate_technicians = set()
        if employee.role == EmployeeProfile.Role.MANAGER:
            subordinate_technicians.update(employee.subordinates.filter(role=EmployeeProfile.Role.TECHNICIAN))
        elif employee.role == EmployeeProfile.Role.DIRECTOR:
            managers = employee.subordinates.filter(role=EmployeeProfile.Role.MANAGER)
            for manager in managers:
                subordinate_technicians.update(manager.subordinates.filter(role=EmployeeProfile.Role.TECHNICIAN))
        
        features = []
        # Removed processed_fsa_codes set to allow all FSAs to be included,
        # even if shared by multiple technicians, for proper color-coding.

        for tech in subordinate_technicians:
            valid_fsas = tech.responsible_fsas.filter(simplified_boundary__isnull=False)
            for fsa in valid_fsas:
                if fsa.simplified_boundary:
                    features.append({
                        'type': 'Feature',
                        'geometry': json.loads(fsa.simplified_boundary.json),
                        'properties': {
                            'code': fsa.code,
                            'client_count': fsa.client_count,
                            'technician_id': tech.pk, # Associate FSA with the technician
                            'technician_name': tech.user.get_full_name()
                        }
                    })

        return JsonResponse({
            'type': 'FeatureCollection',
            'features': features
        })

    except (EmployeeProfile.DoesNotExist, ValueError):
        return HttpResponseBadRequest(f"Invalid employee_id: {pk}")
    except Exception as e:
        return JsonResponse({'error': f'An error occurred during geometry processing: {str(e)}'}, status=500)

@login_required
def fsa_clients_api(request, fsa_code):
    try:
        # Find the FSA object
        fsa_obj = get_object_or_404(FSA, code=fsa_code.upper())

        # Filter clients that have a non-null address, valid lat/lng,
        # and whose address.location intersects with the FSA's boundary
        clients = Client.objects.filter(
            address__isnull=False,
            address__latitude__isnull=False,
            address__longitude__isnull=False,
            address__location__intersects=fsa_obj.boundary # Spatial filter
        ).select_related('address') # Select related address to avoid N+1 queries

        client_data = []
        for client in clients:
            address = client.address
            # Still check for is_degenerate as it's a business rule for address validity
            if not address.is_degenerate():
                client_data.append({
                    'name': client.name,
                    'lat': float(address.latitude),
                    'lng': float(address.longitude),
                    'account_number': client.account_number,
                    'url': reverse('client:client_detail', kwargs={'pk': client.pk})
                })
        return JsonResponse({'clients': client_data})
    except FSA.DoesNotExist:
        return HttpResponseBadRequest(f"FSA with code '{fsa_code}' not found.")
    except Exception as e:
        return JsonResponse({'error': f'An error occurred fetching clients: {str(e)}'}, status=500)

@login_required
@user_passes_test(lambda u: u.is_superuser)
def geocode_and_set_postal_code_api(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            employee_id = data.get('employee_id')
            postal_code_str = data.get('postal_code', '').strip().upper().replace(' ', '')

            if not employee_id or not postal_code_str:
                return JsonResponse({'status': 'error', 'message': 'Employee ID and postal code are required.'}, status=400)

            employee = get_object_or_404(EmployeeProfile, pk=employee_id)
            
            # Get or create the postal code object
            postal_code_obj, created = PostalCode.objects.get_or_create(code=postal_code_str)

            # If it's a new postal code or doesn't have a location, geocode it
            if created or not postal_code_obj.location:
                try:
                    gmaps = GoogleMapsClient()
                    geocode_result = gmaps.geocode_postal_code(postal_code_str)
                except ValueError as e: # Catches the API key error
                    return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

                if not geocode_result:
                    return JsonResponse({'status': 'error', 'message': f'Could not geocode postal code: {postal_code_str}'}, status=400)

                location = geocode_result[0]['geometry']['location']
                lat, lng = location['lat'], location['lng']
                postal_code_obj.latitude = lat
                postal_code_obj.longitude = lng
                postal_code_obj.location = Point(lng, lat, srid=4326)
                postal_code_obj.last_geocoded = timezone.now()
                postal_code_obj.save()

            # Assign the postal code to the employee
            employee.postal_code = postal_code_obj
            employee.save()

            return JsonResponse({'status': 'success', 'message': f'Successfully assigned postal code {postal_code_str}.', 'postal_code': postal_code_str})

        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)
            
    return JsonResponse({'status': 'error', 'message': 'Invalid request method.'}, status=405)
