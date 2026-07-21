---
sidebar_position: 1
title: Client & configuration
---
import Tabs from '@theme/Tabs';
import TabItem from '@theme/TabItem';

# Client & configuration

The client is the entry point: it owns a shared HTTP connection and token handling and
exposes one accessor per service. It is safe to share — **create one and reuse it** for
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
from datahub_sdk import DataHubClient

# from the environment (or an explicit .env file)
client = DataHubClient.from_env()
client = DataHubClient.from_envfile("/path/to/.env")

# or explicitly
client = DataHubClient(base_url="https://api.intellistream.ai", token="...")
```

For `async`/`await`, use `AsyncDataHubClient` instead — same methods, awaited:

```python
from datahub_sdk import AsyncDataHubClient
client = AsyncDataHubClient.from_env()
```

</TabItem>
<TabItem value="rust" label="Rust">

```rust
use dataplatform_rust_sdk::create_api_service;

// from the environment (BASE_URL, TOKEN or OAuth creds)
let api = create_api_service();
```

Every method is `async`, so call them from an async runtime (e.g. `#[tokio::main]`) and
`.await` the result.

Don't want async? Enable the `blocking` cargo feature and use
`dataplatform_rust_sdk::blocking` instead — the same services and methods without
`.await`, driven by the SDK's own runtime (the `reqwest` / `reqwest::blocking` split):

```rust
use dataplatform_rust_sdk::blocking;

let api = blocking::create_api_service();
```

</TabItem>
</Tabs>

## Services

| Service | Java | Python | Rust |
| --- | --- | --- | --- |
| Resources | `client.resources()` | `client.resources` | `api.resources` |
| Time-series | `client.timeseries()` | `client.timeseries` | `api.time_series` |
| Datasets | `client.datasets()` | `client.datasets` | `api.datasets` |
| Events | `client.events()` | `client.events` | `api.events` |
| Units | `client.units()` | `client.units` | `api.units` |
| Files | `client.files()` | `client.files` | `api.files` |
| Subscriptions | `client.subscriptions()` | `client.subscriptions` | `api.subscriptions` |

## Authentication

All three clients read the same configuration: a base URL plus **either** a static
bearer token **or** OAuth2 client-credentials (the SDK fetches and refreshes the token).

| Variable | Meaning |
| --- | --- |
| `BASE_URL` | API base URL (required) |
| `TOKEN` | Static bearer token |
| `CLIENT_ID` / `CLIENT_SECRET` / `TOKEN_URI` | OAuth2 client-credentials (all three) |
| `PROJECT_NAME` | Optional project/tenant hint |

`fromEnv()` / `from_env()` / `create_api_service()` read these from the environment,
falling back to a `.env` file in the working directory (real environment variables win).

### Provider-specific parameters

`scope` and `audience` are left out of the token request unless you set them. Keycloak wants
neither; other providers refuse without them.

| Variable | Java builder | Python kwarg | Rust setter | When you need it |
| --- | --- | --- | --- | --- |
| `SCOPE` | `.scope(...)` | `scope=` | `set_scope(...)` | Entra ID requires `api://<app-id-uri>/.default`. Space-separate several. |
| `AUDIENCE` | `.audience(...)` | `audience=` | `set_audience(...)` | Auth0 requires it. Keycloak ignores it. |

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

Setting an assertion source switches the request at `TOKEN_URI` from client-credentials to
`jwt-bearer`. `CLIENT_ID`/`CLIENT_SECRET`/`TOKEN_URI` then describe the client performing the
*exchange*, and the `ASSERTION_*` keys describe where the assertion comes from:

