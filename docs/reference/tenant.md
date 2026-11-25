---
sidebar_position: 12
title: Tenant
---

import Tabs from '@theme/Tabs';
import TabItem from '@theme/TabItem';

# Tenant

Which optional features the tenant your token belongs to may use, and the settings your
organization administers for itself: `client.tenant()` in Java, `client.tenant` in Python and
`api.tenant` in Rust. Every answer is a plain object, not an `items` list.

## Feature flags {#features}

`GET /tenant/features` says which optional features the tenant may use. A disabled feature's
endpoints answer `404` or `403`.

<Tabs groupId="lang">
<TabItem value="java" label="Java">

```java
import ai.intellistream.datahub.tenant.TenantFeatures;

TenantFeatures features = client.tenant().features();
if (features.isFilesEnabled()) {
    // show the file browser
}
```

</TabItem>
<TabItem value="python" label="Python">

```python
features = client.tenant.features()
if features.files:
    ...  # show the file browser
```

</TabItem>
<TabItem value="rust" label="Rust">

```rust
let features = api.tenant.features().await?;
if features.files {
    // show the file browser
}
```

</TabItem>
</Tabs>

| Wire field | Java | Python and Rust | Feature |
| --- | --- | --- | --- |
| `files` | `isFilesEnabled()` | `files` | The [file storage](./files) endpoints. |
| `policy` | `isPolicyFeatureEnabled()` | `policy` | [Policies and governance](./policies). |
| `streaming` | `isStreamingFeatureEnabled()` | `streaming` | Streaming ingest. |
| `chat` | `isChatFeatureEnabled()` | `chat` | The AI assistant, configured below. |

`policy`, `streaming` and `chat` fall back to the deployment default when the tenant's
configuration does not carry them; `files` reads absent as off. Every client reads each flag as
a plain boolean.

## What you may change {#settings-permissions}

