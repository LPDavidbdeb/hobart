from django import forms
from .models import ClientGroup, Client

class CsvUploadForm(forms.Form):
    csv_file = forms.FileField(
        label='Select a Client Group CSV file',
        help_text='IMPORTANT: The file must NOT have a header row. It must be comma-separated. Column order: Code, Name'
    )

class DimensionUploadForm(forms.Form):
    DIMENSION_CHOICES = (
        ('industry_code', 'Industry Code'),
        ('customer_type_code', 'Customer Type Code'),
        ('industry_sub_code', 'Industry Sub-Code'),
        ('territory', 'Territory'),
    )

    dimension_type = forms.ChoiceField(
        choices=DIMENSION_CHOICES,
        widget=forms.RadioSelect,
        label='Select the type of dimension to upload'
    )
    csv_file = forms.FileField(
        label='Select a CSV file',
        help_text='File must be comma-separated. Column order: Code, Description. The Description column can be empty.'
    )

class ClientUploadForm(forms.Form):
    csv_file = forms.FileField(
        label='Select a Client CSV file',
        help_text='File must be comma-separated, with no header. Columns: Order Territory Code, Account, Address1, Address2, Postal, Name, Industry Code, Customer Type Code, Industry Sub-Code Code, Parent'
    )

class ClientGroupForm(forms.ModelForm):
    class Meta:
        model = ClientGroup
        fields = ['code', 'name']

class ClientAddressEditForm(forms.ModelForm):
    """
    Form for manually editing a client's original address fields (address1, address2, postal_code).
    """
    class Meta:
        model = Client
        fields = ['address1', 'address2', 'postal_code']
        widgets = {
            'address1': forms.TextInput(attrs={'class': 'form-control'}),
            'address2': forms.TextInput(attrs={'class': 'form-control'}),
            'postal_code': forms.TextInput(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Make fields required for data quality, but allow them to be empty if they were already empty
        # This ensures that if a field was legitimately empty, it can remain so, but if it's being edited, it should be filled.
        self.fields['address1'].required = True
        self.fields['postal_code'].required = True

