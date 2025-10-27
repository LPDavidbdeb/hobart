from django import forms

class AddressSearchForm(forms.Form):
    query = forms.CharField(
        label="Search for an address",
        max_length=255,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g., 123 Main St, Ottawa ON'})
    )
