import csv
import io
import json
import os # Added this line
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.views.generic import ListView, DetailView, CreateView, View
from django.urls import reverse_lazy
from django.http import JsonResponse
from django.db.models import Q, Func, F, Value
from django.db.models.functions import Length
from django.template.loader import render_to_string # Import render_to_string
from .models import Client, ClientGroup, IndustryCode, CustomerTypeCode, IndustrySubCode, Territory
from .forms import CsvUploadForm, DimensionUploadForm, ClientUploadForm, ClientGroupForm, ClientAddressEditForm
from employees.models import EmployeeProfile
from address.models import Address, AddressStatus
from address.forms import AddressSearchForm # Import the AddressSearchForm
from DAO.adresses_DAO import GoogleMapsClient # Import GoogleMapsClient for re-geocoding

# --- Permissions --- 
def is_admin_or_director(user):
    return user.is_superuser or user.groups.filter(name='Directors').exists()

# --- Client Views ---
class ClientListView(ListView):
    model = Client
    template_name = 'client/client_list.html'
    context_object_name = 'clients'
    paginate_by = 25
    def get_queryset(self):
        return Client.objects.select_related('client_group', 'territory', 'address_status').order_by('client_group__name', 'name')

class ClientDetailView(LoginRequiredMixin, UserPassesTestMixin, DetailView):
    model = Client
    template_name = 'client/client_detail.html'
    context_object_name = 'client'

    def test_func(self):
        return is_admin_or_director(self.request.user)

    def get_queryset(self):
        return super().get_queryset().select_related('client_group', 'territory', 'industry_code', 'customer_type_code', 'industry_sub_code', 'address', 'address_status')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['address_search_form'] = AddressSearchForm() # For the Google Maps autocomplete
        context['client_address_edit_form'] = ClientAddressEditForm(instance=self.object) # For manual address editing
        return context

    def post(self, request, *args, **kwargs):
        self.object = self.get_object() # Get the client instance
        form = ClientAddressEditForm(request.POST, instance=self.object)
        if form.is_valid():
            form.save()
            messages.success(request, "Client's original address fields updated successfully!")
            
            gmaps_client = GoogleMapsClient()
            full_address_string = f"{self.object.address1}, {self.object.address2}, {self.object.postal_code}"
            
            business_name = self.object.client_group.name if self.object.client_group else self.object.name
            results = gmaps_client.place_search(business_name, full_address_string)

            if not results:
                results = gmaps_client.geocode(full_address_string)
            
            if results:
                address_obj, created = Address.save_from_google_maps_data(results[0])
                self.object.address = address_obj
                
                # Re-evaluate and set the address status
                if address_obj.is_degenerate():
                    status_obj = AddressStatus.objects.get(name='INCOMPLETE')
                else:
                    status_obj = AddressStatus.objects.get(name='COMPLETE')
                self.object.address_status = status_obj
                
                self.object.save(update_fields=['address', 'address_status'])
                messages.success(request, "Client's geocoded address updated based on new original fields.")
            else:
                # If geocoding fails, set status to MISSING
                self.object.address = None
                self.object.address_status = AddressStatus.objects.get(name='MISSING')
                self.object.save(update_fields=['address', 'address_status'])
                messages.warning(request, "Could not re-geocode address based on updated original fields. The address has been marked as MISSING.")

            return redirect(self.object.get_absolute_url()) # Redirect back to the client detail page
        else:
            messages.error(request, "Error updating client's original address fields.")
            context = self.get_context_data(form=form) # Pass the invalid form back to the template
            return self.render_to_response(context)

class ClientAddressValidationListView(LoginRequiredMixin, UserPassesTestMixin, ListView):
    """A view to list clients with degenerate addresses that need manual correction."""
    model = Client
    template_name = 'client/address_validation_list.html'
    context_object_name = 'clients'
    paginate_by = 50

    def test_func(self):
        return is_admin_or_director(self.request.user)

    def get_queryset(self):
        return Client.objects.filter(address_status__name='INCOMPLETE').select_related('address', 'address_status')

# --- ClientGroup Views ---
class ClientGroupListView(ListView):
    model = ClientGroup
    template_name = 'client/clientgroup_list.html'
    context_object_name = 'client_groups'
    queryset = ClientGroup.objects.order_by('name')

