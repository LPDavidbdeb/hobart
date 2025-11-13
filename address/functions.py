from django.contrib.gis.db import models as gis_models
from django.contrib.gis.db.models.functions import GeoFunc

class SimplifyPreserveTopology(GeoFunc):
    """
    A custom database function wrapper for PostGIS's ST_SimplifyPreserveTopology.
    This is safer than ST_Simplify as it prevents the creation of invalid geometries.
    """
    function = 'ST_SimplifyPreserveTopology'
    # This tells Django that the function returns a geometry field.
    output_field = gis_models.MultiPolygonField()
