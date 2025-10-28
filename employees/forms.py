# employees/forms.py

from django import forms

class TerritoryAssignmentForm(forms.Form):
    csv_file = forms.FileField(
        label='Select a CSV file',
        help_text='The file must have two columns: Territory Code and Manager\'s Employee Code.'
    )