class ClientGroupDetailView(DetailView):
    model = ClientGroup
    template_name = 'client/clientgroup_detail.html'
    context_object_name = 'client_group'
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['related_clients'] = self.object.clients.all().order_by('name')
        return context

class ClientGroupCreateView(CreateView):
    model = ClientGroup
    form_class = ClientGroupForm
    template_name = 'client/clientgroup_form.html'
    success_url = reverse_lazy('client:clientgroup_list')
    def form_valid(self, form):
        messages.success(self.request, "Client Group created successfully!")
        return super().form_valid(form)

# --- Map View ---
class ClientMapView(LoginRequiredMixin, UserPassesTestMixin, View):
    template_name = 'client/client_map.html'

    def test_func(self):
        return is_admin_or_director(self.request.user)

    def get(self, request, *args, **kwargs):
        # Fetch clients that have a geocoded address with latitude and longitude
        clients_with_coords = Client.objects.filter(
            address__latitude__isnull=False,
            address__longitude__isnull=False
        ).select_related('address').values('name', 'address__latitude', 'address__longitude')

        # Prepare data for JavaScript
        client_locations = [
            {
                'name': client['name'],
                'lat': float(client['address__latitude']),
                'lng': float(client['address__longitude']),
            }
            for client in clients_with_coords
        ]
        
        # Pass Google Maps API Key to the template
        google_maps_api_key = os.environ.get('GOOGLE_MAPS_API_KEY')

        context = {
            'client_locations_json': json.dumps(client_locations),
            'google_maps_api_key': google_maps_api_key,
        }
        return render(request, self.template_name, context)

# --- APIs ---
@login_required
def client_search_and_filter_api(request):
    query = request.GET.get('q', '')
    queryset = Client.objects.select_related('client_group', 'address_status').order_by('name')
    if query: queryset = queryset.filter(Q(name__icontains=query) | Q(account_number__icontains=query) | Q(address1__icontains=query) | Q(client_group__name__icontains=query))
    html = render_to_string('client/_client_table_rows.html', {'clients': queryset})
    return JsonResponse({'html': html})

@login_required
def client_group_search_and_filter_api(request):
    query = request.GET.get('q', '')
    queryset = ClientGroup.objects.order_by('name')
    if query: queryset = queryset.filter(Q(name__icontains=query) | Q(code__icontains=query))
    html = render_to_string('client/_clientgroup_table_rows.html', {'client_groups': queryset})
    return JsonResponse({'html': html})

@login_required
def update_client_group_field_api(request):
    if not request.user.is_superuser: return JsonResponse({'status': 'error', 'message': 'Permission denied.'}, status=403)
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            pk, field, value = data.get('pk'), data.get('field'), data.get('value')
            client_group = ClientGroup.objects.get(pk=pk)
            if field == 'name':
                client_group.name = value
                client_group.save(update_fields=['name'])
            else:
                return JsonResponse({'status': 'error', 'message': 'Invalid field.'}, status=400)
            return JsonResponse({'status': 'success', 'message': f'{field} updated.'})
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)
    return JsonResponse({'status': 'error', 'message': 'Invalid request method.'}, status=405)

# --- Upload Views ---
@login_required
@user_passes_test(is_admin_or_director)
def upload_client_view(request):
    form = ClientUploadForm(request.POST or None, request.FILES or None)
    if request.method == 'POST' and form.is_valid():
        csv_file = request.FILES['csv_file']
        if not csv_file.name.endswith('.csv'): messages.error(request, 'This is not a CSV file.'); return redirect('client:upload_client')
        try:
            process_client_csv(csv_file)
            messages.success(request, 'Main client data imported successfully!')
        except Exception as e:
            messages.error(request, f'An error occurred: {e}')
        return redirect('client:upload_client')
    return render(request, 'client/upload_client.html', {'form': form})

@login_required
@user_passes_test(is_admin_or_director)
def upload_dimension_view(request):
    form = DimensionUploadForm(request.POST or None, request.FILES or None)
    if request.method == 'POST' and form.is_valid():
        csv_file = request.FILES['csv_file']
        dimension_type = form.cleaned_data['dimension_type']
        if not csv_file.name.endswith('.csv'): messages.error(request, 'This is not a CSV file.'); return redirect('client:upload_dimension')
        try:
            process_dimension_csv(csv_file, dimension_type)
            messages.success(request, f'{dimension_type.replace("_", " ").title()} data imported successfully!')
        except Exception as e:
            messages.error(request, f'An error occurred: {e}')
        return redirect('client:upload_dimension')
    return render(request, 'client/upload_dimension.html', {'form': form})

