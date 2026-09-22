---
sidebar_position: 1
title: Client & configuration
---
import Tabs from '@theme/Tabs';
import TabItem from '@theme/TabItem';

# Client & configuration

The client is the entry point: it owns a shared HTTP connection and token handling and
exposes one accessor per service. It is safe to share: **create one and reuse it** for
the lifetime of your application.

<Tabs groupId="lang">
<TabItem value="java" label="Java">

```java
import ai.intellistream.datahub.sdk.client.DatahubClient;
import ai.intellistream.datahub.sdk.client.DatahubConfig;

// from the environment (and a .env file, if present)
DatahubClient client = DatahubClient.fromEnv();

// or explicitly
DatahubClient client = DatahubClient.create(DatahubConfig.builder()
        .baseUrl("https://api.intellistream.ai")
        .token(System.getenv("TOKEN"))
        .build());
```

</TabItem>
<TabItem value="python" label="Python">

```python
from intellistream_datahub_sdk import DataHubClient

# from the environment (or an explicit .env file)
client = DataHubClient.from_env()
client = DataHubClient.from_envfile("/path/to/.env")

# or explicitly
client = DataHubClient(base_url="https://api.intellistream.ai", token="...")
```

For `async`/`await`, use `AsyncDataHubClient` instead, same methods, awaited (one is spelled
differently, see [Units](./units#client-coverage)):

```python
from intellistream_datahub_sdk import AsyncDataHubClient
client = AsyncDataHubClient.from_env()
```

</TabItem>
<TabItem value="rust" label="Rust">

```rust
use intellistream_datahub_sdk::create_api_service;

// from the environment (and a .env file, if present)
let api = create_api_service();
```

Every method is `async`, so call them from an async runtime (e.g. `#[tokio::main]`) and
`.await` the result.

Don't want async? Enable the `blocking` cargo feature and use
`intellistream_datahub_sdk::blocking` instead, the same calls without `.await`, driven by the
SDK's own runtime (the `reqwest` / `reqwest::blocking` split):

```rust
use intellistream_datahub_sdk::blocking;

let api = blocking::create_api_service();
```

The blocking client covers most of the async one, not all of it. It has no `subscriptions`, and
it lacks `time_series.filter`, `resources.filter`, `resources.get_by_id`,
`resources.fetch_nearest`, `events.get`, `events.update` and `events.count`. `api.async_api()`
hands you the async service for those.

</TabItem>
</Tabs>

## Services

| Service | Java | Python | Rust |
| --- | --- | --- | --- |
| Resources | `client.resources()` | `client.resources` | `api.resources` |
| Time series | `client.timeseries()` | `client.timeseries` | `api.time_series` |
| Datasets | `client.datasets()` | `client.datasets` | `api.datasets` |
| Events | `client.events()` | `client.events` | `api.events` |
| Units | `client.units()` | `client.units` | `api.units` |
| Files | `client.files()` | `client.files` | `api.files` |
| Subscriptions | `client.subscriptions()` | `client.subscriptions` | `api.subscriptions` |
| Edges | `client.edges()` | `client.edges` | `api.edges` |

The Java client adds six more services:

| Service | Java | Covers |
| --- | --- | --- |
| [Assets](./resources#assets) | `client.assets()` | `/assets`, the `ASSET`-labelled resources, typed |
| [Functions](./resources#functions) | `client.functions()` | `/functions`, the `FUNCTION`-labelled resources, typed |
| [Labels](./labels) | `client.labels()` | `/labels`, the tenant's label vocabulary |
| [Policies](./policies) | `client.policies()` | `/policies`, including the naming dry-run |
| [Governance templates](./policies#governance-templates) | `client.governance()` | `/governance/templates` |
| [Tenant](./tenant) | `client.tenant()` | `/tenant/features` and `/tenant/settings` |

:::note Two endpoints no client wraps, on purpose
`GET /stats` is internal to the console and marked hidden: it is not part of the published
contract, so nothing should call it. The browser datapoint tail
`/timeseries/datapoints/listen` authenticates with a `?token=` query parameter, which is for a
page that cannot set a header. Server-side code wants the durable equivalent instead,
[`subscriptions().listen`](./subscriptions#live-delivery), which authenticates the upgrade with
the usual `Authorization` header and survives a reconnect.
:::

## Authentication

All three clients read the same configuration: a base URL plus **either** a static
bearer token **or** OAuth2 client-credentials (the SDK fetches and refreshes the token).

| Variable | Meaning |
| --- | --- |
| `BASE_URL` | API base URL (required) |
| `TOKEN` | Static bearer token |
| `CLIENT_ID` / `CLIENT_SECRET` / `TOKEN_URI` | OAuth2 client-credentials (all three) |
| `PROJECT_NAME` | Optional. Every client accepts it (`.projectName(...)`, `project_name=`), but no request uses it |

Java's `fromEnv()` and Rust's `create_api_service()` read these from the environment, falling
back to a `.env` file in the working directory (real environment variables win). Python's
`from_env()` and Rust's `DataHubConfig::from_env()` read the process environment only. To load a
file there, use `from_envfile(path)` (Python) or `DataHubConfig::from_envfile(Some(path))`
(Rust), where real environment variables also win. Rust and Python read
`DATAPOINT_INSERT_PARALLELISM` from the same place, see
[what the SDKs do about limits](./limits#sdk-behaviour).

### Provider-specific parameters

Every client asks for `openid` in every token request to `TOKEN_URI`, and `scope` **adds** to
it rather than replacing it: `SCOPE=organization:*` asks for `openid organization:*`. The API
reads your dataset grants from the identity provider's UserInfo endpoint, which refuses a token
without `openid`. `audience` is left out unless you set it.

What DataHub needs is a token carrying the `organization` claim naming exactly one
organization (tenant routing and [dataset grants](/reference/datasets#access-control) ride on
it); whether that takes a scope depends on how your realm issues the claim. A realm using a
client protocol mapper (the common production setup) puts it on every token, so leave `SCOPE`
unset. A realm using Keycloak Organizations only issues it when the request names
`organization:*` or `organization:<alias>`. When the claim is missing, every call fails
`401 invalid_token`, which looks like a credentials problem but is not.

When the claim is present but names an organization this deployment holds no tenant for
(never onboarded, or since removed), every call fails **`403`** with an
`application/problem+json` body of `type: ".../errors/unknown-tenant"` naming the refused
`organizationId`. Retrying never helps: an administrator has to register the organization.

| Variable | Java builder | Python kwarg | Rust setter | When you need it |
| --- | --- | --- | --- | --- |
| `SCOPE` | `.scope(...)` | `scope=` | `set_scope(...)` | `organization:*` if your realm issues the organization claim through Keycloak Organizations (see above). Space-separate several. Entra ID's `api://<app-id-uri>/.default` does not go here: Entra rejects it next to `openid`, so it belongs in [`ASSERTION_SCOPE`](#exchanging-an-external-token-jwt-bearer). |
| `AUDIENCE` | `.audience(...)` | `audience=` | `set_audience(...)` | Auth0 requires it. Keycloak ignores it. |

### When a call returns 401

`401 invalid_token` has two causes, and they need different fixes.

| Cause | What you see | Fix |
| --- | --- | --- |
| The token carries no `organization` claim | Every call fails, from the first one | Set `SCOPE` (see above) |
| The identity provider refused the token | Calls succeed, then start failing part-way through a run | Get a new token |

The second one catches long-running processes. The API checks your token locally (signature,
expiry, issuer) and separately reads your data set grants from the identity provider's UserInfo
endpoint. A token can pass the first check and still be refused by the second: it is unexpired,
but the session behind it has ended, because an idle or maximum session lifetime elapsed or
somebody signed out. The response carries `WWW-Authenticate: Bearer error="invalid_token"` and a
problem+json body with `type: ".../errors/token-rejected"`.

Retrying does not clear that. Only a new token does.

:::note Not the same as 503
`503` with `type: ".../errors/permissions-unavailable"` means the API could not reach the identity
provider to check your grants. That one is temporary, and worth retrying.
:::

### Exchanging an external token (jwt-bearer)

A token minted by one issuer is not accepted by an API that trusts another. To bridge them, the
SDK can present an externally-issued JWT as an [RFC 7523](https://www.rfc-editor.org/rfc/rfc7523)
`assertion` and exchange it for a token the API *does* accept. The common case is reaching a
Keycloak-backed API with an **Entra ID service principal**:

```
1. client_credentials          2. jwt-bearer                 3. Bearer
   ────────────────►              ────────────────►             ────────────────►
   Entra token endpoint           Keycloak token endpoint       DataHub API
   → the assertion                → the token you use
```

With `CLIENT_SECRET` set, an assertion source switches the request at `TOKEN_URI` from
client-credentials to `jwt-bearer`. `CLIENT_ID`/`CLIENT_SECRET`/`TOKEN_URI` then describe the
client performing the *exchange*, and the `ASSERTION_*` keys describe where the assertion comes
from:

| Variable | Java builder | Python kwarg | Rust setter | Meaning |
| --- | --- | --- | --- | --- |
| `ASSERTION` | `.assertion(...)` | `assertion=` | `set_assertion(...)` | A ready-made JWT. Never refreshed, prefer the credentials below. |
| `ASSERTION_CLIENT_ID` / `ASSERTION_CLIENT_SECRET` / `ASSERTION_TOKEN_URI` | `.assertionCredentials(...)` | `assertion_client_id=` / `assertion_client_secret=` / `assertion_token_url=` | `set_assertion_credentials(...)` | Fetch the assertion with client credentials from another provider (all three). |
| `ASSERTION_SCOPE` | `.assertionScope(...)` | `assertion_scope=` | `set_assertion_scope(...)` | `scope` for the assertion request, sent as given with no `openid` added. Entra ID requires `api://<app-id-uri>/.default`. |
| `ASSERTION_AUDIENCE` | `.assertionAudience(...)` | `assertion_audience=` | `set_assertion_audience(...)` | `audience` for the assertion request. |
| `ASSERTION_GRANT` | — | `assertion_grant=` | `set_assertion_grant(...)` | Without `CLIENT_SECRET` only: `client_credentials` (default) or `jwt-bearer`. |

Rust and Python can also do the exchange without `CLIENT_SECRET`. The assertion then
authenticates the client itself, sent as the RFC 7523 `client_assertion` (Keycloak's *Signed
JWT - Federated* client authenticator), and no `client_id` is sent. `ASSERTION_GRANT` picks the
grant in that mode: `client_credentials` (the default) gets a token for the client's service
account, `jwt-bearer` one for the user linked to the assertion's subject. It needs Keycloak 26.6
or later, with the `federated-jwt` execution in the realm's client authentication flow. Java
always needs `CLIENT_SECRET` for the exchange.

:::note Python names the URL parameters `*_url`
The Python client already spells `TOKEN_URI` as `token_url`, so the assertion equivalent is
`assertion_token_url`. The environment variables keep the `_URI` spelling in all three SDKs.
:::

<Tabs groupId="lang">
<TabItem value="java" label="Java">

```java
DatahubClient client = DatahubClient.create(DatahubConfig.builder()
        .baseUrl("https://api.intellistream.ai")
        // leg 2 — the confidential Keycloak client that performs the exchange
        .clientCredentials("datahub-jwt-grant", keycloakSecret,
                "https://keycloak.example.com/realms/datahub/protocol/openid-connect/token")
        // leg 1 — the Entra app registration the assertion comes from
        .assertionCredentials(entraAppId, entraSecret,
                "https://login.microsoftonline.com/" + tenantId + "/oauth2/v2.0/token")
        .assertionScope("api://" + entraAppId + "/.default")
        .build());
```

</TabItem>
<TabItem value="python" label="Python">

```python
client = DataHubClient(
    "https://api.intellistream.ai",
    # leg 2 — the confidential Keycloak client that performs the exchange
    client_id="datahub-jwt-grant",
    client_secret=keycloak_secret,
    token_url="https://keycloak.example.com/realms/datahub/protocol/openid-connect/token",
    # leg 1 — the Entra app registration the assertion comes from
    assertion_client_id=entra_app_id,
    assertion_client_secret=entra_secret,
    assertion_token_url=f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token",
    assertion_scope=f"api://{entra_app_id}/.default",
)
```

</TabItem>
<TabItem value="rust" label="Rust">

```rust
use intellistream_datahub_sdk::{ApiService, datahub::DataHubConfig};

// leg 2 — BASE_URL and the Keycloak client (CLIENT_ID, CLIENT_SECRET, TOKEN_URI) from the env
let mut config = DataHubConfig::from_env()?;
// leg 1 — the Entra app registration the assertion comes from
config.set_assertion_credentials(
    &entra_app_id,
    &entra_secret,
    &format!("https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"),
);
config.set_assertion_scope(format!("api://{entra_app_id}/.default"));
let api = ApiService::new(config);
```

</TabItem>
</Tabs>

Or entirely from the environment:

```bash
BASE_URL=https://api.intellistream.ai
CLIENT_ID=datahub-jwt-grant
CLIENT_SECRET=...
TOKEN_URI=https://keycloak.example.com/realms/datahub/protocol/openid-connect/token
ASSERTION_CLIENT_ID=<entra-application-id>
ASSERTION_CLIENT_SECRET=...
ASSERTION_TOKEN_URI=https://login.microsoftonline.com/<tenant-id>/oauth2/v2.0/token
ASSERTION_SCOPE=api://<entra-application-id>/.default
```

The exchanged token is cached and refreshed exactly like a client-credentials one. The assertion
itself is **never** cached, providers commonly reject a replayed assertion, so every exchange
starts from a fresh request.

:::caution Server-side setup is required
The identity provider must be configured to trust the external issuer, and the external identity
must map to a real user on that side. For Keycloak that means an Identity Provider with **JWT
Authorization Grant** enabled (Keycloak 26.5+), a client with the matching capability, and a
linked user carrying the roles and tenant claim. See
[`EntraID.md`](https://github.com/IntelliStream-DataHub/datahub-platform/blob/master/EntraID.md)
in the platform repository for the full walkthrough, including the audience and
assertion-lifetime settings that trip up a first attempt.
:::

### From HashiCorp Vault (Java)

The Java client can also read the same keys from a Vault KV v2 secret, with a token or
with AppRole:

```java
DatahubConfig cfg = DatahubConfig.fromVault(vaultAddr, vaultToken, "datahub/sdk");
DatahubConfig cfg = DatahubConfig.fromVaultEnv("datahub/sdk");                 // VAULT_ADDR + VAULT_TOKEN
DatahubConfig cfg = DatahubConfig.fromVaultAppRole(vaultAddr, roleId, secretId, "datahub/sdk");
DatahubConfig cfg = DatahubConfig.fromVaultAppRoleEnv("datahub/sdk");          // VAULT_ADDR + VAULT_ROLE_ID + VAULT_SECRET_ID
```

## Durable ingest buffering

Optional and **off by default**. When enabled, datapoint and event ingestion that can't reach the
API, or is rejected with an auth failure (HTTP 401/403, e.g. an expired or rotated token), spools
to disk and is flushed automatically on the next ingest call. Neither a transient outage nor a
credential hiccup loses data or raises. The buffer is a segmented, compressed log (gzip in Java,
zstd in Rust/Python) bounded on two axes, either of which may be left unset; an unset axis defaults
to **72 hours** / **5 GiB** once buffering is on:

- **time**: datapoints/events older than the window are dropped.
- **size**: when the on-disk spool exceeds the cap, the oldest segment is dropped.

It is memory-safe: the spool is drained in segments, so even a multi-gigabyte buffer never loads
into memory, and it is recovered from disk on the next start.

<Tabs groupId="lang">
<TabItem value="java" label="Java">

```java
DatahubClient client = DatahubClient.create(DatahubConfig.builder()
        .baseUrl("https://api.intellistream.ai")
        .token(System.getenv("TOKEN"))
        .enableBuffering()                          // 72 h / 5 GiB defaults
        // .bufferRetention(Duration.ofMinutes(60))     // override the time window
        // .bufferMaxBytes(2L * 1024 * 1024 * 1024)      // override the size cap
        // .bufferDirectory(Path.of("datahub-spool"))    // default: .datahub-spool
        .build());

IngestResult r = client.timeseries().ingest(byExternalId);
if (r.buffered() > 0) {
    // server unreachable: r.buffered() datapoints are spooled, retried on the next call
}
```

`fromEnv()` instead reads `BUFFER_RETENTION` (an ISO-8601 duration, e.g. `PT72H`),
`BUFFER_MAX_BYTES` and `BUFFER_DIRECTORY`. Setting either bound turns buffering on.

</TabItem>
<TabItem value="python" label="Python">

```python
client = DataHubClient(
    base_url="https://api.intellistream.ai",
    token="...",
    enable_buffering=True,            # 72 h / 5 GiB defaults
    buffer_retention_secs=3600,       # optional: override the time window
    buffer_max_bytes=2 * 1024**3,     # optional: override the size cap
    buffer_dir="datahub-spool",       # optional, default .datahub-spool
)
```

`from_env()` / `from_envfile(path)` instead read `ENABLE_BUFFERING`, `BUFFER_RETENTION_SECS`,
`BUFFER_MAX_BYTES` and `BUFFER_DIR` from the environment.

</TabItem>
<TabItem value="rust" label="Rust">

```rust
use intellistream_datahub_sdk::{ApiService, datahub::DataHubConfig};

let mut config = DataHubConfig::from_env().unwrap();
config
    .enable_buffering()                            // 72 h / 5 GiB defaults
    .set_buffer_retention_secs(3600)               // optional: override the time window
    .set_buffer_max_bytes(2 * 1024 * 1024 * 1024)  // optional: override the size cap
    .set_buffer_dir("datahub-spool");              // optional, default .datahub-spool
let api = ApiService::new(config);
```

Or via the environment (read by `create_api_service()`): `ENABLE_BUFFERING=true`,
`BUFFER_RETENTION_SECS`, `BUFFER_MAX_BYTES`, `BUFFER_DIR`.

</TabItem>
</Tabs>

:::note Java never spools one `403`
A [lifetime ceiling](./limits#lifetime-ceilings) answers `403` too, and the Java client
**surfaces it rather than buffering it**. The auth failures are worth spooling because a rotated
token or a missing grant is fixed out of band and the data then flushes; a ceiling never becomes
acceptable by being replayed, so spooling it would fill the buffer with data the server
refuses every time. Java matches the problem `type`, so an ordinary permission `403` is
buffered.

Rust and Python do not make that exception: with buffering on they spool every `401` and `403`,
a ceiling included. The call then returns without an error, and the refused data stays in the
spool until the time window or size cap drops it.
:::

:::note Retries are idempotent
A flush re-sends buffered data, which is safe: datapoints are keyed by `(series, timestamp)` and
events by `id`, so the backend collapses duplicates. The SDK stamps each event with a time-ordered
UUID v7 before the first send, so a retried event keeps the same id (see [Events](./events)).
:::

## Results & errors

Most calls return the entity (or a thin wrapper around a list of them); a non-2xx
response surfaces as an exception/error carrying the HTTP status, the raw body, and the
[problem document](#problem-documents) the API explained itself with, when it sent one.

<Tabs groupId="lang">
<TabItem value="java" label="Java">

Methods return `DataWrapper<T>`: `getItems()` holds the results. Non-2xx throws
`DatahubApiException`:

```java
import ai.intellistream.datahub.models.IdCollection;
import ai.intellistream.datahub.sdk.http.DatahubApiException;

try {
    DataWrapper<NodeModel> r = client.resources().byIds(List.of(IdCollection.createFromExternalId("pump_1")));
    r.getItems().forEach(System.out::println);
} catch (DatahubApiException e) {
    System.err.println(e.statusCode() + ": " + e.body());
}
```

</TabItem>
<TabItem value="python" label="Python">

Methods return plain `list[T]`. Non-2xx raises `DataHubException`:

```python
from intellistream_datahub_sdk import DataHubException

try:
    resources = client.resources.by_ids(["pump_1"])
except DataHubException as e:
    print(e.status_code, e.message)
```

</TabItem>
<TabItem value="rust" label="Rust">

Most methods return `Result<DataWrapper<T>, ResponseError>`, where `get_items()` holds the
results. `resources.by_ids`, `create`, `update` and `delete`, and `edges.by_ids`, return a
`GraphDataWrapper` instead, whose `nodes()` holds them. `ResponseError` exposes
`get_status()` and `get_message()` (its `Display` prints both):

```rust
use intellistream_datahub_sdk::generic::IdAndExtId;

match api.resources.by_ids(&vec![IdAndExtId::from_external_id("pump_1")]).await {
    Ok(wrapper) => for node in wrapper.nodes().unwrap_or_default() { println!("{:?}", node); }
    Err(e) => eprintln!("{}: {}", e.get_status(), e.get_message()),
}
```

</TabItem>
</Tabs>

:::note Entity ids are JSON strings on the wire
64-bit ids are serialized as JSON **strings** so they survive JavaScript's 2⁵³ number
limit. Each client reads them back into a native integer, so this only matters if you
inspect raw responses.
:::

### Reading the problem document {#problem-documents}

A refusal the API explains comes back as an
[RFC 9457](https://www.rfc-editor.org/rfc/rfc9457) `application/problem+json` document:
`type`, `title`, `status`, `detail` and `instance`, plus extension members. Every `type` this
API mints sits under `https://intellistream.ai/errors/`, and the **`type` is the contract**.
Branch on it, or on its kebab-case tail (the *slug*), never on `title` or `detail`: those are
prose and may be reworded at any time (RFC 9457 §3.1.1).

<Tabs groupId="lang">
<TabItem value="java" label="Java">

The Java client exposes the raw body only. `DatahubApiException.body()` is the problem document
as it arrived, and there is no typed accessor for its members yet, so read it with your own JSON
parser and match on `type`.

```java
try {
    client.timeseries().create(List.of(series));
} catch (DatahubApiException e) {
    System.err.println(e.statusCode() + ": " + e.body());
}
```

</TabItem>
<TabItem value="python" label="Python">

`DataHubException` carries the whole document as `problem` (a `dict`), its `type` as
`problem_type`, and the slug as `problem_slug`:

```python
from intellistream_datahub_sdk import DataHubException

try:
    client.timeseries.create([ts])
except DataHubException as e:
    if e.problem is None:                       # not a problem document, see the caution below
        print(e.status_code, e.message)
    elif e.problem_slug == "validation-failed":
        for field in e.problem.get("fields", []):
            print(field["field"], field["message"])
    elif e.problem_slug == "unreadable-request-body":
        for offender in e.problem.get("errors", []):
            print(offender["pointer"], "accepts", offender["allowedFields"])
    else:
        print(e.problem_type, e.problem.get("detail"))
```

</TabItem>
<TabItem value="rust" label="Rust">

`ResponseError::problem()` returns `Option<ProblemDetail>`, `problem_slug()` the slug on its own,
and `content_type()` the response media type. `ProblemDetail` holds the standard members as public
fields and reads the extensions through `fields()`, `unknown_fields()`, `duplicated()`,
`blocked_by()`, `retry()`, `request_id()`, `docs()`, `location()` and `pointer()`:

```rust
if let Err(e) = api.time_series.create_one(&series).await {
    match e.problem() {
        // Not a problem document, see the caution below.
        None => eprintln!("{}: {}", e.get_status(), e.get_message()),
        Some(problem) => match problem.slug() {
            Some("validation-failed") => for f in problem.fields() {
                eprintln!("{:?}: {:?}", f.field, f.message);
            }
            Some("unreadable-request-body") => for o in problem.unknown_fields() {
                eprintln!("{:?} accepts {:?}", o.pointer, o.allowed_fields);
            }
            // A document with no `type` still carries a status and prose.
            _ => eprintln!("{:?}: {:?}", problem.status, problem.detail),
        },
    }
}
```

</TabItem>
</Tabs>

Beside the standard members, a problem carries whichever of these the failure has something to
say with. Members a client does not recognise are **kept, not dropped** (RFC 9457 §3.2), so one
the API adds later is readable without a client upgrade.

| Member | Sent with | Holds |
| --- | --- | --- |
| `fields` | Validation failures | One entry per rejected field: `field`, `message`, `code` (the i18n key behind the message, so you can localise rather than parse English) and `rejected` (an argument such as an offending length, never the value you sent) |
| `errors` | [Unknown fields](#unknown-fields) | One entry per unrecognised property: `pointer` to it, and `allowedFields`, the names accepted at that position |
| `duplicated` | A `409` on an identifier already taken | Each collision, as field to value |
| `blockedBy` | A refused delete | What stands in the way, each named by its own ids so you can go and clear it |
| `retry` | Most refusals | `same-request`, `change-request` or `needs-operator` |
| `requestId` | Most refusals | Quote it when you ask an operator about the failure |
| `docs` | Types with a page that explains them | A link to that page. Absent when nothing is written yet |

`retry` is **advisory**. It says whether repeating the request unchanged could ever work, which is
not the same question as what a client should do, and the two part company in one place on
purpose: a `403` is marked `needs-operator`, yet [durable buffering](#durable-ingest-buffering)
still spools `401`/`403`, so a rotated credential does not cost the batch.
[Which failures are worth retrying](#retryable-failures) is the split the ingest paths act on.

:::caution Not every failure is a problem document
Some endpoints still answer in a shape the API has not converged yet: plain text, a Spring
whitelabel body carrying a stack trace, the legacy `{"error": {...}}` wrapper, or a
success-shaped `{"items": [...]}` envelope. Those all arrive labelled `application/json`, so the
`Content-Type` does not separate them and the clients read the body's structure instead.
`problem` is absent for every one of them, and a real problem document may still carry no `type`
(some `404`s), which leaves the slug absent. Write that branch first and keep the status and raw
message as the fallback: it stays load-bearing until the API is done converging.
:::

### Which failures are worth retrying {#retryable-failures}

The API answers a limit it will forgive differently from one it will not, so a client can tell
them apart from the status alone:

| Response | Meaning | Do |
| --- | --- | --- |
| `429` + `Retry-After` | A [rate limit or daily quota](./limits) | Wait the seconds it names and replay |
| `413` | The [request body](./limits#request-body-size) is too large | Split the batch, never retry as-is |
| `403` with `type: ".../errors/tenant-limit-reached"` | A [lifetime ceiling](./limits#lifetime-ceilings) | Nothing to wait for: it is raised by asking |
| `400` / `422` | Validation, including the [field and batch caps](./limits#field-caps) | Fix the request |
| `422` with `type: ".../errors/invalid-timestamp"` or `".../errors/invalid-datapoint"` | A [timestamp](#timestamps) in neither accepted form, or a [datapoint value](./timeseries#write-datapoints) its series' value type cannot parse | Fix the value; `retry` is `change-request` |
| `404` with `type: ".../errors/unknown-timeseries"` or `422` with `type: ".../errors/external-id-mismatch"` | A [binary datapoint request](./binary-datapoints#responses) naming a series that was removed or renamed since you cached it | Re-resolve the ids in `timeseriesIds`, rebuild, send once more; the Java SDK does |

The ingest paths act on that split for you, differently per client. Java's `ingest` retries
`429`, `5xx` and network failures with backoff and surfaces everything else. Rust and Python
retry JSON ingest through the [durable spool](#durable-ingest-buffering): with buffering on,
those failures and a `401` or `403` are written to disk and sent again, oldest first, by the next
ingest call; with it off, they reach you. Their binary path,
`insert_datapoints_binary`, retries `429`, `5xx` and network failures up to three times by
default, 1, 2 and 3 seconds apart, and rebuilds a request refused for a removed or renamed
series once. No client waits the `Retry-After`. [Limits & quotas](./limits#sdk-behaviour) has
the numbers.

### Batch writes are all-or-nothing

Every call that takes a list is validated in full before anything is written, so one bad item
in 500 creates nothing and the error names every offending item rather than the first. Retry
the whole batch once you have fixed them. A [binary datapoint request](./binary-datapoints) is
the same: every frame is validated before any is published. A `validation-failed` problem names
each offender in its `fields` member ([reading it](#problem-documents)).

Two responses are worth recognising by shape:

- **`400` with `type: ".../errors/naming-policy"`**: one or more external ids broke the
  configured [naming policy](./external-ids#the-naming-policy). Nothing was created; the
  `violations` array names each one and suggests a replacement.
- **A `warnings` array beside `items` on a `2xx`**: the write succeeded, and the ids in it
  are in a data steward's queue. The field is absent when empty.

Both shapes, and the rules behind them, are in
[External ids & naming](./external-ids).

### Unknown fields are refused {#unknown-fields}

A request body naming a field the endpoint does not have is a `400`, not a silent success. A
typo, or a field that has since been retired, would otherwise be dropped and answered `200`,
telling you a change was applied when nothing happened. The body is an
[RFC 9457](https://www.rfc-editor.org/rfc/rfc9457) problem document of
`type: ".../errors/unreadable-request-body"`, with one `errors` entry per offender, each
located by a JSON Pointer and listing the names accepted at that position:

```json
{
  "type": "https://intellistream.ai/errors/unreadable-request-body",
  "title": "Bad Request",
  "status": 400,
  "detail": "Unknown field: eventTime",
  "errors": [
    {
      "detail": "Unknown field",
      "pointer": "#/items/0/update/eventTime",
      "allowedFields": ["dataSetId", "description", "externalId", "metadata",
                        "relatedResources", "source", "status", "subType", "type"]
    }
  ]
}
```

Every offender in the body is reported at once, at whatever depth it sits, so several stale
fields cost one round trip rather than one each. A body that cannot be parsed at all,
malformed JSON or a value of the wrong shape, answers with the same `type` and a `detail`
naming the problem, plus `line` and `column` where the parser can say.

The clients only ever send fields they declare, so this reaches you when you build a body by
hand, or keep an old field name in one. How each client hands you the `errors` entries:
[Reading the problem document](#problem-documents).

## Timestamps {#timestamps}

Every timestamp the API accepts reads the same way: `eventTime`, datapoint timestamps, the
`createdTime` / `lastUpdatedTime` / `eventTime` filter bounds, the datapoint delete window,
file metadata dates, the `/analysis` window and the MCP tool parameters. Two forms are
accepted.

| Form | Example | Rules |
| --- | --- | --- |
| Epoch milliseconds, UTC | `1767225600000` | A bare number is always milliseconds, never seconds. 12 to 14 digits, which spans 1973-03-03 to the year 5138. |
| ISO-8601 with an offset | `2026-01-01T00:00:00Z` | `Z`, `+02:00`, `-04:00` and a bracketed region id all work. Fractional seconds and minute precision both parse. |

Two mistakes are refused rather than accepted and misread:

- **Epoch seconds.** Ten digits is exactly the shape of a seconds value, so it falls outside
  the accepted width and is refused, with an error that names the mistake and tells you to
  multiply by 1000. Nothing is scaled for you. A caller that has been sending seconds to
  `POST /events/create` now sees a `422` where the write used to succeed and store a time tens
  of thousands of years out.
- **ISO-8601 without an offset.** `2026-01-01T00:00:00` and a bare date `2026-01-01` are
  refused rather than assumed to be UTC.

For an instant **before 1973-03-03**, use the ISO-8601 form. The numeric form does not reach
back that far.

In the places below, a refused timestamp is answered with a `422` of
`type: ".../errors/invalid-timestamp"` and `retry: change-request`. `detail` is the parser's own
message, naming both accepted forms and the factor of 1000 for seconds. Where it was sent decides
how the offender is located:

| Sent in | Located by | Was |
| --- | --- | --- |
| A JSON body: an event's `eventTime`, a `createdTime` / `lastUpdatedTime` / `eventTime` filter bound, or the `start` / `end` of a [datapoint retrieve](./timeseries#retrieve-datapoints) | `pointer`, a JSON Pointer to the field (`#/eventTime`); no `line` or `column` | `400` of `type: ".../errors/unreadable-request-body"`, with `pointer`, `line` and `column` |
| A bound of the [datapoint delete window](./timeseries#delete-datapoints) | `fields`, naming the bound and the series' `externalId` | `400` with `fields` |
| A datapoint's `timestamp` on `POST /timeseries/data` | `fields`, naming `timestamp` and the series' `externalId` | `500` |
