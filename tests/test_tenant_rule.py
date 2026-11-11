"""The core security rule: pharmacy_id never comes from the client.

These tests read the whole API description (OpenAPI), so they keep
checking every new endpoint added in later slices too.
"""

from app.main import app


def _schema_property_names(schema: dict, components: dict, seen: set[str]) -> set[str]:
    names: set[str] = set()
    if "$ref" in schema:
        ref = schema["$ref"].rsplit("/", 1)[-1]
        if ref in seen:
            return names
        seen.add(ref)
        return _schema_property_names(components[ref], components, seen)
    for name, sub in schema.get("properties", {}).items():
        names.add(name)
        names |= _schema_property_names(sub, components, seen)
    for key in ("allOf", "anyOf", "oneOf"):
        for sub in schema.get(key, []):
            names |= _schema_property_names(sub, components, seen)
    if "items" in schema:
        names |= _schema_property_names(schema["items"], components, seen)
    return names


def test_no_endpoint_accepts_pharmacy_id_from_the_client():
    spec = app.openapi()
    components = spec.get("components", {}).get("schemas", {})

    for path, operations in spec["paths"].items():
        assert "pharmacy" not in path.lower(), f"{path} takes a pharmacy in the URL"
        for method, operation in operations.items():
            for parameter in operation.get("parameters", []):
                assert "pharmacy" not in parameter["name"].lower(), f"{method.upper()} {path}: {parameter['name']}"
            for content in operation.get("requestBody", {}).get("content", {}).values():
                fields = _schema_property_names(content["schema"], components, set())
                assert "pharmacy_id" not in fields, f"{method.upper()} {path} accepts pharmacy_id in its body"


def test_request_bodies_reject_unknown_fields():
    # Unknown fields are a 422, so a pharmacy_id sent anyway is refused, not silently ignored
    spec = app.openapi()
    components = spec["components"]["schemas"]

    for path, operations in spec["paths"].items():
        for method, operation in operations.items():
            for content in operation.get("requestBody", {}).get("content", {}).values():
                ref = content["schema"]["$ref"].rsplit("/", 1)[-1]
                assert components[ref].get("additionalProperties") is False, f"{method.upper()} {path} ({ref})"
