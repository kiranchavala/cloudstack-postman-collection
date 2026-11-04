# Apache CloudStack Postman Collection

A ready-to-import [Postman](https://www.postman.com/) collection covering the full
Apache CloudStack API (**928 commands, CloudStack 4.23.0.0**), with automatic
request signing (HmacSHA1) built in.

The collection is generated from the server's own `listApis` output via
[`cloudstack-openapi-ngine`](https://pypi.org/project/cloudstack-openapi-ngine/),
so every command, parameter and description matches a real management server.

## Contents

| Path | What it is |
|------|------------|
| `postman/cloudstack.postman_collection.json` | Postman v2.1 collection, grouped by API tag, signing script included |
| `openapi/cloudstack-openapi.yaml` | Original OpenAPI 3.2 spec: open it in Swagger UI as API reference docs |
| `openapi/cloudstack-openapi-3.0.json` | OpenAPI 3.0.3 version, for tools that don't support 3.1+ yet (Postman, Insomnia, …) |
| `scripts/signing_proxy.py` | Local signing proxy so Swagger UI "Try it out" works |
| `docker-compose.yml` | Swagger UI + signing proxy in one command |
| `scripts/pre-request.js` | The collection-level signing script (for reference / reuse) |
| `scripts/openapi_to_3_0.py` | Downgrades the generated OpenAPI 3.1/3.2 spec to 3.0.3 |
| `scripts/build_collection.py` | Turns the converted collection into the final collection |

## Quick start

1. In Postman: **Import → File →** `postman/cloudstack.postman_collection.json`
2. Open the collection → **Variables** and set:
   | Variable | Example |
   |----------|---------|
   | `baseUrl` | `http://<mgmt-server>:8080/client/api` |
   | `apiKey` | your user's API key |
   | `secretKey` | your user's secret key |
3. Open any request (e.g. *VirtualMachine → List the Instances owned by the account*), tick the
   optional params you want, fill in values, and hit **Send**.

You get API keys from the CloudStack UI (**Profile → Generate keys**) or with
`cmk registerUserKeys id=<user-id>`.

### How signing works

The collection's pre-request script runs before every request. It:

1. takes the command name from the last path segment (`{{baseUrl}}/listVirtualMachines`) and
   sends it as `command=`; CloudStack really has just one endpoint,
2. collects the **ticked** query params, skipping unfilled placeholders such as `<string>` and `<uuid>`,
3. adds `apikey` and `response=json`, URL-encodes the values, sorts by key, lowercases the whole string,
4. signs it with HMAC-SHA1 using `secretKey`, then appends the Base64 + URL-encoded `signature`.

The string that was signed and the signature appear in the Postman Console (**View → Show Postman Console**),
which helps with debugging `401 unable to verify user credentials` errors.

> Async commands (`deployVirtualMachine`, …) return a `jobid`. Poll it with
> *queryAsyncJobResult* (`jobid=<id>`).

## Regenerating for your CloudStack version

The collection only contains the APIs your management server exposes. To build one for a different
version, or for a server with extra plugins enabled:

```bash
# 1. Install the generator
brew install uv
uv tool install --python 3.12 'cloudstack-openapi-ngine[live]'

# 2. Credentials (root admin keys give the most complete API list)
cat > ~/.cloudstack.ini <<'INI'
[cloudstack]
endpoint = http://<mgmt-server>:8080/client/api
key = <api-key>
secret = <secret-key>
INI
chmod 600 ~/.cloudstack.ini
cs listCapabilities          # sanity check

# 3. Generate the OpenAPI spec from listApis
mkdir -p /tmp/cs-spec
cloudstack-openapi --probe-response-keys \
  --server-url http://localhost:8080/client/api \
  --dump-listapis /tmp/cs-spec/listapis.json \
  -o /tmp/cs-spec/cloudstack-openapi.yaml

# 4. Downgrade to OpenAPI 3.0.3 (Postman's importer doesn't support 3.1+ yet)
uv run --python 3.12 --with pyyaml scripts/openapi_to_3_0.py \
  /tmp/cs-spec/cloudstack-openapi.yaml openapi/cloudstack-openapi-3.0.json

# 5. Convert to a Postman collection and add signing
npx -y openapi-to-postmanv2@4 -s openapi/cloudstack-openapi-3.0.json -o /tmp/cs-spec/raw.json \
  -O folderStrategy=Tags,requestParametersResolution=Schema,enableOptionalParameters=false
python3 scripts/build_collection.py /tmp/cs-spec/raw.json postman/cloudstack.postman_collection.json
```

## Swagger UI with "Try it out"

`openapi/cloudstack-openapi.yaml` gives you searchable API docs in Swagger UI. A small
**signing proxy** (`scripts/signing_proxy.py`) lets you run requests from Swagger too.
Without the proxy, Swagger can't send requests: CloudStack signatures change on every request,
and the management server sends no CORS headers.

```
Browser (Swagger UI :8088) ──► signing proxy :8081 ──► CloudStack management server
                               adds apikey + HMAC signature
                               adds CORS headers
```

Your secret key stays in the proxy and never reaches the browser.

### Option A: Docker Compose (recommended)

```bash
git clone https://github.com/kiranchavala/cloudstack-postman-collection.git
cd cloudstack-postman-collection
cp .env.example .env        # set CS_ENDPOINT, CS_API_KEY, CS_SECRET_KEY
docker compose up -d
```

1. Open http://localhost:8088
2. Keep the server dropdown on **`http://localhost:8081/client/api` (signing proxy)**
3. Expand any command → **Try it out** → fill in params → **Execute**.
   Leave the **Authorize** button alone; the proxy signs requests for you.

Stop it with `docker compose down`. View proxied calls with `docker compose logs -f signing-proxy`.

### Option B: proxy without Docker

You need Python 3.8+, and nothing else to install. The proxy reads `~/.cloudstack.ini`, the same
file the `cs` CLI uses, or `CS_ENDPOINT` / `CS_API_KEY` / `CS_SECRET_KEY` env vars:

```bash
python3 scripts/signing_proxy.py          # listens on http://127.0.0.1:8081/client/api

docker run --rm -p 8088:8080 \
  -e SWAGGER_JSON=/spec/cloudstack-openapi.yaml \
  -e DOC_EXPANSION=none -e FILTER=true -e SHOW_EXTENSIONS=true \
  -e SUPPORTED_SUBMIT_METHODS='["get"]' \
  -v "$(pwd)/openapi":/spec docker.io/swaggerapi/swagger-ui
```

For an `https` management server with a self-signed certificate, set `CS_VERIFY_TLS=false`.

### Docs only (no keys)

Paste this URL into https://editor.swagger.io (**File → Import URL**):
`https://raw.githubusercontent.com/kiranchavala/cloudstack-postman-collection/main/openapi/cloudstack-openapi.yaml`

`SHOW_EXTENSIONS=true` also shows CloudStack metadata: `x-cloudstack-since` (the version a parameter
was added in) and `x-cloudstack-related` (APIs that return a valid value for it).

> **Security:** the proxy signs *any* request sent to it with your keys, including deletes. It
> binds to `127.0.0.1` only, so don't expose port 8081 on a shared network, and prefer keys for
> a non-admin user where you can.

When regenerating (see above), copy `/tmp/cs-spec/cloudstack-openapi.yaml` into `openapi/`. Then
put back the two `servers:` entries (signing proxy + `{endpoint}`) at the top of the file.

## License

Apache License 2.0. Apache CloudStack is a trademark of the Apache Software Foundation; this
is a community project and is not endorsed by the ASF.
