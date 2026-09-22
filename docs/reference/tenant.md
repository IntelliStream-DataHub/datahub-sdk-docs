---
sidebar_position: 12
title: Tenant
---

# Tenant

Which optional features the tenant your token belongs to may use, and the settings your
organization administers for itself. The Java client reaches them through `client.tenant()`.

## Feature flags {#features}

`GET /tenant/features` says which optional features the tenant may use. A disabled feature's
endpoints answer `404` or `403`.

```java
import ai.intellistream.datahub.tenant.TenantFeatures;

TenantFeatures features = client.tenant().features();
if (features.isFilesEnabled()) {
    // show the file browser
}
```

| Wire field | Java | Feature |
| --- | --- | --- |
| `files` | `isFilesEnabled()` | The [file storage](./files) endpoints. |
| `policy` | `isPolicyFeatureEnabled()` | [Policies and governance](./policies). |
| `streaming` | `isStreamingFeatureEnabled()` | Streaming ingest. |
| `chat` | `isChatFeatureEnabled()` | The AI assistant, configured below. |

`policy`, `streaming` and `chat` fall back to the deployment default when the tenant's
configuration does not carry them; `files` reads absent as off. The Java accessors return
primitive booleans.

## What you may change {#settings-permissions}

Settings are granted per **scope**, through Keycloak organization groups:
`/settings/<scope>/read` and `/settings/<scope>/write`, or `/settings/*/read` and
`/settings/*/write` for every scope. Read and write are separate grants, and write does not
imply read. The one scope is `llm`.

`GET /tenant/settings/permissions` says which grants you hold, with wildcards resolved, so
every scope the platform knows is listed by name. The endpoint is ungated.

```java
import ai.intellistream.datahub.models.tenant.SettingsPermission;

Map<String, SettingsPermission> grants = client.tenant().settingsPermissions();
SettingsPermission llm = grants.get("llm");
llm.read();
llm.write();
```

## Model configuration {#llm-settings}

`GET /tenant/settings/llm` and `PUT /tenant/settings/llm` read and replace the model your
organization's assistant runs on. The API key is never returned: `apiKeySet` says whether one
is stored, and `configured` says whether the settings amount to a model that can be called.

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
`current.provider()` and so on. `apiKey` is write-only: it is carried on the form and never
returned by a read.

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

## What each client covers {#client-coverage}

| Operation | Java | Python | Rust |
| --- | --- | --- | --- |
| Feature flags (`GET /tenant/features`) | `tenant().features` | — | — |
| Settings permissions (`GET /tenant/settings/permissions`) | `tenant().settingsPermissions` | — | — |
| Read model configuration (`GET /tenant/settings/llm`) | `tenant().llmSettings` | — | — |
| Change model configuration (`PUT /tenant/settings/llm`) | `tenant().updateLlmSettings` | — | — |
