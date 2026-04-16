# DEPRECATED: This ad-hoc script is no longer needed.
#
# Geocoding is handled by the pipeline:
#   1. engines/rt/parcel_resolver/geocode.py  (Mapbox geocoding)
#   2. engines/rt/compile.py                  (carries geocoded_coords into clean records)
#   3. cleo/compiler/writer.py                (uses geocoded_coords as fallback when no parcel centroid)
#
# To geocode new properties, run the pipeline stages in order:
#   python -m engines.rt.parcel_resolver.geocode --preflight
#   python -m engines.rt.parcel_resolver.geocode --run
#   python engines/rt/compile.py
#   python -m cleo.compiler
