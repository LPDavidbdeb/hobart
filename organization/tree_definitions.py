# In organization/tree_definitions.py

from django.conf import settings
from organization.models import NestedTerritory # Import the model to use the enum

BASE_GEODATA_PATH = settings.BASE_DIR / 'DL' / 'geodata'

# LEVEL_DEFINITIONS is UNCHANGED from your file.
LEVEL_DEFINITIONS = {
    'province': {
        'log_name': 'Province',
        'territory_type': NestedTerritory.TerritoryType.PROVINCE,
        'name_field': 'PRNOM',
        'code_field': 'PRIDU',
        'parent_code_field': None,
        'parent_type': None,
    },
    'cd': {
        'log_name': 'Census Division (CD)',
        'territory_type': NestedTerritory.TerritoryType.REGION,
        'name_field': 'DRNOM',
        'code_field': 'DRIDU',
        'parent_code_field': 'PRIDU',
        'parent_type': NestedTerritory.TerritoryType.PROVINCE,
    },
    'csd': {
        'log_name': 'Census Subdivision (CSD)',
        'territory_type': NestedTerritory.TerritoryType.CITY,
        'name_field': 'SDRNOM',
        'code_field': 'SDRIDU',
        'parent_code_field': 'PRIDU', # <-- This is loaded "wrong" (flat), which is correct for now
        'parent_type': NestedTerritory.TerritoryType.PROVINCE,
    },
    'fed': {
        'log_name': 'Federal Riding (FED)',
        'territory_type': NestedTerritory.TerritoryType.REGION,
        'name_field': 'CÉFNOM',
        'code_field': 'CÉFIDU',
        'parent_code_field': 'PRIDU',
        'parent_type': NestedTerritory.TerritoryType.PROVINCE,
    },
    'fsa': {
        'log_name': 'Forward Sortation Area (FSA)',
        'territory_type': NestedTerritory.TerritoryType.FSA,
        'name_field': 'RTACIDU',
        'code_field': 'RTACIDU',
        'parent_code_field': 'PRIDU',
        'parent_type': NestedTerritory.TerritoryType.PROVINCE,
    },
}

# --- THIS IS THE CORRECTED SECTION ---
# We define the three trees we want to build.
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