"""Portable object identity. References neither authenticate nor authorize."""
import unicodedata

FORMAT = 'delvetalk-object-ref-v1'
MAX_COMPONENT = 256


def component(value):
    if (not isinstance(value, str) or not value or len(value) > MAX_COMPONENT
            or any(unicodedata.category(char) in ('Cc', 'Cs') for char in value)):
        raise ValueError('Reference components require 1..256 Unicode scalars without controls')
    # Do not normalize, case-fold, interpret URI syntax, or resolve aliases.
    return value


def object_reference(world_id, object_id):
    return {'format': FORMAT, 'world': component(world_id), 'object': component(object_id)}


def validate_reference(value):
    if (not isinstance(value, dict) or set(value) != {'format', 'world', 'object'}
            or value['format'] != FORMAT):
        raise ValueError('Unknown or malformed object reference')
    return object_reference(value['world'], value['object'])


def local_object(value, world_id):
    reference = validate_reference(value)
    if reference['world'] != component(world_id):
        raise ValueError('Reference belongs to another world; no implicit resolution')
    return reference['object']
