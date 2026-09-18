---
sidebar_position: 12
title: Tenant
---

# Tenant

Two things about the tenant your token belongs to: which optional features are switched on, and
the settings your organization administers for itself.

The Java client reaches them through `client.tenant()`.

## Feature flags {#features}

`GET /tenant/features` says which optional features your tenant may use. Gate feature-specific
code on it: a disabled feature still has endpoints, and they answer `404` or `403`.

```java
import ai.intellistream.datahub.tenant.TenantFeatures;

TenantFeatures features = client.tenant().features();
if (features.isFilesEnabled()) {
    // show the file browser
}
```

| Wire field | Java | Meaning |
| --- | --- | --- |
| `files` | `isFilesEnabled()` | The [file storage](./files) endpoints. |
| `policy` | `isPolicyFeatureEnabled()` | [Policies and governance](./policies). |
| `streaming` | `isStreamingFeatureEnabled()` | Streaming ingest. |
| `chat` | `isChatFeatureEnabled()` | The AI assistant, configured below. |

A flag absent from the tenant's configuration falls back to the deployment default, and the
Java accessors read absent as false.

## What you may change {#settings-permissions}

Settings are granted per **scope**, through Keycloak organization groups:
`/settings/<scope>/read` and `/settings/<scope>/write`, or `/settings/*/read` and
`/settings/*/write` for every scope. Read and write are separate grants, and **write does not
imply read**. The scope known today is `llm`.

`GET /tenant/settings/permissions` says which you hold, with wildcards already resolved, so
every scope the platform knows is listed by name.

```java
import ai.intellistream.datahub.models.tenant.SettingsPermission;

Map<String, SettingsPermission> grants = client.tenant().settingsPermissions();
SettingsPermission llm = grants.get("llm");
llm.read();     // show the form, or show it read-only
llm.write();
```

It is deliberately ungated, so it answers for everyone. It exists so a client can decide
between an editable form, a read-only one, and no form at all, without calling an endpoint and
reading the `403`. It is **not** the security boundary: the settings endpoints enforce the same
grants regardless of what this says.

## Model configuration {#llm-settings}

`GET /tenant/settings/llm` and `PUT /tenant/settings/llm` read and replace the model your
organization's assistant runs on. The API key is never returned: `apiKeySet` says whether one
is stored, and `configured` says whether the whole thing amounts to a model that can actually
be called. When `configured` is false, your organization has no assistant.

```java
import ai.intellistream.datahub.models.tenant.TenantLlmSettings;
import ai.intellistream.datahub.models.tenant.TenantLlmSettingsForm;

TenantLlmSettings current = client.tenant().llmSettings();
current.apiKeySet();     // true, but never the key itself
current.configured();

TenantLlmSettings saved = client.tenant().updateLlmSettings(new TenantLlmSettingsForm(
        current.provider(), "the-model-id", null /* apiKey: keep the stored one */,
        current.baseUrl(), current.reasoningEffort(), "high", current.turnTimeout(),
        current.maxOutputTokens(), current.maxIterations(), current.instructions()));
```

`TenantLlmSettings` and `TenantLlmSettingsForm` are records, so the fields read as
`current.provider()` and so on. They are two records rather than one because `apiKey` travels
one way only: it can be written and is never read back.

:::note `apiKey` is the one exception to "replace"
The `PUT` replaces the configuration with what you send, absent meaning unset, except for
`apiKey`: absent or blank leaves the stored credential alone, and only a non-blank value
overwrites it. That is what lets a form render the field empty, since the credential is never
returned, and still be savable without retyping it.
:::

A field you leave unset falls back to the deployment default, except the ones that identify the
model, which have no default: a `provider`, a `model`, and an `apiKey` or a `baseUrl` depending
on the provider. Those are what make the assistant available at all.

`effort` accepts `low`, `medium`, `high`, `xhigh` or `max`, weakest first, and the list is on
the record as `TenantLlmSettings.EFFORT_LEVELS` so a client rendering a picker does not have to
hard-code it.

A change takes effect for the API immediately. Other services cache the tenant registry and
pick it up within five minutes.

## The Java surface {#client-coverage}

| Operation | Endpoint | Java |
| --- | --- | --- |
| Feature flags | `GET /tenant/features` | `tenant().features` |
| Settings permissions | `GET /tenant/settings/permissions` | `tenant().settingsPermissions` |
| Read model configuration | `GET /tenant/settings/llm` | `tenant().llmSettings` |
| Change model configuration | `PUT /tenant/settings/llm` | `tenant().updateLlmSettings` |
