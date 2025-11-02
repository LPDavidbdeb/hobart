# In organization/tree_definitions.py

from django.conf import settings

# --- 1. BASE PATH CONFIGURATION ---
# This points to 'your_project_root/DL/geodata/'
BASE_GEODATA_PATH = settings.BASE_DIR / 'DL' / 'geodata'


# --- 2. LEVEL DEFINITIONS (Your "Library") ---
LEVEL_DEFINITIONS = {
    'province': {
        'level_name': 'Province',
        'name_field': 'PRNOM',
        'code_field': 'PRIDU',
        'parent_code_field': None,
    },
    'cd': {
        'level_name': 'Census Division (CD)',
        'name_field': 'DRNOM',
        'code_field': 'DRIDU',
        'parent_code_field': 'PRIDU',
    },
    'csd': {
        'level_name': 'Census Subdivision (CSD)',
        'name_field': 'CSDNAME',
        'code_field': 'CSDIDU',
        'parent_code_field': 'DRIDU',
    },
    'fed': {
        'level_name': 'Federal Riding (FED)',
        'name_field': 'CÉFNOM',
        'code_field': 'CÉFIDU',
        'parent_code_field': 'PRIDU',
    },
    'fsa': {
        'level_name': 'Forward Sortation Area (FSA)',
        'name_field': 'CFSAUID', # From address/management/commands/seed_fsas.py
        'code_field': 'CFSAUID', # From address/management/commands/seed_fsas.py
        'parent_code_field': 'PRIDU', # Links to province
    },
}


# --- 3. TREE COMPOSITIONS ---
TREE_COMPOSITIONS = {
    'statistical': [
        'province',
        'cd',
        'csd',
    ],
    'electoral': [
        'province',
        'fed',
    ],
    'postal': [
        'province',
        'fsa',
    ]
}