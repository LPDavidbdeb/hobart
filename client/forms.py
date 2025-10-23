from django import forms
from .models import ClientGroup

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