@login_required
@user_passes_test(is_admin_or_director)
def upload_client_group_view(request):
    form = CsvUploadForm(request.POST or None, request.FILES or None)
    if request.method == 'POST' and form.is_valid():
        csv_file = request.FILES['csv_file']
        if not csv_file.name.endswith('.csv'): messages.error(request, 'This is not a CSV file.'); return redirect('client:upload_group_csv')
        try:
            process_client_group_csv(csv_file)
            messages.success(request, 'Client Group data imported successfully!')
        except Exception as e:
            messages.error(request, f'An error occurred: {e}')
        return redirect('client:upload_group_csv')
    return render(request, 'client/upload_csv.html', {'form': form})

# --- CSV Processing Logic ---
def process_client_csv(file):
    decoded_file = file.read().decode('utf-8-sig')
    io_string = io.StringIO(decoded_file)
    reader = csv.reader(io_string, delimiter=',')
    territories = {t.code: t for t in Territory.objects.all()}
    industry_codes = {ic.code: ic for ic in IndustryCode.objects.all()}
    customer_type_codes = {ctc.code: ctc for ctc in CustomerTypeCode.objects.all()}
    industry_sub_codes = {isc.code: isc for isc in IndustrySubCode.objects.all()}
    client_groups = {cg.code: cg for cg in ClientGroup.objects.all()}
    gmaps_client = GoogleMapsClient()

    for i, row in enumerate(reader):
        line_num = i + 1
        if not row or len(row) != 10: raise ValueError(f"Row {line_num} is malformed.")
        (terr_code, acc_num, addr1, addr2, postal, client_name, ind_code, cust_type_code, ind_sub_code, parent_code) = [item.strip() for item in row]
        client_group_obj = client_groups.get(parent_code)
        if not client_group_obj: raise ValueError(f"Row {line_num}: Could not find ClientGroup with code ''{parent_code}''.")
        
        client, created = Client.objects.update_or_create(
            account_number=acc_num,
            defaults={
                'name': client_name,
                'address1': addr1, 'address2': addr2, 'postal_code': postal,
                'client_group': client_group_obj, 'territory': territories.get(terr_code),
                'industry_code': industry_codes.get(ind_code), 'customer_type_code': customer_type_codes.get(cust_type_code),
                'industry_sub_code': industry_sub_codes.get(ind_sub_code),
            })

        # --- Automated Geocoding Logic ---
        full_address_string = f"{addr1}, {addr2}, {postal}"
        results = gmaps_client.geocode(full_address_string)
        address_obj = None
        if results:
            address_obj, _ = Address.save_from_google_maps_data(results[0])

        is_degenerate = not address_obj or address_obj.is_degenerate()
        if is_degenerate:
            place_search_results = gmaps_client.place_search(client_group_obj.name, full_address_string)
            if place_search_results:
                address_obj, _ = Address.save_from_google_maps_data(place_search_results[0])

        if address_obj:
            client.address = address_obj
            client.save(update_fields=['address'])

def process_dimension_csv(file, dimension_type):
    decoded_file = file.read().decode('utf-8-sig')
    io_string = io.StringIO(decoded_file)
    reader = csv.reader(io_string, delimiter=',')
    for i, row in enumerate(reader):
        line_num = i + 1
        if not row: continue
        if len(row) > 2: raise ValueError(f"Row {line_num} has too many columns.")
        code = row[0].strip()
        description = row[1].strip() if len(row) > 1 else ''
        if len(code) > 50: raise ValueError(f"Error in row {line_num}: Code ''{code}'' is too long.")
        TargetModel.objects.update_or_create(code=code, defaults={'description': description})

def process_client_group_csv(file):
    decoded_file = file.read().decode('utf-8-sig')
    io_string = io.StringIO(decoded_file)
    reader = csv.reader(io_string, delimiter=',')
    for i, row in enumerate(reader):
        line_num = i + 1
        if not row: continue
        if len(row) != 2: raise ValueError(f"Row {line_num} is malformed.")
        code, name = [item.strip() for item in row]
        if len(code) > 10: raise ValueError(f"Error in row {line_num}: Code ''{code}'' is too long.")
        ClientGroup.objects.update_or_create(code=code, defaults={'name': name})
