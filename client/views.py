import csv
import io
import json
from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.views.generic import ListView, DetailView, CreateView
from django.urls import reverse_lazy
from django.http import JsonResponse
from django.db.models import Q
from django.template.loader import render_to_string
from .models import Client, ClientGroup, IndustryCode, CustomerTypeCode, IndustrySubCode, Territory
from .forms import CsvUploadForm, DimensionUploadForm, ClientUploadForm, ClientGroupForm

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
        return Client.objects.select_related('client_group', 'territory').order_by('name', 'account_number')

class ClientDetailView(DetailView):
    model = Client
    template_name = 'client/client_detail.html'
    context_object_name = 'client'
    def get_queryset(self):
        return super().get_queryset().select_related('client_group', 'territory', 'industry_code', 'customer_type_code', 'industry_sub_code')

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
        # Add the list of related clients to the context
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

# --- APIs ---
@login_required
def client_search_and_filter_api(request):
    query = request.GET.get('q', '')
    queryset = Client.objects.select_related('client_group').order_by('name')
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

# --- Upload Views & Logic ---
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
    for i, row in enumerate(reader):
        line_num = i + 1
        if not row or len(row) != 10: raise ValueError(f"Row {line_num} is malformed.")
        (terr_code, acc_num, addr1, addr2, postal, client_name, ind_code, cust_type_code, ind_sub_code, parent_code) = [item.strip() for item in row]
        client_group_obj = client_groups.get(parent_code)
        if not client_group_obj: raise ValueError(f"Row {line_num}: Could not find ClientGroup with code ''{parent_code}''.")
        Client.objects.update_or_create(
            account_number=acc_num,
            defaults={
                'name': client_name,
                'address1': addr1, 'address2': addr2, 'postal_code': postal,
                'client_group': client_group_obj, 'territory': territories.get(terr_code),
                'industry_code': industry_codes.get(ind_code), 'customer_type_code': customer_type_codes.get(cust_type_code),
                'industry_sub_code': industry_sub_codes.get(ind_sub_code),
            })

def process_dimension_csv(file, dimension_type):
    decoded_file = file.read().decode('utf-8-sig')
    MODEL_MAP = {'industry_code': IndustryCode, 'customer_type_code': CustomerTypeCode, 'industry_sub_code': IndustrySubCode, 'territory': Territory}
    TargetModel = MODEL_MAP.get(dimension_type)
    if not TargetModel: raise ValueError("Invalid dimension type specified.")
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
