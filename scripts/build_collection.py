"""Convert the OpenAPI 3.0 spec into a Postman v2.1 collection and inject
CloudStack request signing (collection pre-request script + variables).

Usage:
  npx openapi2postmanv2 -s openapi/cloudstack-openapi-3.0.json -o /tmp/raw.json \
      -O folderStrategy=Tags,requestParametersResolution=Schema,enableOptionalParameters=false
  python3 scripts/build_collection.py /tmp/raw.json postman/cloudstack.postman_collection.json
"""
import json, sys, pathlib

src, dst = sys.argv[1], sys.argv[2]
here = pathlib.Path(__file__).parent
col = json.load(open(src))

col["info"]["name"] = "Apache CloudStack API"
col["auth"] = {"type": "noauth"}
col["variable"] = [
    {"key": "baseUrl", "value": "http://localhost:8080/client/api", "type": "string"},
    {"key": "apiKey", "value": "", "type": "string"},
    {"key": "secretKey", "value": "", "type": "secret"},
]
col["event"] = [{
    "listen": "prerequest",
    "script": {"type": "text/javascript",
               "exec": (here / "pre-request.js").read_text().splitlines()},
}]

DROP = {"apiKey", "apikey", "signature", "sessionkey"}

def walk(items):
    for it in items:
        if "item" in it:
            walk(it["item"])
            continue
        req = it["request"]
        req.pop("auth", None)
        url = req["url"]
        url["query"] = [q for q in url.get("query", []) if q.get("key") not in DROP]
        # 'command' is derived from the path segment by the pre-request script
        url["query"] = [q for q in url["query"] if q.get("key") != "command"]
        it.pop("response", None)   # drop example responses to keep file small

walk(col["item"])
json.dump(col, open(dst, "w"), indent=1)
print("wrote", dst)
