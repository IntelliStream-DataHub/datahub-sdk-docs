---
sidebar_position: 5.5
title: Labels
---

# Labels

Labels are the tenant-wide vocabulary that resources and time series are categorised by. Every
resource carries at least one. Creating a resource with a label name that does not exist yet
creates the label.

## The label object {#body}

`LabelForm` is the request body, and what the Java client reads responses back into:

| Field | Type | Notes |
| --- | --- | --- |
| `id` | number | Server-assigned. |
| `name` | string, 3 to 128 | Normalised to `SNAKE_UPPER_CASE`. Unique per tenant. |
| `description` | string | Prose. |
| `i18nCode` | string | Translation key for a localised UI (`nifi.function`). |
| `color` | string, at most 7 | Hex, `#3A9F2E`. |

## Read

```java
import ai.intellistream.datahub.label.LabelForm;

DataWrapper<LabelForm> all = client.labels().list();
DataWrapper<LabelForm> one = client.labels().getById(5677892L);
```

`list()` takes no limit and no cursor: it returns the whole vocabulary.

## Create and update

```java
LabelForm critical = new LabelForm();
critical.setName("critical");            // stored as CRITICAL
critical.setDescription("Needs an operator response within the hour");
critical.setColor("#cc11cc");

client.labels().create(List.of(critical));
```

A name that already exists is a `409`.

`update` identifies each label by `id`, and the fields you send replace what is stored.

```java
LabelForm recolour = new LabelForm();
recolour.setId(5677892L);
recolour.setName("critical");            // required on the form
recolour.setColor("#a11");
client.labels().update(List.of(recolour));
```

## Delete

```java
client.labels().delete(List.of(IdCollection.createFromId(5677892L)));
```

The endpoint answers `204` with no body. Two cases are refused with a `400`:

| Refusal | Detail |
| --- | --- |
| The label is still carried by a node | The error names what is blocking it. Clear it with `resources().update` and `labels.remove`, then delete. |
| The label is a type-label | `ASSET`, `DATASET`, `POLICY`, `TIMESERIES` and `FUNCTION` are reserved, whether attached or not. They cannot be renamed either, and an ordinary label cannot be renamed onto one. |

## What each client covers {#client-coverage}

| Operation | Java | Python | Rust |
| --- | --- | --- | --- |
| Get by id (`GET /labels/{id}`) | `labels().getById` | `labels.get` | `labels.get` |
| List all (`GET /labels`) | `labels().list` | `labels.list` | `labels.list` |
| Create (`POST /labels/create`) | `labels().create` | `labels.create` | `labels.create` |
| Update (`POST /labels/update`) | `labels().update` | `labels.update` | `labels.update` |
| Delete (`POST` or `DELETE /labels/delete`) | `labels().delete` | `labels.delete` | `labels.delete` |

The per-resource label caps (64 labels, each at most 512 characters) are in
[Limits & quotas](./limits#field-caps).
