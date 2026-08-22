---
sidebar_position: 10
title: Edges
---
import Tabs from '@theme/Tabs';
import TabItem from '@theme/TabItem';

# Edges

The relationships between resources, as objects in their own right. An edge is **directional**
(`from` → `to`), **typed** by a relationship type, and **unique** per pair and type — two
resources can be connected many ways, but only once each way.

Most edges are born with their nodes: `POST /resources/create` takes `nodes` and `relations`
together and writes them in one transaction. The `/edges` endpoints are for everything after
that — linking resources that already exist, reading an edge back, cutting one without
touching its endpoints, and managing the relationship-type catalog.
[Create resources and relations →](./resources#create-resources-and-relations)

## The edge object {#body}

| Field | Type | Notes |
| --- | --- | --- |
| `id` | number | Server-assigned. |
| `start` | number | Id of the `from` node. |
| `end` | number | Id of the `to` node. |
| `type` | string | The relationship type name, upper-cased (`CONTAINS`, `FLOWS_TO`). |
| `relationshipTypeId` | number | The type's id in the [catalog](#types). |
| `description` | string | Prose. |
| `metadata` | map&lt;string, string&gt; | Flat key/value. |

You write `fromExternalId`/`toExternalId` and read `start`/`end`: the write side speaks in
your identifiers, the read side in the graph's.

## Create {#create}

`POST /edges/create` links resources that **already exist**. Both ends are resolved before
anything is written; an end that isn't there is an error, not an implicit create.

```http
POST /edges/create
{
  "items": [
    {
      "fromExternalId": "plant_oslo",
      "toExternalId": "pump_1",
      "relationshipType": "contains",
      "description": "Feeds the east wing",
      "metadata": { "work_order": "wo-sap-12344" }
    }
  ]
}
```

Name each end by external id (`fromExternalId`/`toExternalId`) or by numeric id
(`fromId`/`toId`), and the relation by `relationshipType` or `relationshipTypeId`. A type
name you haven't used before is created for you, so [pre-registering types](#types) is only
for seeding the catalog or attaching a description.

The batch is **all-or-nothing** — one relation the server won't take and none of them are
written. Success is a `201` with the created edges under `items`.

<Tabs groupId="lang">
<TabItem value="java" label="Java">

```java
RelForm contains = new RelForm();
contains.setFromExternalId("plant_oslo");
contains.setToExternalId("pump_1");
contains.setRelationshipType("CONTAINS");

DataWrapper<EdgeProxy> created = client.edges().create(List.of(contains));
System.out.println(created.getItems().iterator().next().getId());
```

`setName("Flows To")` is the alternative to `setRelationshipType`: it normalises the name to
`FLOWS_TO` before it leaves the client. See [naming](#type-names).

</TabItem>
<TabItem value="python" label="Python">

```python
import intellistream_datahub_sdk

contains = intellistream_datahub_sdk.RelForm(
    relationship_type="CONTAINS",
    from_external_id="plant_oslo",
    to_external_id="pump_1",
    description="Feeds the east wing",
)

created = client.edges.create([contains])
print(created[0].id)
```

`RelForm.by_external_ids(from_external_id, to_external_id, relationship_type)` is the short
form when you only need the three; `RelForm.by_ids` is its numeric-id counterpart. The service
unwraps for you — `create` hands back a plain `list[EdgeProxy]`, not a wrapper.

</TabItem>
<TabItem value="rust" label="Rust">

```rust
use intellistream_datahub_sdk::relations::RelForm;

let contains = RelForm::by_external_ids("plant_oslo", "pump_1", "CONTAINS");

let created = api.edges.create(&vec![contains]).await?;
println!("{:?}", created.get_items()[0].id);
```

`RelForm::by_ids(from, to, ty)` is the numeric-id counterpart.

</TabItem>
</Tabs>

### When it fails {#create-errors}

| Status | Means |
| --- | --- |
| `400` | An end doesn't exist (the message names which), the relation has no type, or it breaks one of the dataset or time-series rules below. |
| `403` | You can't write one of the two resources. Both ends are checked, so linking something *into* a data set needs write access on that data set too. |
| `409` | The two are already connected that way. `(start, end, type)` is unique — one relation per pair per type. |

:::note Edges into datasets and time-series are validated
The same two rules the [graph create](./resources#create-resources-and-relations) enforces
apply here:

- A relation **to a dataset** must use the `BELONGS_TO` relationship type — that is the
  relation dataset membership is built from, and anything else is a `400`.
- A **dataset → time-series** edge is accepted only when the series has no dataset yet, or
  already belongs to that very dataset. A series in a *different* dataset is a `400`: a
  time-series has one dataset.
:::

## Look up {#look-up}

`GET /edges/{id}` returns a single edge; an id that doesn't exist is a `404`. Older backends
answered `200` with an empty `items[]` here, so code that has to work against both should
check the count rather than the status.

`POST /edges/byids` takes several ids and answers with a **graph**: the edges under
`relations` and the resources at both ends under `nodes`, so you don't need a follow-up call
to resolve endpoints. Unlike the single lookup, ids that match nothing are **silently
omitted** — compare what comes back against what you asked for.

:::info Reading an edge needs read access to both ends
An edge has no data set of its own, so reading one is authorised on the two resources it
connects, the same rule the write side uses: you need **read access to both endpoints'** data
sets. An edge you may not read looks exactly like one that doesn't exist: `404` from
`GET /edges/{id}`, silently omitted from `POST /edges/byids`. So a missing edge in either
response can mean "no such id" *or* "not yours to see"; don't infer that two resources are
unlinked from it.
:::

<Tabs groupId="lang">
<TabItem value="java" label="Java">

```java
DataWrapper<EdgeProxy> one = client.edges().findById(341);

GraphDataWrapper<Resource, EdgeProxy> many = client.edges()
        .byIds(List.of(IdCollection.createFromId(341), IdCollection.createFromId(342)));

for (Resource endpoint : many.getNodes()) {
    System.out.println(endpoint.getExternalId());
}
```

</TabItem>
<TabItem value="python" label="Python">

```python
one = client.edges.get(341)          # EdgeProxy, or None if nothing has that id

many = client.edges.by_ids([341, 342])
for endpoint in many.nodes:
    print(endpoint.external_id)
```

Edges have no external id, so `by_ids` and `delete` take numeric ids — or an `EdgeProxy` you
already hold, which is accepted anywhere an id is.

</TabItem>
<TabItem value="rust" label="Rust">

```rust
use intellistream_datahub_sdk::generic::IdAndExtId;

let one = api.edges.get(341).await?;

let many = api.edges.by_ids(&vec![IdAndExtId::from_id(341)]).await?;
for endpoint in many.nodes().unwrap_or_default() {
    println!("{}", endpoint.external_id);
}
```

</TabItem>
</Tabs>

## Delete {#delete}

`POST /edges/delete` (or `DELETE`, the endpoint takes both) removes relationships by id and
answers `204` with no body. The resources at each end are untouched — this is how you
disconnect two things without losing either. [Deleting a resource](./resources#delete) is the
heavier move: it takes every relation the resource had with it.

Deletion is **idempotent**: unknown ids are silently skipped, so a successful call is not
evidence the edge existed.

It can still be refused. Cutting an edge is rejected with a `400` if it would leave a
surviving resource unreachable from a root — the same connectivity rule
[deleting a resource](./resources#delete) is checked against, and the response names the
resources that would be stranded. An edge that is the only path from a subtree to the root is
exactly the one you cannot cut: re-attach the subtree another way first, or delete it in the
same call. A `403` means you lack write access to a data set one of the endpoints sits in.

<Tabs groupId="lang">
<TabItem value="java" label="Java">

```java
client.edges().delete(List.of(IdCollection.createFromId(341)));
```

</TabItem>
<TabItem value="python" label="Python">

```python
client.edges.delete([341])
```

</TabItem>
<TabItem value="rust" label="Rust">

```rust
use intellistream_datahub_sdk::generic::IdAndExtId;

api.edges.delete(&vec![IdAndExtId::from_id(341)]).await?;
```

</TabItem>
</Tabs>

## Relationship types {#types}

Every edge carries a type, and the types are a per-tenant catalog: `GET /edges/types` lists
them, `POST /edges/types/create` registers names up front. Registering is optional — a type
is created the first time an edge uses its name — so reach for it when you want the catalog
seeded before anyone writes, or a `description`/`i18nCode` attached to a type.

A type is `{ id, name, description, i18nCode }`.

<Tabs groupId="lang">
<TabItem value="java" label="Java">

```java
DataWrapper<RelationshipType> catalog = client.edges().types();

RelTypeForm form = new RelTypeForm();
form.setName("Flows To");        // normalised to FLOWS_TO by the form, client-side
client.edges().createTypes(List.of(form));
```

</TabItem>
<TabItem value="python" label="Python">

```python
import intellistream_datahub_sdk

catalog = client.edges.types()

client.edges.create_types([
    intellistream_datahub_sdk.RelTypeForm("FLOWS_TO", description="Flow direction"),
])
```

</TabItem>
<TabItem value="rust" label="Rust">

```rust
use intellistream_datahub_sdk::relations::RelTypeForm;

let catalog = api.edges.types().await?;

api.edges.create_types(&vec![RelTypeForm::new("FLOWS_TO")]).await?;
```

</TabItem>
</Tabs>

### What the server does to a name {#type-names}

The two write paths do **not** normalise the same way, which is worth knowing before you
create a type by accident.

`POST /edges/types/create` snake-upper-cases the name as it reads the request, so `Flows To`,
`flows to` and `FLOWS_TO` all land on the one type `FLOWS_TO`.

`POST /edges/create` only **upper-cases** the `relationshipType` you give it. No underscores
are inserted, so an edge created with `"relationshipType": "Flows To"` gets the type
`FLOWS TO` — a *different* type from `FLOWS_TO`, silently created on the spot. Lookup is on the
normalised name, so `flows_to` and `FLOWS_TO` are the same type either way.

The practical rule: write the type name the way you want it stored, `FLOWS_TO`, and the two
paths agree. In Java, `RelForm.setName("Flows To")` snake-upper-cases client-side and lines the
create path up with the catalog; `setRelationshipType` passes the string through. Python and
Rust send what you give them.

A name with no letter or digit in it (blank, or symbols only) is a `400`, and names registered
through `types/create` are capped at 128 characters.

:::caution A duplicate type name takes the whole batch with it
`POST /edges/types/create` has no find-or-create: it saves a fresh type unconditionally, so a
name that already exists (matched case-insensitively) collides on the unique name hash and
comes back as a **`409`** naming the conflict — not the "existing ones returned unchanged" the
endpoint used to advertise. You cannot use it to look up the id of a type you did not just
create; read `GET /edges/types` for that.

Every form in a batch is saved in one transaction, so a single duplicate rolls the valid new
types back alongside it. Treat the `409` as *"nothing in this batch was created"* rather than
*"one of these already existed"*. Creating an edge with an unknown type name does not have
this problem — that path is a proper find-or-create.
:::

## What each client covers {#client-coverage}

| Operation | Java | Python | Rust |
| --- | --- | --- | --- |
| Create relations | `edges().create` | `edges.create` | `edges.create` |
| Get by id | `edges().findById` | `edges.get` | `edges.get` |
| Look up several, with endpoints | `edges().byIds` | `edges.by_ids` | `edges.by_ids` |
| Delete | `edges().delete` | `edges.delete` | `edges.delete` |
| List types | `edges().types` | `edges.types` | `edges.types` |
| Create types | `edges().createTypes` | `edges.create_types` | `edges.create_types` |

All three clients cover the whole endpoint surface; what differs is how much wrapping survives.
Java and Rust hand back the `DataWrapper`/`GraphDataWrapper` the API returns, so the items come
out of `getItems()` / `get_items()`. Python unwraps: `create` and `types` return plain lists,
`get` returns an `EdgeProxy` or `None`, and `delete` returns nothing. Python's async client
exposes the same six methods on `AsyncDataHubClient.edges`.

The [MCP server](../mcp-server#relationships) covers all of these except `byids`, as
`edge_create`, `edge_get`, `edge_delete`, `edge_list_types` and `edge_create_type`.
