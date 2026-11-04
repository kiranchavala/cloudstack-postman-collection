import json, sys, yaml

src, dst = sys.argv[1], sys.argv[2]
doc = yaml.safe_load(open(src))

doc["openapi"] = "3.0.3"
doc.pop("$self", None)
doc.pop("jsonSchemaDialect", None)

# 3.2 tag fields (summary/parent/kind) -> drop
for t in doc.get("tags", []):
    for k in ("summary", "parent", "kind"):
        t.pop(k, None)

def fix(node):
    if isinstance(node, dict):
        if "const" in node:                     # 3.1+ only
            node["enum"] = [node.pop("const")]
        t = node.get("type")
        if isinstance(t, list):                 # ["string","null"] -> 3.0 style
            non_null = [x for x in t if x != "null"]
            node["type"] = non_null[0] if non_null else "string"
            if "null" in t:
                node["nullable"] = True
        for k in ("$schema", "$id", "examples"):
            node.pop(k, None)
        for v in node.values():
            fix(v)
    elif isinstance(node, list):
        for v in node:
            fix(v)

fix(doc)
json.dump(doc, open(dst, "w"), indent=1)
print("wrote", dst)
