"""Validate only the JSON Schema keywords used by this contract (stdlib).
Not a general OpenAPI validator or an HTTP integration test.
Run: python validate_contract.py
"""
import json
from pathlib import Path
from datetime import datetime, date
from urllib.parse import urlparse
from uuid import UUID
import runpy

ROOT = Path(__file__).resolve().parent
spec = json.loads((ROOT / "openapi.json").read_text(encoding="utf-8"))
index = json.loads((ROOT / "example-index.json").read_text(encoding="utf-8"))
schemas = spec["components"]["schemas"]

def resolve(pointer):
    node = spec
    for part in pointer.removeprefix("#/").split("/"):
        node = node[part.replace("~1", "/").replace("~0", "~")]
    return node

def check(value, schema, path="$"):
    if "$ref" in schema:
        return check(value, resolve(schema["$ref"]), path)
    for key in ("anyOf", "oneOf"):
        if key in schema:
            matches = 0
            for choice in schema[key]:
                try:
                    check(value, choice, path)
                    matches += 1
                except (AssertionError, ValueError, TypeError):
                    pass
            assert matches >= 1 if key == "anyOf" else matches == 1, (path, key, matches)
            return
    kind = schema.get("type")
    valid = {
        "null": value is None,
        "object": isinstance(value, dict),
        "array": isinstance(value, list),
        "string": isinstance(value, str),
        "boolean": isinstance(value, bool),
        "integer": isinstance(value, int) and not isinstance(value, bool),
        "number": isinstance(value, (int, float)) and not isinstance(value, bool),
    }
    if kind:
        assert valid[kind], (path, "type", kind)
    if "enum" in schema:
        assert value in schema["enum"], (path, "enum")
    if kind == "object":
        assert set(schema.get("required", [])) <= value.keys(), (path, "required")
        if schema.get("additionalProperties") is False:
            assert value.keys() <= schema.get("properties", {}).keys(), (path, "extra fields")
        for key, child in value.items():
            if key in schema.get("properties", {}):
                check(child, schema["properties"][key], path + "." + key)
    if kind == "array":
        assert len(value) >= schema.get("minItems", 0), (path, "minItems")
        assert len(value) <= schema.get("maxItems", float("inf")), (path, "maxItems")
        if schema.get("uniqueItems"):
            assert len({json.dumps(v, sort_keys=True) for v in value}) == len(value), (path, "unique")
        for i, child in enumerate(value):
            check(child, schema["items"], f"{path}[{i}]")
    if kind == "string":
        assert len(value) >= schema.get("minLength", 0), (path, "minLength")
        assert len(value) <= schema.get("maxLength", float("inf")), (path, "maxLength")
        fmt = schema.get("format")
        if fmt == "uuid":
            UUID(value)
        elif fmt == "date-time":
            assert datetime.fromisoformat(value).utcoffset() is not None, (path, "timezone")
        elif fmt == "date":
            date.fromisoformat(value)
        elif fmt == "uri":
            parsed = urlparse(value)
            assert parsed.scheme and parsed.netloc, (path, "uri")
    if kind in ("integer", "number"):
        assert value >= schema.get("minimum", -float("inf")), (path, "minimum")
        assert value <= schema.get("maximum", float("inf")), (path, "maximum")

def walk(node):
    if isinstance(node, dict):
        if "$ref" in node:
            resolve(node["$ref"])
        for child in node.values():
            walk(child)
    elif isinstance(node, list):
        for child in node:
            walk(child)

walk(spec)
for schema in schemas.values():
    walk(schema)
for filename, name in index.items():
    value = json.loads((ROOT / filename).read_text(encoding="utf-8"))
    check(value, schemas[name], filename)
    if "profile" in value:
        for field in value["profile"].values():
            if isinstance(field, dict) and "source" in field:
                assert (field["value"] is None) == (field["source"] == "UNSET")
    if value.get("status") == "READY":
        assert value["questions"] == []
    if value.get("status") == "NEEDS_INPUT":
        assert 1 <= len(value["questions"]) <= 2

for path, methods in spec["paths"].items():
    for method, operation in methods.items():
        containers = list(operation["responses"].values())
        if "requestBody" in operation:
            containers.append(operation["requestBody"])
        for container in containers:
            for content in container.get("content", {}).values():
                for example in content.get("examples", {}).values():
                    check(example["value"], content["schema"], path + "." + method)

response = json.loads((ROOT / "examples/04-course.success.response.json").read_text(encoding="utf-8"))
course = response["course"]
items, legs = course["items"], course["legs"]
assert len(legs) == len(items) - 1
assert [i["order"] for i in items] == list(range(1, len(items) + 1))
assert len({i["id"] for i in items}) == len(items)
sources = {s["id"] for s in course["sources"]}
assert len(sources) == len(course["sources"])
parse = datetime.fromisoformat
wait = 0
for i, item in enumerate(items):
    assert set(item["place"]["sourceIds"]) <= sources
    assert all(e["sourceId"] in sources for e in item["place"]["accessibility"]["evidence"])
    assert (parse(item["endAt"]) - parse(item["startAt"])).total_seconds() / 60 == item["stayMinutes"]
    if i:
        leg = legs[i - 1]
        assert leg["fromItemId"] == items[i - 1]["id"] and leg["toItemId"] == item["id"]
        gap = (parse(item["startAt"]) - parse(items[i - 1]["endAt"])).total_seconds() / 60
        assert gap >= leg["minutes"]
        wait += gap - leg["minutes"]
summary = course["summary"]
assert summary["totalStayMinutes"] == sum(i["stayMinutes"] for i in items)
assert summary["totalTravelMinutes"] == sum(l["minutes"] for l in legs)
assert summary["totalWaitingMinutes"] == wait
assert summary["totalMinutes"] == summary["totalStayMinutes"] + summary["totalTravelMinutes"] + wait
assert summary["totalMinutes"] == (parse(course["endAt"]) - parse(course["startAt"])).total_seconds() / 60
assert course["startAt"] == items[0]["startAt"] and course["endAt"] == items[-1]["endAt"]
assert parse(course["availableWindow"]["startAt"]) <= parse(course["startAt"]) < parse(course["endAt"]) <= parse(course["availableWindow"]["endAt"])
assert not set(course["validation"]["checkedHardConstraints"]) & set(course["validation"]["unverifiedFields"])

# Negative controls prove common shape mistakes are rejected.
for invalid, schema in [
    ({"sessionId": "not-a-uuid", "profileRevision": 1}, schemas["CourseRequest"]),
    ({"sessionId": "11111111-1111-4111-8111-111111111111", "profileRevision": -1}, schemas["CourseRequest"]),
    ({}, schemas["ChatRequest"]),
]:
    try:
        check(invalid, schema)
    except (AssertionError, ValueError, TypeError):
        continue
    raise AssertionError("Negative control unexpectedly accepted")
operations = sum(len(v) for v in spec["paths"].values())
policy_cases = json.loads((ROOT / 'policy-cases.json').read_text(encoding='utf-8'))
runpy.run_path(str(ROOT / 'policy_contract.py'))['validate_cases'](policy_cases, spec, check)
print(f"PASS: {operations} operations, {len(schemas)} schemas, {len(index)} JSON examples; references, embedded examples, timeline, source links, negative controls.")
print(f"PASS: {len(policy_cases['cases'])} synthetic policy cases (DEC-019~021), including negative controls; no HTTP calls.")