| Variable | Java builder | Python kwarg | Rust setter | Meaning |
| --- | --- | --- | --- | --- |
| `ASSERTION` | `.assertion(...)` | `assertion=` | `set_assertion(...)` | A ready-made JWT. Never refreshed — prefer the credentials below. |
| `ASSERTION_CLIENT_ID` / `ASSERTION_CLIENT_SECRET` / `ASSERTION_TOKEN_URI` | `.assertionCredentials(...)` | `assertion_client_id=` / `assertion_client_secret=` / `assertion_token_url=` | `set_assertion_credentials(...)` | Fetch the assertion with client credentials from another provider (all three). |
| `ASSERTION_SCOPE` | `.assertionScope(...)` | `assertion_scope=` | `set_assertion_scope(...)` | `scope` for the assertion request. |
| `ASSERTION_AUDIENCE` | `.assertionAudience(...)` | `assertion_audience=` | `set_assertion_audience(...)` | `audience` for the assertion request. |

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
let mut api = DataHubApi::from_env()?;
api.set_assertion_credentials(
    &entra_app_id,
    &entra_secret,
    &format!("https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"),
);
api.set_assertion_scope(format!("api://{entra_app_id}/.default"));
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
itself is **never** cached — providers commonly reject a replayed assertion, so every exchange
starts from a fresh request.

:::caution Server-side setup is required
The identity provider must be configured to trust the external issuer, and the external identity
must map to a real user on that side. For Keycloak that means an Identity Provider with **JWT
Authorization Grant** enabled (Keycloak 26.5+), a client with the matching capability, and a
linked user carrying the roles and tenant claim. See `EntraID.md` in the platform repository for
the full walkthrough, including the audience and assertion-lifetime settings that trip up a first
attempt.
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
API — or is rejected with an auth failure (HTTP 401/403, e.g. an expired or rotated token) — spools
to disk and is flushed automatically on the next ingest call, so neither a transient outage nor a
credential hiccup loses data or raises. The buffer is a segmented, compressed log (gzip in Java,
zstd in Rust/Python) bounded on two axes, either of which may be left unset; an unset axis defaults
to **72 hours** / **5 GiB** once buffering is on:

- **time** — datapoints/events older than the window are dropped.
- **size** — when the on-disk spool exceeds the cap, the oldest segment is dropped.

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
`BUFFER_MAX_BYTES` and `BUFFER_DIRECTORY` — setting either bound turns buffering on.

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

`from_env()` / `from_envfile()` instead read `ENABLE_BUFFERING`, `BUFFER_RETENTION_SECS`,
`BUFFER_MAX_BYTES` and `BUFFER_DIR` from the environment.

</TabItem>
<TabItem value="rust" label="Rust">

```rust
use dataplatform_rust_sdk::{ApiService, datahub::DataHubApi};

let mut config = DataHubApi::from_env().unwrap();
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

:::note Retries are idempotent
A flush re-sends buffered data, which is safe: datapoints are keyed by `(series, timestamp)` and
events by `id`, so the backend collapses duplicates. The SDK stamps each event with a time-ordered
UUID v7 before the first send, so a retried event keeps the same id (see [Events](./events)).
:::

## Results & errors

Most calls return the entity (or a thin wrapper around a list of them); a non-2xx
response surfaces as an exception/error carrying the HTTP status and the raw body.

<Tabs groupId="lang">
<TabItem value="java" label="Java">

Methods return `DataWrapper<T>` — `getItems()` holds the results. Non-2xx throws
`DatahubApiException`:

```java
import ai.intellistream.datahub.models.IdCollection;
import ai.intellistream.datahub.sdk.http.DatahubApiException;

try {
    DataWrapper<Resource> r = client.resources().byIds(List.of(IdCollection.createFromExternalId("pump_1")));
    r.getItems().forEach(System.out::println);
} catch (DatahubApiException e) {
    System.err.println(e.statusCode() + ": " + e.body());
}
```

</TabItem>
<TabItem value="python" label="Python">

Methods return plain `list[T]`. Non-2xx raises `DataHubException`:

```python
from datahub_sdk import DataHubException

try:
    resources = client.resources.by_ids(["pump_1"])
except DataHubException as e:
    print(e.status_code, e.message)
```

</TabItem>
<TabItem value="rust" label="Rust">

Methods return `Result<DataWrapper<T>, ResponseError>` — `get_items()` holds the results,
and `ResponseError` exposes `get_status()` and `get_message()` (its `Display` prints both):

```rust
match api.resources.by_ids(&vec![IdAndExtId::from_external_id("pump_1")]).await {
    Ok(wrapper) => for r in wrapper.get_items() { println!("{:?}", r); }
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
