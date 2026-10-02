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
imply read. The one scope is `llm`.

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

### Suggest model names {#llm-models}

`POST /tenant/settings/llm/models` asks an OpenAI-compatible server which models it offers and
returns their ids (`data[].id` from `<baseUrl>/models`). The SDKs have no method for it, so call
it over REST:

```bash
curl -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"baseUrl": "http://localhost:11434/v1"}' \
  "$API/tenant/settings/llm/models"
# ["qwen3.8:latest", "nemotron-3.5-lightning:30b"]
```

An optional `apiKey` goes in the body, not the URL, so it stays out of access logs. Leave it out
and the API uses your organization's stored key, but only when `baseUrl` is the stored base URL;
for any other URL no key is sent.

The list is a suggestion, not a check: the `PUT` above accepts any model name, since some hosts
answer to names they do not list (deployment names, gateway aliases). A server that cannot be
reached, or that answers with something other than a model list, gives `200` with an empty
array, and nothing else from it is passed back. A missing or non-http(s) `baseUrl` is a `400`
with a field error on `baseUrl`.

It needs the same grant as changing the configuration, `llm` write (`/settings/llm/write` or
`/settings/*/write`, see [above](#settings-permissions)), and is a `403` without it.

## What each client covers {#client-coverage}

| Operation | Java | Python | Rust |
| --- | --- | --- | --- |
| Feature flags (`GET /tenant/features`) | `tenant().features` | `tenant.features` | `tenant.features` |
| Settings permissions (`GET /tenant/settings/permissions`) | `tenant().settingsPermissions` | `tenant.settings_permissions` | `tenant.settings_permissions` |
| Read model configuration (`GET /tenant/settings/llm`) | `tenant().llmSettings` | `tenant.llm_settings` | `tenant.llm_settings` |
| Change model configuration (`PUT /tenant/settings/llm`) | `tenant().updateLlmSettings` | `tenant.update_llm_settings` | `tenant.update_llm_settings` |
| [Suggest model names](#llm-models) (`POST /tenant/settings/llm/models`) | — | — | — |