Settings are granted per **scope**, through Keycloak organization groups:
`/settings/<scope>/read` and `/settings/<scope>/write`, or `/settings/*/read` and
`/settings/*/write` for every scope. Read and write are separate grants, and write does not
imply read. The scopes are `llm`, the [model configuration](#llm-settings), and `flow`, the
[flow settings](#flow-settings).

`GET /tenant/settings/permissions` says which grants you hold, with wildcards resolved, so
every scope the platform knows is listed by name. The endpoint is ungated.

<Tabs groupId="lang">
<TabItem value="java" label="Java">

```java
import ai.intellistream.datahub.models.tenant.SettingsPermission;

Map<String, SettingsPermission> grants = client.tenant().settingsPermissions();
SettingsPermission llm = grants.get("llm");
llm.read();
llm.write();
```

</TabItem>
<TabItem value="python" label="Python">

```python
grants = client.tenant.settings_permissions()   # dict[str, SettingsPermission]
grants["llm"].read
grants["llm"].write
```

</TabItem>
<TabItem value="rust" label="Rust">

```rust
let grants = api.tenant.settings_permissions().await?;   // HashMap<String, SettingsPermission>
grants["llm"].read;
grants["llm"].write;
```

</TabItem>
</Tabs>

## Model configuration {#llm-settings}

`GET /tenant/settings/llm` and `PUT /tenant/settings/llm` read and replace the model your
organization's assistant runs on. The API key is never returned: `apiKeySet` says whether one
is stored, and `configured` says whether the settings amount to a model that can be called.

<Tabs groupId="lang">
<TabItem value="java" label="Java">

```java
import ai.intellistream.datahub.models.tenant.TenantLlmSettings;
import ai.intellistream.datahub.models.tenant.TenantLlmSettingsForm;

TenantLlmSettings current = client.tenant().llmSettings();
current.apiKeySet();
current.configured();

TenantLlmSettings saved = client.tenant().updateLlmSettings(new TenantLlmSettingsForm(
        current.provider(), "the-model-id", null /* apiKey: keep the stored one */,
        current.baseUrl(), current.reasoningEffort(), "high", current.turnTimeout(),
        current.maxOutputTokens(), current.maxIterations(), current.instructions()));
```

`TenantLlmSettings` and `TenantLlmSettingsForm` are records, so the fields read as
`current.provider()` and so on.

</TabItem>
<TabItem value="python" label="Python">

```python
current = client.tenant.llm_settings()
current.api_key_set
current.configured

# Keywords rather than a form. Every one you leave out is sent unset, so carry the rest over;
# api_key left out keeps the stored credential.
saved = client.tenant.update_llm_settings(
    provider=current.provider, model="the-model-id", base_url=current.base_url,
    reasoning_effort=current.reasoning_effort, effort="high",
    turn_timeout=current.turn_timeout, max_output_tokens=current.max_output_tokens,
    max_iterations=current.max_iterations, instructions=current.instructions,
)
```

</TabItem>
<TabItem value="rust" label="Rust">

```rust
use intellistream_datahub_sdk::tenant::TenantLlmSettingsForm;

let current = api.tenant.llm_settings().await?;
current.api_key_set;
current.configured;

// A form built from what is stored saves it unchanged, `api_key: None` keeping the credential;
// change only what you mean to.
let form = TenantLlmSettingsForm {
    model: Some("the-model-id".into()),
    effort: Some("high".into()),
    ..TenantLlmSettingsForm::from(&current)
};
let saved = api.tenant.update_llm_settings(&form).await?;
```

</TabItem>
</Tabs>

`apiKey` is write-only: it is carried on the form and never returned by a read.

The `PUT` replaces the configuration with what you send, absent meaning unset, except for
`apiKey`: absent or blank leaves the stored credential alone, and only a non-blank value
overwrites it.

A field you leave unset falls back to the deployment default. The fields that identify the
model have no default: a `provider`, a `model`, and an `apiKey` or a `baseUrl` depending on the
provider.

`effort` accepts `low`, `medium`, `high`, `xhigh` or `max`, weakest first, and the list is on
the record as `TenantLlmSettings.EFFORT_LEVELS`.

The API instance that served the write refreshes immediately. Other instances and services
cache the tenant registry and pick the change up within five minutes.

## Flow settings {#flow-settings}

The credentials your organization's flows and [agents](../agents) may use, under
`/tenant/settings/flow`. No client wraps these; call them over REST. Every one is write-only
for what is secret: `GET /tenant/settings/flow` returns names, client ids, URLs and header names,
never a secret's value, a client's secret or a tool server's credential.

```json
{
  "secrets": ["erp-api-key"],
  "clients": [ { "name": "nightly", "clientId": "datahub-nightly" } ],
  "mcpServers": [
    { "name": "crm", "url": "https://tools.example.com/mcp", "auth": "header", "headerName": "Authorization" },
    { "name": "erp", "url": "https://erp.example.com/mcp", "auth": "client-credentials",
      "tokenUrl": "https://auth.example.com/oauth2/token", "clientId": "datahub-agents",
      "scope": "tools.read", "resource": "https://erp.example.com/mcp" }
  ]
}
```

`secrets` are the named values a flow refers to as [`${secrets.<name>}`](#flow-secrets), and
`clients` the [Keycloak clients a flow may be deployed to run as](#flow-clients). `mcpServers`
are the [tool servers agents may call](../agents#tool-servers). The fields of the kind of
authentication a server does not use are left out. Reading needs `/settings/flow/read`; every
`PUT` and `DELETE` below needs `/settings/flow/write`, answers `204`, and reports a bad name or
field as a `400` with field errors.

A secret's or a client's `name` is lowercase letters, digits and dashes, starting with a letter
or digit, at most 63 characters.

### `PUT /tenant/settings/flow/secrets/{name}` {#flow-secrets}

Stores the value under `name`, replacing any value it had. `value` is required and is never
returned.

```json
{ "value": "…" }
```

A step refers to it as `${secrets.<name>}`, in a property marked sensitive, where the whole value
must be that one reference; the flow service resolves it when the run starts. A run that refers
to a secret the organization does not have fails with `MISSING_SECRET`.

### `DELETE /tenant/settings/flow/secrets/{name}` {#flow-secrets-delete}

Removes the secret; also `204` when there was none. Flows that refer to it fail their next run.

### `PUT /tenant/settings/flow/clients/{name}` {#flow-clients}

Registers a confidential Keycloak client under `name`, replacing it when the name is taken.

```json
{ "clientId": "datahub-nightly", "clientSecret": "…" }
```

Both fields are required every time, since the secret is never returned: a pair stored half old
and half new would fail only when a run first tries it. `clientId` is the client id Keycloak
shows, not its internal UUID. The client's service-account user must be a member of the
organization with `DATAHUB_ACCESS` and the groups its flows need.

The credentials are not tried here. A deployment that names the client,
`PUT /flows/{id}/deployment` with `"runAs": "<name>"` on the flow service, takes a token with
them and checks that the client may write the flow's data set, and that the caller holds every
group the client holds ([whose access a run uses](../agents#run-identity)). A replaced secret
is used from the next token on.

### `DELETE /tenant/settings/flow/clients/{name}` {#flow-clients-delete}

Removes the registration; also `204` when nothing was registered. The client stays in Keycloak:
disable it or rotate its secret there to end its access. Flows that run as it fail and show
`needs-reauthorisation` until they are deployed again.

A removed or replaced secret or client secret stays in Vault's version history until Vault rolls
it out, so removing one is no substitute for rotating it at its source.

### `PUT /tenant/settings/flow/mcp-servers/{name}` {#flow-mcp-servers}

Registers the server, replacing it when the name is taken. Needs `/settings/flow/write`.
`name` is lowercase letters, digits and dashes, starting with a letter or digit, at most 24
characters; it is the prefix of the server's tools, `crm__ticket_get`.

```json
{ "url": "https://tools.example.com/mcp", "auth": "header", "headerName": "X-Api-Key", "headerValue": "…" }
```

```json
{ "url": "https://erp.example.com/mcp", "auth": "client-credentials",
  "tokenUrl": "https://auth.example.com/oauth2/token", "clientId": "datahub-agents", "clientSecret": "…",
  "scope": "tools.read", "resource": "https://erp.example.com/mcp" }
```

| Field | | |
| --- | --- | --- |
| `url` | required | The server's Streamable HTTP endpoint, called as given. |
| `auth` | `header` | `header` or `client-credentials`; saving one kind drops what was stored for the other. |
| `headerName` | `Authorization` | `header`: the header the credential travels in. One the client sets itself (`Accept`, `Content-Type`, `Mcp-Session-Id`, `MCP-Protocol-Version`, `Host` and the like) is refused. |
| `headerValue` | | `header`: the credential, a single line, sent as it is (`Bearer …`). |
| `tokenUrl` | required | `client-credentials`: the token endpoint. |
| `clientId` | required | `client-credentials`: the client. |
| `clientSecret` | | `client-credentials`: its secret, a single line. |
| `scope` | | `client-credentials`: sent when given, space-separated as the endpoint expects it. |
| `resource` | | `client-credentials`: an absolute URI, sent when given. |

`headerValue` and `clientSecret` are never returned, and absent or blank means **keep the stored
one**, so a server can be re-pointed without retyping its credential. One is required when
nothing of that kind is stored under the name, when `auth` switches kind, and, for a secret, when
`clientId` changes. Problems are a `400` with field errors, as for the other settings.

`url` and `tokenUrl` are checked for where they point, not for whether anything answers: one that
resolves to a private, loopback or link-local address is refused unless the deployment allows
private networks, and so is plain `http`. Nothing is called on save; `GET /agents/tools` on the
flow service shows what the server answers.

### `DELETE /tenant/settings/flow/mcp-servers/{name}` {#flow-mcp-servers-delete}

Removes the registration, credential included; `204`, also when nothing was registered under the
name. An agent whose `tools` still name the server fails its next run until it is edited.

## What each client covers {#client-coverage}

| Operation | Java | Python | Rust |
| --- | --- | --- | --- |
| Feature flags (`GET /tenant/features`) | `tenant().features` | `tenant.features` | `tenant.features` |
| Settings permissions (`GET /tenant/settings/permissions`) | `tenant().settingsPermissions` | `tenant.settings_permissions` | `tenant.settings_permissions` |
| Read model configuration (`GET /tenant/settings/llm`) | `tenant().llmSettings` | `tenant.llm_settings` | `tenant.llm_settings` |
| Change model configuration (`PUT /tenant/settings/llm`) | `tenant().updateLlmSettings` | `tenant.update_llm_settings` | `tenant.update_llm_settings` |
| Flow settings (`/tenant/settings/flow`, secrets, clients and tool servers) | REST only | REST only | REST only |
