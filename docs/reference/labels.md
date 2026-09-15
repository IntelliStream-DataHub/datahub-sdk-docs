---
sidebar_position: 5.5
title: Labels
---

# Labels

Labels are the tenant-wide vocabulary that resources and time series are categorised by, and
what filters and the graph view group on. Every resource carries at least one.

Most callers never touch these endpoints: creating a resource with a label name that does not
exist yet auto-creates the label. `/labels` is for the admin flows, pre-seeding names, colours
and translation keys before they are used, and renaming, describing or retiring a label later.

The Java client reaches them through `client.labels()`.

## The label object {#body}

`LabelForm` is both the request and the response shape. It is five fields, and that is the
whole wire contract:

| Field | Type | Notes |
| --- | --- | --- |
| `id` | number | Crosses the wire as a JSON string, like every other id. Synthetic: derived from the name. |
| `name` | string, 3 to 128 | Normalised to `SNAKE_UPPER_CASE`, server-side on write and by the setter on read, so what you send back is what you were given. Unique per tenant. |
| `description` | string | Prose. |
| `i18nCode` | string | Translation key for a localised UI (`nifi.function`). |
| `color` | string, at most 7 | Hex, `#3A9F2E`. |

## Read

```java
import ai.intellistream.datahub.label.LabelForm;

DataWrapper<LabelForm> all = client.labels().list();
DataWrapper<LabelForm> one = client.labels().getById(5677892L);
```

`list()` takes no limit and no cursor. The vocabulary is a small, slow-changing set, so
listing all of it is cheap and there is nothing to page through.

## Create and update

```java
LabelForm critical = new LabelForm();
critical.setName("critical");            // stored as CRITICAL
critical.setDescription("Needs an operator response within the hour");
critical.setColor("#cc11cc");

client.labels().create(List.of(critical));
```

A name that already exists is a `409` naming the collision, not a silent merge.

`update` identifies each label by `id` or by `name`, and the fields you send replace what is
stored. Most callers use the name, since the id is synthetic; to **rename** a label, identify
it by `id`, because a name used to look it up cannot also be the new name.

```java
LabelForm recolour = new LabelForm();
recolour.setName("critical");
recolour.setColor("#a11");
client.labels().update(List.of(recolour));
```

An item that identifies nothing, no `id` and no `name`, is a `400`.

## Delete

```java
client.labels().delete(List.of(IdCollection.createFromId(5677892L)));
```

The endpoint answers `204` with no body. Two refusals, both `400` rather than a silent no-op:

| Refusal | Why | What to do |
| --- | --- | --- |
| The label is still carried by something | Deleting it would silently strip it from those nodes | Clear it first with `resources().update` and `labels.remove`, then delete. The error names what is blocking it. |
| The label is a **type-label** | `ASSET`, `DATASET`, `POLICY`, `TIMESERIES` and `FUNCTION` are the wire discriminator for the node family. Removing one would make every node carrying it unreadable. | Nothing: reserved whether attached or not. |

The same reservation applies to renaming. A type-label cannot be renamed, and an ordinary
label cannot be renamed onto one.

## The Java surface {#client-coverage}

| Operation | Endpoint | Java |
| --- | --- | --- |
| Get by id | `GET /labels/{id}` | `labels().getById` |
| List all | `GET /labels` | `labels().list` |
| Create | `POST /labels/create` | `labels().create` |
| Update | `POST /labels/update` | `labels().update` |
| Delete | `POST` or `DELETE /labels/delete` | `labels().delete` |

The per-resource label caps (64 labels, each at most 512 characters) are in
[Limits & quotas](./limits#field-caps), and labels share the tenant's `objects` ceiling with
resources, time series, data sets and policies.
