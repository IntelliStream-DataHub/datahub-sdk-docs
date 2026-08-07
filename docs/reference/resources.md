---
sidebar_position: 3
title: Resources
---
import Tabs from '@theme/Tabs';
import TabItem from '@theme/TabItem';

# Resources

Hierarchical, asset-like entities and the relationships between them. Create resources
and the edges between them in one call; the server returns the persisted graph.

A resource's `externalId` is its **identity**: unique per tenant, stored exactly as you send
it, and compared without case. Mirror the tag your operation already maintains —
`COM-99-PT-1034` is stored as `COM-99-PT-1034`, not rewritten.
[External ids & naming →](./external-ids)

## The resource body {#body}

| Field | Type | Notes |
| --- | --- | --- |
| `id` | number | Server-assigned. Crosses the wire as a JSON string — see the note below. |
| `externalId` | string, 3–256 | **Required.** Unique per tenant, stored verbatim, matched case-insensitively. |
| `name` | string, 3–512 | **Required.** What a human calls it. This is the field [search](#search) reads. |
| `labels` | string[] | **Required, at least one.** The type tags (`Pump`, `Plant`). Upper-cased by the server. |
| `description` | string | Prose. |
| `metadata` | map&lt;string, string&gt; | Flat key/value, filterable by exact match. |
| `source` | string, 2–128 | The upstream system of record this came from (`SAP`, a historian, a file drop). |
| `dataSetId` | number | The data set the resource belongs to. |
| `geoLocation` | GeoJSON geometry | `Point`, `Polygon`, … Validated on write; stored verbatim. |
| `isRoot` | boolean | Whether the resource is a navigation root. Deletes are checked against reachability from a root — see [Delete](#delete). |
| `relatedResources` | object[] | Read-only view of the graph: `{ id, externalId, relationshipType, direction }` per connected node. Populated where the graph is loaded, empty otherwise. |
| `createdTime`, `lastUpdatedTime` | epoch millis | Server-set. |

Labels are how the platform types a node. The type-label (`ASSET`, `TIMESERIES`, `DATASET`,
`POLICY`, `FUNCTION`) is what the create pipeline reads to decide which kind of entity to
build, and free-form labels ride alongside it. That is also why one `/resources/create` call
can hold a mix of node types — a time-series next to an asset — rather than needing one
endpoint per type.

:::note Numeric ids cross the wire as JSON strings
`id` and `dataSetId` serialize as `"5677892"`, not `5677892` — ids can exceed the 53-bit
integer a JSON number is safe for in JavaScript. The clients parse them back for you.
:::

## Look up

Fetch by numeric id or external id (you can mix them). Lookup ignores case, so `pump_1` and
`PUMP_1` resolve to the same resource; what comes back keeps the spelling it was created
with. Identifiers that match nothing are **silently omitted** rather than erroring, so
compare the returned items against what you asked for when a miss matters.

<Tabs groupId="lang">
<TabItem value="java" label="Java">

```java
import ai.intellistream.datahub.models.IdCollection;

Resource pump = client.resources().getById(5677892).getItems().iterator().next();

DataWrapper<Resource> some = client.resources().byIds(List.of(
        IdCollection.createFromExternalId("pump_1"),
        IdCollection.createFromId(5677892)));
```

</TabItem>
<TabItem value="python" label="Python">

```python
# pass entity objects, external-id strings, or numeric ids
resources = client.resources.by_ids(["pump_1", 5677892])
```

</TabItem>
<TabItem value="rust" label="Rust">

```rust
use dataplatform_rust_sdk::generic::IdAndExtId;

let resources = api.resources.by_ids(&vec![
    IdAndExtId::from_external_id("pump_1"),
    IdAndExtId::from_id(5677892),
]).await?;
```

</TabItem>
</Tabs>

## Create resources and relations {#create-resources-and-relations}

Pass the resource forms (nodes) and the relation forms (edges); the call returns the
created graph — nodes plus server-assigned edges. Each resource needs **at least one
label** (a type tag such as `Plant` or `Pump`) — a node with none is rejected with
`400 resource.needs.at.least.one.label`. Labels and relationship types are both
upper-cased by the server. External ids are not: they are stored verbatim.

The call is **all-or-nothing**. Every external id in the batch is validated before anything
is written, so one item rejected by the
[naming policy](./external-ids#the-naming-policy) means nothing is created and the `400`
names every offending item, not just the first. If the policy is set to warn instead, the
response carries a [`warnings` array](./external-ids#warnings-on-the-response) next to
`items`.

A relation may reference a node being created in the same request by its `externalId`, or
point at one that already exists. An edge whose endpoint is neither is a `400` naming the
endpoint it could not resolve. Re-using an `externalId` that already exists in the tenant is
a `409` whose `duplicated` list names which ones — use [update](#update) to change the
existing resource instead.

:::note Edges into datasets and time-series are validated
Two endpoint rules apply to every edge, on create and on update (an update can retarget an
edge or change its type):

- A relation **to a dataset** must use the `BELONGS_TO` relationship type — that is the
  relation the dataset hierarchy and membership are built from, and anything else is
  rejected with a `400`.
- A **dataset → time-series** edge is accepted only when the series has no dataset yet, or
  already belongs to that very dataset (creating a series inside a dataset produces exactly
  that membership edge). A series in a *different* dataset is rejected with a `400` — a
  time-series has one dataset.
:::

<Tabs groupId="lang">
<TabItem value="java" label="Java">

```java
ResourceForm plant = new ResourceForm();
plant.setExternalId("plant_oslo");
plant.setName("Oslo Plant");
plant.setLabels(List.of("Plant"));

ResourceForm pump = new ResourceForm();
pump.setExternalId("pump_1");
pump.setName("Pump 1");
pump.setLabels(List.of("Pump"));

RelForm contains = new RelForm();
contains.setName("contains");
contains.setFromExternalId("plant_oslo");
contains.setToExternalId("pump_1");

GraphDataWrapper<Resource, EdgeProxy> created = client.resources()
        .create(List.of(plant, pump), List.of(contains));

System.out.println(created.getNodes().size() + " resources, "
        + created.getRelations().size() + " relations");
```

</TabItem>
<TabItem value="python" label="Python">

```python
import datahub_sdk

plant = datahub_sdk.Resource(external_id="plant_oslo", name="Oslo Plant", labels=["Plant"])
pump = datahub_sdk.Resource(external_id="pump_1", name="Pump 1", labels=["Pump"])
contains = datahub_sdk.RelForm.by_external_ids("plant_oslo", "pump_1", "contains")

result = client.resources.create([plant, pump], [contains])
print(len(result.nodes), "resources,", len(result.relations), "relations")
```

</TabItem>
<TabItem value="rust" label="Rust">

```rust
use dataplatform_rust_sdk::resources::Resource;
use dataplatform_rust_sdk::relations::RelForm;

let mut plant = Resource::new();
plant.external_id = "plant_oslo".into();
plant.name = "Oslo Plant".into();
plant.labels = Some(vec!["Plant".into()]);

let mut pump = Resource::new();
pump.external_id = "pump_1".into();
pump.name = "Pump 1".into();
pump.labels = Some(vec!["Pump".into()]);

let contains = RelForm::by_external_ids("plant_oslo", "pump_1", "contains");

let created = api.resources.create(vec![plant, pump], vec![contains]).await?;
```

</TabItem>
</Tabs>

An edge comes back as a `Relation` — `{ id, start, end, type, description, metadata }`,
where `start` and `end` are the numeric ids of the two nodes. That is why you send
`fromExternalId`/`toExternalId` but read `start`/`end`: the write side speaks in your
identifiers, the read side in the graph's.

Relations are directional. `from` → `to` is the direction you will see when you
[traverse](#traverse-the-graph), so `plant contains pump` and `pump contains plant`
describe different graphs.

### Relations without the nodes {#create-relations}

There are two ways to create a relation and they produce the same edge. The call above
sends nodes and relations together. `POST /edges/create` sends the relations by
themselves:

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

`items[]` takes exactly what you would have put in `relations[]` — the same fields, the
same endpoint rules, the same `Relation` objects back, now under `items` and with a `201`.
Which form you pick is only a question of whether the two ends need creating: send them
together when a resource and its relation have to appear in one go, and send the relation
alone when both ends are already there and repeating them would be noise.

Either way the failures are the same. A `400` means one end doesn't exist (the message
says which), the relation has no type, or the dataset and time-series rules above don't
allow it. A `403` means you can't write one of the two resources — both ends are checked,
so connecting something *into* a data set needs write access on that data set too. A `409`
means the two are already connected that way; a pair can carry one relation per type.

In Java that is `resources().createRelations(relations)`:

```java
RelForm contains = new RelForm();
contains.setName("contains");
contains.setFromExternalId("plant_oslo");
contains.setToExternalId("pump_1");

DataWrapper<EdgeProxy> created = client.resources().createRelations(List.of(contains));
```

:::note Python and Rust
The other two clients don't wrap this one yet. Until they do, `resources.create` with your
relations and an empty list of nodes gets you the same edges.
:::

To disconnect two resources without touching either of them, `POST /edges/delete` with the
relation's id. [Deleting a resource](#delete) is the heavier move: it takes every relation
the resource had with it.

## Filter

`POST /resources/filter` finds resources by structured criteria. Everything you supply is
combined with **AND**.

| Field | Matching |
| --- | --- |
| `name` | Case-insensitive **substring**. `%` works as a wildcard (`"pipe%"`). |
| `source` | Case-insensitive substring. |
| `externalId` | Exact (case-insensitive). |
| `id` | Exact numeric id. |
| `isRoot` | `true` or `false`. |
| `dataSetIds` | Resources in any of these data sets. |
| `metadata` | Every key/value given must be present on the resource. |
| `createdTime`, `lastUpdatedTime` | `{ "min": …, "max": … }`, ISO-8601, both bounds inclusive. |

```json
{
  "limit": 100,
  "filter": {
    "name": "pipe%",
    "dataSetIds": [{ "id": 12 }],
    "metadata": { "work_order": "wo-sap-12344" },
    "createdTime": { "min": "2026-01-01T00:00:00Z" }
  }
}
```

`limit` defaults to **1 000** and is capped at **10 000**; a zero, negative or null value
falls back to the default rather than returning nothing.

:::caution `dataSetIds` here takes ids only
On a resource filter each entry is `{"id": 12}` — an `externalId` is not accepted, unlike
the [event filter](./events#filtering), where either works. Resolve the data set's external
id to its numeric id first.
:::

<Tabs groupId="lang">
<TabItem value="java" label="Java">

```java
ResourceRetreiver retriever = new ResourceRetreiver();
retriever.setLimit(100);
retriever.getFilter().setName("pipe%");
retriever.getFilter().setMetadata(Map.of("work_order", "wo-sap-12344"));

DataWrapper<Resource> matches = client.resources().filter(retriever);
```

</TabItem>
<TabItem value="python" label="Python">

```python
matches = client.resources.filter(
    name="pipe%",
    metadata={"work_order": "wo-sap-12344"},
    data_set_ids=[12],
    limit=100)
```

</TabItem>
<TabItem value="rust" label="Rust">

```rust
use dataplatform_rust_sdk::resources::{IdObject, ResourceFilter, ResourceRetreiver};

let retriever = ResourceRetreiver::new(ResourceFilter {
    name: Some("pipe%".into()),
    data_set_ids: Some(vec![IdObject::new(12)]),
    ..Default::default()
}).with_limit(100);

let matches = api.resources.filter(&retriever).await?;
```

</TabItem>
</Tabs>

## Search {#search}

Free-text search across resource **names**. Matching is fuzzy and word-aware: search `pipe`
and you also get `pipes`, `piping`, and multi-word names containing the term. Results are
ordered by relevance, not alphabetically.

A search body may carry the same `filter` block as `POST /resources/filter`, so a free-text
query can be narrowed to a data set or a metadata value. `limit` is capped at **1 000** here,
lower than the 10 000 of `filter`, and `query` must be 3–140 characters.

<Tabs groupId="lang">
<TabItem value="java" label="Java">

```java
ResourceSearch search = new ResourceSearch();
search.setLimit(10);
search.getSearch().setQuery("pump");
DataWrapper<Resource> matches = client.resources().search(search);
```

</TabItem>
<TabItem value="python" label="Python">

```python
form = datahub_sdk.SearchAndFilterForm(query="pump", limit=10)
matches = client.resources.search(form)
```

</TabItem>
<TabItem value="rust" label="Rust">

```rust
use dataplatform_rust_sdk::generic::{SearchAndFilterForm, SearchForm};

let form = SearchAndFilterForm {
    search: Some(SearchForm { name: None, description: None, query: Some("pump".into()) }),
    limit: Some(10),
    filter: None,
};
let matches = api.resources.search(&form).await?;
```

</TabItem>
</Tabs>

Reach for `filter` instead whenever the question is structured — an exact external id, a
metadata value, a data set, a time range. It is faster and its results are predictable.

## Update {#update}

`POST /resources/update` changes fields on resources and relations that already exist.
Identify each node by `id` or `externalId`, each relation by `id`, and name only what you
want changed — anything you leave out keeps its current value.

Each field is an object carrying a verb rather than a bare value, which is what lets "clear
this" be said distinctly from "leave it alone":

| Verb | Applies to | Effect |
| --- | --- | --- |
| `set` | every field | Replace the value. |
| `setNull: true` | nullable fields | Clear the value. |
| `add` | `metadata`, `labels` | Merge entries in, keeping the rest. |
| `remove` | `metadata`, `labels` | Take entries out, keeping the rest. |

```json
{
  "nodes": [
    {
      "externalId": "klp_pipe_ws_a1212_dl",
      "update": {
        "name": { "set": "klp pipe ws-a1212-dl (renamed)" },
        "metadata": { "add": { "inspected_by": "olav" } },
        "labels": { "add": ["CRITICAL"] }
      }
    }
  ],
  "relations": []
}
```

Updatable node fields are `externalId`, `name`, `description`, `source`, `dataSetId`,
`metadata`, `labels` and `geoLocation`. On a relation they are `start`, `end`,
`fromExternalId`, `toExternalId`, `relationship`, `relationshipId`, `description` and
`metadata` — so an edge can be retargeted or retyped in place, subject to the same
[endpoint rules](#create-resources-and-relations) as a create.

Sending both `set` and `setNull` for one field is a `400`: the request is contradictory, so
it is refused rather than resolved by precedence. Changing `externalId` runs it past the
[naming policy](./external-ids#the-naming-policy), which reports violations per item in an
RFC 9457 problem response. The whole batch is **all-or-nothing**.

:::caution A `409` means someone else got there first
Updates are guarded by optimistic locking. If another request changed or deleted the
resource while yours was in flight, you get a `409` with `"cause": "concurrency"` and
**nothing was written** — no partial application to unpick. Re-read the resource with
`byIds` and retry the update against fresh state.

This is worth designing for rather than retrying blindly: two writers doing
`metadata: { add: … }` can both succeed after a re-read, whereas two doing
`metadata: { set: … }` will keep clobbering each other however many times you retry.
:::

All three clients wrap this: `resources().update(nodes, relations)` in Java,
`resources.update([...])` in Python, and `resources.update(&updates)` in Rust, each taking the
per-entry update forms above.

## Delete {#delete}

Delete by id or external id; unknown identifiers are silently skipped. A successful delete
returns `204` with no body, and deleting something already gone is a no-op — so a retried
delete needs no bookkeeping.

Deleting a resource takes **all** of its relationships with it, inbound and outbound. That is
where the one real constraint comes from:

:::caution The graph must stay connected
A delete is rejected with `400` if it would leave any surviving resource unreachable from a
root resource — that is, if it would strand part of the graph. The response names the
resources that would be stranded, so the fix is either to include them in the same delete or
to re-attach them through another path first.

Delete a mid-level node in a hierarchy and this is what you will hit: removing a plant that
holds twenty pumps takes the edges to those pumps with it, stranding all twenty. The check
is what stops a routine cleanup from quietly orphaning half a site.
:::

A single safety-check failure rolls the whole batch back — nothing is deleted unless
everything can be. As with update, a concurrent modification surfaces as a `409` with
nothing removed.

<Tabs groupId="lang">
<TabItem value="java" label="Java">

```java
client.resources().delete(List.of(IdCollection.createFromExternalId("pump_1")));
```

</TabItem>
<TabItem value="python" label="Python">

```python
client.resources.delete(["pump_1"])
```

</TabItem>
<TabItem value="rust" label="Rust">

```rust
api.resources.delete(&vec![IdAndExtId::from_external_id("pump_1")]).await?;
```

</TabItem>
</Tabs>

## Traverse the graph

`fetchRelated` walks the graph outward from a starting resource and returns the
connected sub-graph — a `ResourceNetwork` of `nodes`, the `edges` between them, and
their `labels`. Traversal is **undirected** and bounded by `depth` (`-1` = the whole
connected component), optionally filtered to specific relationship types. Use it for
relationship reasoning — root-cause correlation, blast radius — that a flat lookup
can't do. See [Correlate alarms with the graph](/guides/correlate-alarms).

| Field | Default | Meaning |
| --- | --- | --- |
| `id` / `externalId` | — | Where to start. Supply exactly one. |
| `depth` | `-1` | Hops to follow. `-1` loads the entire connected component. |
| `relationshipTypes` | all | Which edge types the walk may follow. |
| `excludedLabels` | none | Labels the walk neither passes through nor returns — e.g. `["POLICY"]` to keep governance nodes out of an asset view. |
| `limit` | `5000` | Safety cap on nodes loaded. When the component is bigger, the nearest `limit` nodes come back. |

That `limit` is the one to watch: it is a silent truncation, not an error. On a densely
connected site an unbounded `depth` will hit 5 000 nodes long before it runs out of graph,
and what you get back is a *neighbourhood*, not the component you asked for. Bound `depth`
to 1–3 unless you know the graph is sparse.

<Tabs groupId="lang">
<TabItem value="java" label="Java">

```java
// convenience: within `depth` hops of an external id
ResourceNetwork net = client.resources().fetchRelated("sensor_a", 5);

// or the full form, filtering which relationship types to follow
RelatedResourcesForm form = new RelatedResourcesForm();
form.setExternalId("sensor_a");
form.setDepth(5);
form.setRelationshipTypes(List.of("PART_OF"));
ResourceNetwork filtered = client.resources().fetchRelated(form);

net.nodes().forEach(n -> System.out.println(n.getExternalId()));
```

</TabItem>
<TabItem value="python" label="Python">

```python
net = client.resources.fetch_related(
    external_id="sensor_a", depth=5, relationship_types=["PART_OF"])

for node in net.nodes:
    print(node.external_id)
for edge in net.edges:
    print(edge.start, "->", edge.end, edge.relationship_type)
```

</TabItem>
<TabItem value="rust" label="Rust">

```rust
use dataplatform_rust_sdk::resources::RelatedResourcesForm;

let net = api.resources.fetch_related(
    &RelatedResourcesForm::from_external_id("sensor_a")
        .with_depth(5)
        .with_relationship_types(vec!["PART_OF".into()])).await?;

for node in net.nodes() {
    println!("{}", node.external_id);
}
```

</TabItem>
</Tabs>

### The nearest N of a kind {#fetch-nearest}

`POST /resources/fetch-nearest` answers a question `fetchRelated` cannot: *the ten nearest
time-series to this pump*. It walks breadth-first and caps on the number of **matching
end-nodes**, not on hops or total nodes — so "the 10 nearest `TIMESERIES`" is exactly ten
however many intermediate nodes lie between them. You get those nodes plus the sub-graph
connecting them back to the start.

| Field | Default | Meaning |
| --- | --- | --- |
| `id` | — | Where to start. **Numeric id only** — see below. |
| `endLabels` | — | Labels that qualify as a match, e.g. `["TIMESERIES"]`. The walk continues past them. |
| `limit` | `10` | How many matching end-nodes to return. |
| `relationshipTypes` | all | Which edge types the walk may follow. |
| `excludedLabels` | none | Labels never traversed or returned. |

That is the difference worth internalising: with `fetchRelated` you pick a radius and find
out what is inside it, which on an unfamiliar graph is a guess. With `fetch-nearest` you name
what you are looking for and how many you want, and the radius follows.

:::caution `externalId` is accepted but not read
The request form carries an `externalId` field, but this endpoint starts from `id` only —
sending an external id alone gets you a `404`. Resolve it to a numeric id with `byIds` first.
`fetchRelated` takes either.
:::

<Tabs groupId="lang">
<TabItem value="java" label="Java">

```java
FetchNearestResourcesForm form = new FetchNearestResourcesForm();
form.setId(5677892L);                       // numeric id, not external id
form.setEndLabels(List.of("TIMESERIES"));
form.setLimit(10);
form.setExcludedLabels(List.of("POLICY"));

ResourceNetwork nearest = client.resources().fetchNearest(form);
```

</TabItem>
<TabItem value="python" label="Python">

```python
nearest = client.resources.fetch_nearest(
    5677892,                       # numeric id, not external id
    end_labels=["TIMESERIES"],
    limit=10,
    excluded_labels=["POLICY"])
```

</TabItem>
<TabItem value="rust" label="Rust">

```rust
use dataplatform_rust_sdk::resources::FetchNearestResourcesForm;

let nearest = api.resources.fetch_nearest(
    &FetchNearestResourcesForm::from_id(5677892)   // numeric id, not external id
        .with_end_labels(vec!["TIMESERIES".into()])
        .with_limit(10)
        .with_excluded_labels(vec!["POLICY".into()])).await?;
```

</TabItem>
</Tabs>

## What each client covers {#client-coverage}

| Operation | Java | Python | Rust |
| --- | --- | --- | --- |
| Get by numeric id | `resources().getById` | `resources.get_by_id` | `resources.get_by_id` |
| Look up by id / external id | `resources().byIds` | `resources.by_ids` | `resources.by_ids` |
| Create | `resources().create` | `resources.create` | `resources.create` |
| Create relations only (`/edges/create`) | `resources().createRelations` | — | — |
| Update | `resources().update` | `resources.update` | `resources.update` |
| Delete | `resources().delete` | `resources.delete` | `resources.delete` |
| Search | `resources().search` | `resources.search` | `resources.search` |
| Filter | `resources().filter` | `resources.filter` | `resources.filter` |
| Traverse (`fetch-related`) | `resources().fetchRelated` | `resources.fetch_related` | `resources.fetch_related` |
| Nearest N (`fetch-nearest`) | `resources().fetchNearest` | `resources.fetch_nearest` | `resources.fetch_nearest` |
