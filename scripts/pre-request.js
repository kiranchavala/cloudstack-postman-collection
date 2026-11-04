// ---- CloudStack request signing (HmacSHA1) ----
// Collection-level pre-request script. Signs every request with the
// apiKey / secretKey collection variables.
const apiKey = pm.collectionVariables.get("apiKey");
const secret = pm.collectionVariables.get("secretKey");
const url = pm.request.url;

// 1. Command comes from the synthetic path segment (/listVirtualMachines)
const last = url.path[url.path.length - 1];
let command = null;
if (last && last !== "api") command = url.path.pop();

// 2. Collect ticked params, skipping importer placeholders
const SKIP = new Set(["apikey", "apiKey", "signature", "sessionkey", "response"]);
const PLACEHOLDERS = new Set(["", "string", "string,string",
  "a809251f-f681-a262-522b-b1adaf659ed9", "7013"]);
const isPlaceholder = v => PLACEHOLDERS.has(v) || /^<[^>]*>$/.test(v);

const params = {};
url.query.each(q => {
  if (q.disabled || !q.key || SKIP.has(q.key)) return;
  if (/^key_\d+$/.test(q.key)) return;
  const v = pm.variables.replaceIn(q.value ?? "");
  if (isPlaceholder(v)) return;
  params[q.key] = v;
});
if (command) params.command = command;
params.response = "json";
params.apikey = apiKey;

// 3. URL-encode values (spaces as %20), sort by key, join
const enc = v => encodeURIComponent(v)
  .replace(/[!'()]/g, c => "%" + c.charCodeAt(0).toString(16).toUpperCase());
const keys = Object.keys(params).sort();
const query = keys.map(k => `${k}=${enc(params[k])}`).join("&");

// 4. Lowercase the whole string and HMAC-SHA1 it with the secret key
const hash = CryptoJS.HmacSHA1(query.toLowerCase(), secret);

// 5. Base64-encode, then URL-encode, and append as signature
const signature = CryptoJS.enc.Base64.stringify(hash);

url.query.clear();
keys.forEach(k => url.query.add({ key: k, value: enc(params[k]) }));
url.query.add({ key: "signature", value: encodeURIComponent(signature) });

console.log("String to sign:", query.toLowerCase());
console.log("Signature:", signature);
