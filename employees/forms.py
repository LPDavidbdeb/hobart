from django import forms

class CsvUploadForm(forms.Form):
    csv_file = forms.FileField(
        label='Select a CSV file',
        help_text='IMPORTANT: The file must NOT have a header row. It must be comma-separated. Column order: Code, Full Name, Title, Supervisor Code. Valid Titles: DIRECTOR, MANAGER, TECHNICIAN, DISPATCHER.'
    )
