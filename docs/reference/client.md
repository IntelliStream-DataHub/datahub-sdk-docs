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

### From HashiCorp Vault (Java)

The Java client can also read the same keys from a Vault KV v2 secret, with a token or
with AppRole:

```java
DatahubConfig cfg = DatahubConfig.fromVault(vaultAddr, vaultToken, "datahub/sdk");
DatahubConfig cfg = DatahubConfig.fromVaultEnv("datahub/sdk");                 // VAULT_ADDR + VAULT_TOKEN
DatahubConfig cfg = DatahubConfig.fromVaultAppRole(vaultAddr, roleId, secretId, "datahub/sdk");
DatahubConfig cfg = DatahubConfig.fromVaultAppRoleEnv("datahub/sdk");          // VAULT_ADDR + VAULT_ROLE_ID + VAULT_SECRET_ID
```

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
and `ResponseError` carries `.status` and `.message`:

```rust
match api.resources.by_ids(&vec![IdAndExtId::from_external_id("pump_1")]).await {
    Ok(wrapper) => for r in wrapper.get_items() { println!("{:?}", r); }
    Err(e) => eprintln!("{}: {}", e.status, e.message),
}
```

</TabItem>
</Tabs>

:::note Entity ids are JSON strings on the wire
64-bit ids are serialized as JSON **strings** so they survive JavaScript's 2⁵³ number
limit. Each client reads them back into a native integer, so this only matters if you
inspect raw responses.
:::
