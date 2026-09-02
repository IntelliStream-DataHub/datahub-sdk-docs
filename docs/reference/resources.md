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
| `geoLocation` | GeoJSON geometry | `Point`, `Polygon`, … Validated on write; stored verbatim. Returned only on [assets](#typed-reads). |
| `isRoot` | boolean | Whether the resource is a navigation root. Deletes are checked against reachability from a root — see [Delete](#delete). Returned only on resources and assets. |
| `relatedResources` | object[] | Read-only view of the graph: `{ id, externalId, relationshipType, direction, edgeId }` per connected node. Populated on the create echo and on `fetch-related` / `fetch-nearest`; empty on `/resources/{id}`, `byids`, `filter` and `search`. |
| `createdTime`, `lastUpdatedTime` | epoch millis | Server-set. A create body may carry them, but they are ignored: the stored values are the server's. |

Labels are how the platform types a node. The type-label (`ASSET`, `TIMESERIES`, `DATASET`,
`POLICY`, `FUNCTION`) is what the create pipeline reads to decide which kind of entity to
build, and free-form labels ride alongside it. That is also why one `/resources/create` call
can hold a mix of node types — a time series next to an asset — rather than needing one
endpoint per type. The same label types what a read returns: see
[Reads come back typed](#typed-reads).

Two of those type-labels are privileged. A create carrying `DATASET` or `POLICY` builds a
data set or a policy, and managing those is stricter than writing data: it requires the
`/datasets/*/write` grant or `DATAHUB_ADMIN`, whichever endpoint the request arrives
through. Without it the call is a `403`, even when you can write the data set named in
`dataSetId`. The same rule guards updating or deleting such a node via `/resources`, and
edges onto a data set node. See [Access control](./datasets#access-control).

:::note Numeric ids cross the wire as JSON strings
`id` and `dataSetId` serialize as `"5677892"`, not `5677892` — ids can exceed the 53-bit
integer a JSON number is safe for in JavaScript. The clients parse them back for you. The same
holds for the ids on an [edge](./edges#body), `start` and `end` included.
:::

## Reads come back typed {#typed-reads}

The read endpoints (`/resources/{id}`, `byids`, `filter`, `search`, `fetch-related`,
`fetch-nearest`) return each node in the shape of its kind, and the type-label inside
`labels` is the discriminator. There is deliberately no separate type property on the wire:
an element whose labels contain `TIMESERIES` *is* the time series shape.

| Type-label present | Shape returned |
| --- | --- |
| `ASSET` | An asset: the body above, `geoLocation` included. |
| `TIMESERIES` | A [time series](./timeseries): `unit`, `unitExternalId`, `valueType`. |
| `DATASET` | A [data set](./datasets). |
| `POLICY` | A policy: `type`, `value`, `deactivated`, `templateId`. |
| `FUNCTION` | A function. |
| none | A plain resource, the body above. |

Three rules govern which fields appear where:

- A time series carries its **full label set**, not only `["TIMESERIES"]`.
- `isRoot` belongs to resources and assets; `geoLocation` belongs to assets. A flat resource
  body naming a `geoLocation` is a `400`: a plain resource has nowhere to store one, so it is
  refused rather than accepted and dropped. Send an `ASSET`-labelled body instead.
- A policy carries no `nodeType` field. The `POLICY` label is the type.

<Tabs groupId="lang">
<TabItem value="java" label="Java">

These calls return `DataWrapper<NodeModel>`, and the concrete class of each item is the
subtype, so pattern-match to reach type-specific fields. `fetchRelated`/`fetchNearest` still
return a `ResourceNetwork`; its `nodes` are `NodeModel` too.

```java
for (NodeModel node : client.resources().filter(retriever).getItems()) {
    if (node instanceof Timeseries ts) {
        System.out.println(ts.getExternalId() + " in " + ts.getUnit());
    }
}
```

</TabItem>
<TabItem value="python" label="Python">

Each item is the same class the type's own endpoint returns, so `isinstance` works and a
time series from `resources.filter()` behaves exactly like one from `timeseries.by_ids()`.
`Asset` and `Policy` are in the set.

```python
from intellistream_datahub_sdk import TimeSeries

for node in client.resources.filter(external_id="pump_*"):
    if isinstance(node, TimeSeries):
        print(node.external_id, node.unit)
```

When you are dispatching from data rather than branching, every node class also carries
`node_type`, one of `asset`, `timeseries`, `function`, `resource`, `dataset`, `policy`:

```python
by_type = {}
for node in client.resources.filter(external_id="pump_*"):
    by_type.setdefault(node.node_type, []).append(node)
```

</TabItem>
<TabItem value="rust" label="Rust">

Reads return `DataWrapper<Node>` (or `GraphDataWrapper<Node>`), where `Node` is an enum with
one variant per type. Match it, or use the accessors for the fields every node shares.

```rust
use intellistream_datahub_sdk::Node;

for node in api.resources.filter(&form).await?.get_items() {
    match node {
        Node::TimeSeries(ts) => println!("{} in {:?}", ts.external_id, ts.unit),
        other => println!("{} ({:?})", other.external_id(), other.kind()),
    }
}
```

`Node` is `#[non_exhaustive]`, so a node type added later is not a breaking change for a
`match` that already has a catch-all arm.

</TabItem>
</Tabs>

Create and update echoes are typed the same way, so an asset updated through
`/resources/update` comes back as an asset carrying its `geoLocation`. One difference on the
update echo: `relatedResources` is left empty on purpose. The request touched only some of the
node's edges, and answering with those alone would be indistinguishable from answering with all
of them. A delete has no echo at all, being a `204` with no body.

## Look up

Fetch by numeric id or external id (you can mix them). Lookup ignores case, so `pump_1` and
`PUMP_1` resolve to the same resource; what comes back keeps the spelling it was created
with. Identifiers that match nothing are **silently omitted** rather than erroring, so
compare the returned items against what you asked for when a miss matters.

<Tabs groupId="lang">
<TabItem value="java" label="Java">

```java
import ai.intellistream.datahub.models.IdCollection;

NodeModel pump = client.resources().getById(5677892).getItems().iterator().next();

DataWrapper<NodeModel> some = client.resources().byIds(List.of(
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
use intellistream_datahub_sdk::generic::IdAndExtId;

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

One request carries at most **1 000 nodes and 1 000 relations**, and one node at most 10 000
characters of `description`, 256 metadata entries, 64 labels and 64 KiB of raw GeoJSON in
`geoLocation`. Past any of those is a `400` before anything is written; the same caps apply on
[update](#update), to `set` and `add` alike. See [Limits & quotas](./limits#field-caps).

A relation may reference a node being created in the same request by its `externalId`, or
point at one that already exists. An edge whose endpoint is neither is a `400` naming the
endpoint it could not resolve.

Two more checks run over the whole batch before anything is written, on **every** node create
endpoint: `/resources`, `/assets`, `/datasets`, `/functions`, `/policies` and `/timeseries`
alike. Both refuse the whole request, so a rejected batch creates nothing.

| Refused | Status | Named in |
| --- | --- | --- |
| An `externalId` already taken in the tenant, or repeated within the same batch. Compared without case. | `409` | `error.duplicated`, one entry per offending id |
| A `dataSetId` that does not exist, or that resolves to a node which is not a data set. | `400` | `error.fields`, one entry per offending id |

```json
{
  "error": {
    "code": 409,
    "message": "A node with that externalId already exists.",
    "duplicated": [{ "externalId": "pump_1" }]
  }
}
```

Use [update](#update) to change an existing resource rather than re-creating it. Access is
decided before either check, so a caller who may not write the data set is told that (`403`)
instead of being handed a `400` about an id they were never allowed to name.

:::note Relationships into data sets and time series are validated
Two endpoint rules apply to every relationship, on create and on update (an update can
retarget a relationship or change its type):

- A relationship **to a data set** must use the `BELONGS_TO` relationship type — that is the
  relationship the data set hierarchy and membership are built from, and anything else is
  rejected with a `400`.
- A **data set → time series** relationship is accepted only when the series has no data set
  yet, or already belongs to that very data set (creating a series inside a data set produces
  exactly that membership relationship). A series in a *different* data set is rejected with a
  `400` — a time series has one data set.
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
import intellistream_datahub_sdk

plant = intellistream_datahub_sdk.Resource(external_id="plant_oslo", name="Oslo Plant", labels=["Plant"])
pump = intellistream_datahub_sdk.Resource(external_id="pump_1", name="Pump 1", labels=["Pump"])
contains = intellistream_datahub_sdk.RelForm.by_external_ids("plant_oslo", "pump_1", "contains")

result = client.resources.create([plant, pump], [contains])
print(len(result.nodes), "resources,", len(result.relations), "relations")
```

</TabItem>
<TabItem value="rust" label="Rust">

```rust
use intellistream_datahub_sdk::resources::Resource;
use intellistream_datahub_sdk::relations::RelForm;

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
where `start` and `end` are the ids of the two nodes (as JSON strings, like every other id).
That is why you send `fromExternalId`/`toExternalId` but read `start`/`end`: the write side
speaks in your identifiers, the read side in the graph's.

Relations are directional. `from` → `to` is the direction you will see when you
[traverse](#traverse-the-graph), so `plant contains pump` and `pump contains plant`
describe different graphs.

### Relations without the nodes {#create-relations}

There are two ways to create a relation and they produce the same edge. The call above sends
nodes and relations together, in one transaction. `POST /edges/create` sends the relations by
themselves, for when both ends already exist and repeating them would be noise — same fields,
same rules, same edges back.

That endpoint, and the rest of the `/edges` surface (reading a relationship back, deleting one
without touching its endpoints, the relationship-type catalogue), has its own page.
[Edges →](./edges)

To disconnect two resources without touching either of them, [delete the edge](./edges#delete).
[Deleting a resource](#delete) is the heavier move: it takes every relation the resource had
with it.

## Filter

`POST /resources/filter` finds resources by structured criteria. Everything you supply is
combined with **AND**.

| Field | Matching |
| --- | --- |
| `name` | Pattern, case-insensitive. `*` and `%` are wildcards, `_` is literal. |
| `source` | Pattern, on the same rules. |
| `externalId` | Pattern, on the same rules. |
| `id` | Exact numeric id. |
| `nodeType` | Restrict to these node types. Omit for every type. |
| `isRoot` | `true` or `false`. |
| `labels` | Resources carrying **all** of these labels. |
| `dataSetId` | Resources in any of these data sets. |
| `metadata` | Every key/value given must be present on the resource. |
| `createdTime`, `lastUpdatedTime` | `{ "min": …, "max": … }`, ISO-8601, both bounds inclusive. |

Each field above except `isRoot`, `labels` and `metadata` takes **either a bare value or an
array**, and the entries of an array are combined with **OR**. That is why they are named in the
singular: `"name": "pipe%"` is the common case, and `"name": ["pipe%", "valve%"]` asks for either.
`labels` and `metadata` are the exceptions, requiring **all** entries to match, and they keep
plural names because adding an entry there narrows the result where adding a `name` widens it.

```json
{
  "limit": 100,
  "filter": {
    "name": "pipe%",
    "dataSetId": [{ "id": 12 }, { "externalId": "data_set_sap" }],
    "metadata": { "work_order": "wo-sap-12344" },
    "createdTime": { "min": "2026-01-01T00:00:00Z" }
  }
}
```

`limit` defaults to **1 000** and is capped at **10 000**; a zero, negative or null value
falls back to the default rather than returning nothing. Results come newest created first
unless ordered otherwise, and page with a cursor — the same contract as
[timeseries](./timeseries#sorting-and-paging), over the same sortable properties.

:::caution A pattern-less value matches exactly, not as a substring
`"name": "pipe"` matches a resource named exactly `pipe`, not every name containing it. Add a
wildcard for the loose match you probably want: `"pipe*"` for a prefix, `"*pipe*"` for a contains
search. The same holds for `source` and `externalId`.
:::

:::note Omitting `dataSetId` and sending `[]` are opposites
Omit the field (or send `null`) for **no data set restriction**. An explicit empty list means
**narrow to no data sets**, which matches nothing. Every other list field treats empty as "no
restriction", so this is the one to watch when you build the filter programmatically.
:::

<Tabs groupId="lang">
<TabItem value="java" label="Java">

```java
ResourceRetreiver retriever = new ResourceRetreiver();
retriever.setLimit(100);
retriever.getFilter().setName(List.of("pipe%"));
retriever.getFilter().setMetadata(Map.of("work_order", "wo-sap-12344"));
retriever.getFilter().setDataSetId(List.of(IdCollection.createFromId(12L)));

DataWrapper<NodeModel> matches = client.resources().filter(retriever);
```

</TabItem>
<TabItem value="python" label="Python">

```python
matches = client.resources.filter(
    name="pipe%",
    metadata={"work_order": "wo-sap-12344"},
    data_set_id=[12],
    limit=100)
```

</TabItem>
<TabItem value="rust" label="Rust">

```rust
use intellistream_datahub_sdk::filters::NodeFilter;
use intellistream_datahub_sdk::generic::IdAndExtId;
use intellistream_datahub_sdk::resources::{ResourceFilter, ResourceRetreiver};

// The criteria every node type shares are a flattened `NodeFilter`, so they nest in Rust even
// though they sit alongside the resource's own fields on the wire.
let retriever = ResourceRetreiver::new(ResourceFilter {
    node: NodeFilter {
        name: Some(vec!["pipe%".into()]),
        metadata: Some([("work_order".into(), Some("wo-sap-12344".into()))].into()),
        ..Default::default()
    },
    data_set_id: Some(vec![IdAndExtId::from_id(12)]),
    ..Default::default()
}).with_limit(100);

let matches = api.resources.filter(&retriever).await?;
```

</TabItem>
</Tabs>

## Search {#search}

Free-text search across **every node type** (assets, timeseries, functions, resources, data sets
and policies), the same breadth as `POST /resources/filter`. The phrase is matched against `name`,
`externalId` and `description`. Matching is fuzzy and word-aware: search `pipe` and you also get
`pipes`, `piping`, and multi-word names containing the term.

Results are **ranked by relevance** (`ts_rank`), strongest match first, with `id` as a tie-break so
equal-scoring rows keep a stable order and repeated identical searches agree. Ranking means the
database scores and sorts every match before applying `limit`, so a very broad phrase costs more
than a narrow one.

`limit` is capped at **1 000** here, lower than the 10 000 of `filter`, and `query` must be
3 to 140 characters. `limit` applies across all node types, and `POLICY` nodes are searched.

### Narrowing with `filter` {#search-filter}

`filter` is optional and takes the same criteria as `POST /resources/filter`. It only ever removes
matches: the phrase decides what the candidates are. `nodeType` and `dataSetId` are applied by the
search query itself, everything else is applied to the hits afterwards.

```json
{
  "search": { "query": "pump" },
  "filter": { "nodeType": ["timeseries"], "dataSetId": [{ "id": "12" }] },
  "limit": 50
}
```

<Tabs groupId="lang">
<TabItem value="java" label="Java">

```java
ResourceSearch search = new ResourceSearch();
search.setLimit(10);
search.getSearch().setQuery("pump");
DataWrapper<NodeModel> matches = client.resources().search(search);
```

</TabItem>
<TabItem value="python" label="Python">

```python
form = intellistream_datahub_sdk.SearchAndFilterForm(query="pump", limit=10)
matches = client.resources.search(form)
```

</TabItem>
<TabItem value="rust" label="Rust">

```rust
use intellistream_datahub_sdk::generic::{SearchAndFilterForm, SearchForm};

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
| `setNull: true` | nullable fields only | Clear the value. `name` and `externalId` are not nullable, so asking to clear either is a `400`. |
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
it is refused rather than resolved by precedence. `setNull` against `name` or `externalId`
is also a `400`, for the same reason a create cannot omit them: every resource has to have
both. Rename with `set` instead.
Changing `externalId` runs it past the
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

Nodes from `fetchRelated` and `fetch-nearest` come back [typed by label](#typed-reads) and
carry the fields the graph mirror holds: `id`, `externalId`, `name`, `description`, `source`,
`dataSetId`, `labels`, `metadata`, `createdTime` and `lastUpdatedTime`, plus `relatedResources`
built from the edges of the network you fetched. By type: `isRoot` on resources and assets,
`geoLocation` on assets, `unit`, `unitExternalId` and `valueType` on time series, and
`isDeactivated` on policies. Fetch by id when you need a field outside that list.

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
use intellistream_datahub_sdk::resources::RelatedResourcesForm;

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
time series to this pump*. It walks breadth-first and caps on the number of **matching
end-nodes**, not on hops or total nodes — so "the 10 nearest `TIMESERIES`" is exactly ten
however many intermediate nodes lie between them. You get those nodes plus the sub-graph
connecting them back to the start.

| Field | Default | Meaning |
| --- | --- | --- |
| `id` / `externalId` | — | Where to start. Supply exactly one, as for `fetchRelated`. |
| `endLabels` | — | Labels that qualify as a match, e.g. `["TIMESERIES"]`. The walk continues past them. |
| `limit` | `10` | How many matching end-nodes to return. |
| `relationshipTypes` | all | Which edge types the walk may follow. |
| `excludedLabels` | none | Labels never traversed or returned. |

That is the difference worth internalising: with `fetchRelated` you pick a radius and find
out what is inside it, which on an unfamiliar graph is a guess. With `fetch-nearest` you name
what you are looking for and how many you want, and the radius follows.

The endpoint resolves an `externalId` for you, and so does the Java form. The Python and Rust
clients build the request from a numeric `id` only, so there resolve an external id with
`by_ids` first when that is all you have.

<Tabs groupId="lang">
<TabItem value="java" label="Java">

```java
FetchNearestResourcesForm form = new FetchNearestResourcesForm();
form.setExternalId("pump_1");               // or form.setId(5677892L)
form.setEndLabels(List.of("TIMESERIES"));
form.setLimit(10);
form.setExcludedLabels(List.of("POLICY"));

ResourceNetwork nearest = client.resources().fetchNearest(form);
```

</TabItem>
<TabItem value="python" label="Python">

```python
nearest = client.resources.fetch_nearest(
    5677892,                       # the Python client takes the numeric id
    end_labels=["TIMESERIES"],
    limit=10,
    excluded_labels=["POLICY"])
```

</TabItem>
<TabItem value="rust" label="Rust">

```rust
use intellistream_datahub_sdk::resources::FetchNearestResourcesForm;

let nearest = api.resources.fetch_nearest(
    &FetchNearestResourcesForm::from_id(5677892)   // the Rust client takes the numeric id
        .with_end_labels(vec!["TIMESERIES".into()])
        .with_limit(10)
        .with_excluded_labels(vec!["POLICY".into()])).await?;
```

</TabItem>
</Tabs>

## Export and import a graph {#graph-transfer}

Two endpoints move a whole connected component between tenants or environments as one file.
Export starts from one resource, walks outward with no depth limit, and writes every reachable
node and every relationship between them; import recreates them somewhere else. The file
references everything by `externalId` and never by numeric id, which is what makes it
portable: numeric ids are database identities and do not survive the transfer.

| Endpoint | Body | Returns |
| --- | --- | --- |
| `GET /resources/export/{id}` | none; `id` is the numeric id of the resource to start from | The file, `application/octet-stream`, as an attachment named `<externalId>.dhgraph` |
| `POST /resources/import` | the file, verbatim, as `application/octet-stream` | A JSON summary of what was created and what was skipped |

The file is a gzip-compressed binary, streamed on the way out and decoded incrementally on the
way in, so neither side holds it whole in memory. Treat it as opaque: the format is versioned
by the server and is not part of the API contract.

**What the file carries.** Per node: `externalId`, `name`, `description`, `source`, `isRoot`,
`labels`, `metadata`, the data set it belongs to (by that data set's `externalId`) and, for an
`ASSET`, a point `geoLocation`; other geometries are not carried. Per relationship: both
endpoints by `externalId`, the type, `description`, `metadata` and the data set. A data set
node inside the component is exported as a node like any other, ahead of everything that
references it.

**What it does not carry.** A time-series's `unit` and `valueType`, so a time-series node in
the file cannot be created on import and is reported instead; datapoints; events; files.

### Export {#graph-export}

Export needs read access to the data set of the starting resource, and nothing more: the walk
is [gated on the starting node only](./datasets#access-control), so the file holds every node
the component reaches. A component of more than **2 000 000 nodes** or **2 000 000
relationships** is refused with a `400` naming the limit, and nothing is exported partially.

| Status | Meaning |
| --- | --- |
| `200` | The file. |
| `404` | No such resource, or the caller may not read it. |
| `400` | The component is over the export limit. |

### Import {#graph-import}

Import replays the file through the same pipeline as [create](#create-resources-and-relations),
so everything a create does, an import does: the [naming policy](./external-ids#the-naming-policy)
is applied, the data set ACLs are checked, and each committed segment is published to the
message bus and mirrored into the graph. The caller needs write access to every data set a
node or a relationship lands in, and the all-data-sets grant for a node that arrives with no
data set and for any `DATASET` node in the file. A denial is a `403`.

**Skipped, not refused.** A node whose `externalId` already exists in the tenant is left as it
is, and so is a relationship already present between the same two endpoints with the same
type. Importing a file back into the tenant it came from is therefore a no-op, and
re-uploading after a failure is safe. Time-series nodes are skipped and listed by
`externalId`, and the relationships touching them are skipped with them; to keep those, create
the series through [`/timeseries`](./timeseries#create-a-series) first and import the same file
again. A data set reference is resolved by `externalId` against the data sets in the file and
those already in the tenant; one that resolves nowhere is dropped, and the node is created
without a data set.

**Segments.** The upload is committed as it streams in, one transaction per 50 000 objects,
nodes first and relationships after, so memory stays flat however large the file. Each segment
is atomic on its own: a failure keeps the segments already committed and rejects the rest.
Because import skips what already exists, re-upload the same file once the cause is fixed and
it fast-forwards through the committed segments and resumes where it stopped. The response
counts the segments committed.

```json
{
  "nodesCreated": 4210,
  "relationsCreated": 4209,
  "nodesSkippedExisting": 3,
  "nodesSkippedTimeseries": ["pump_1_vibration", "pump_1_temperature"],
  "relationsSkipped": 2,
  "dataSetReferencesDropped": 0,
  "segments": 1,
  "warnings": []
}
```

`warnings` carries [naming-policy warnings](./external-ids#the-naming-policy) exactly as a
create does, and a naming-policy refusal is the same `400` problem body a create returns.

| Status | Meaning |
| --- | --- |
| `200` | The summary above, also when everything was skipped. |
| `400` | Not a readable graph file, a naming-policy refusal, or a value that failed validation. |
| `403` | A data set the caller may not write to. |
| `413` | Over a transfer limit: more than 2 000 000 nodes or relationships in the file, or a file larger than 512 MB. Nothing is imported. |

:::caution The general request-body cap applies first
`POST /resources/import` is not exempt from the [request body size](./limits#request-body-size)
cap, which is 4 MiB unless the deployment raises `datahub.limits.max-body-bytes`. A larger
file is refused with that cap's own `413` (`.../errors/request-too-large`) before the import
reads it, so the 512 MB figure above is the format's ceiling, not what a default deployment
accepts. The upload's size also counts against the tenant's daily ingest byte quota.
:::

No client wraps the pair. Call them over HTTP with the bearer token the client already holds:

```bash
curl -fsS -H "Authorization: Bearer $TOKEN" \
  -o plant_oslo.dhgraph "$API/resources/export/5677892"

curl -fsS -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/octet-stream" \
  --data-binary @plant_oslo.dhgraph "$API/resources/import"
```

Against the [rate-limit](./limits#rate-limits) budget, export is a read and import a write.

## The `/assets` endpoints {#assets}

An **asset** is the node type that can be a navigation root and the only one that carries a
`geoLocation`. It has its own endpoint family, and every call in it is the pipeline above with
the `ASSET` type pinned: the same ACLs, the same [naming policy](./external-ids#the-naming-policy),
the same [create checks](#create-resources-and-relations), the same status codes. Reach for it
when a call should only ever see assets, and for `/resources` when one call carries or returns
several node types.

| Endpoint | Behaves as | Worth knowing |
| --- | --- | --- |
| `POST /assets/create` | [create](#create-resources-and-relations) | Nodes only, no `relations` array. `201`, and the echo is asset-shaped. `labels` may be omitted: `ASSET` is added for you. |
| `GET /assets/{id}` | [look up](#look-up) | One asset, wrapped in `items` like every other read. |
| `POST /assets/byids` | [look up](#look-up) | Ids that are missing, are not assets, or are not readable are omitted rather than failing the call. |
| `POST /assets/filter` | [filter](#filter) | The same criteria, the same paging. A `nodeType` in the body is replaced, see below. |
| `POST /assets/search` | [search](#search) | Same replacement, and the `filter` block is applied exactly as on [`/resources/search`](#search-filter). |
| `POST /assets/update` | [update](#update) | Takes `nodes` and `relations` exactly as `/resources/update` does. |
| `POST` or `DELETE /assets/delete` | [delete](#delete) | `204`, and the same [connectivity check](#delete). |

```http
POST /assets/create
{
  "items": [
    {
      "externalId": "plant_oslo",
      "name": "Oslo Plant",
      "labels": ["Plant"],
      "isRoot": true,
      "geoLocation": { "type": "Point", "coordinates": [10.75, 59.91] }
    }
  ]
}
```

:::caution `nodeType` in the body is replaced, not merged
A `nodeType` you send to `/assets/filter` or `/assets/search` is overwritten with `asset`.
`nodeType` entries are combined with **OR**, so honouring a supplied `["timeseries"]` would
*widen* a request made to `/assets` into a mixed query instead of narrowing it. Ask
`/resources/filter` when you want a mixed set.
:::

:::note A `404` here answers three questions at once
`GET /assets/{id}` replies the same way to an id that does not exist, an id belonging to a node
of some other type, and an asset in a data set you may not read. That is deliberate: a
distinguishable `403` would confirm that an id exists.
:::

## The `/functions` endpoints {#functions}

A **function** is a plain node distinguished by its `FUNCTION` label, with the same shape as a
resource. Its family is `POST /functions/create`, `GET /functions/list`, `GET /functions/{id}`,
`POST /functions/update` and `POST` or `DELETE /functions/delete`, on the same shared pipeline.
`GET /functions/list` takes no filter: the inventory is expected to be small.

`GET /functions/{id}` returns the one function wrapped in `items`, and reports a function
you may not read as missing (`404`) rather than forbidden, exactly as `GET /assets/{id}` does.

The Java client has no `assets()` or `functions()` service, so reach for the endpoints there.
Creating an asset through `resources().create` with an `ASSET` label is the same pipeline and
gives you the same asset back.

## What each client covers {#client-coverage}

| Operation | Java | Python | Rust |
| --- | --- | --- | --- |
| Get by numeric id | `resources().getById` | `resources.get_by_id` | `resources.get_by_id` |
| Look up by id / external id | `resources().byIds` | `resources.by_ids` | `resources.by_ids` |
| Create | `resources().create` | `resources.create` | `resources.create` |
| Update | `resources().update` | `resources.update` | `resources.update` |
| Delete | `resources().delete` | `resources.delete` | `resources.delete` |
| Search | `resources().search` | `resources.search` | `resources.search` |
| Filter | `resources().filter` | `resources.filter` | `resources.filter` |
| Traverse (`fetch-related`) | `resources().fetchRelated` | `resources.fetch_related` | `resources.fetch_related` |
| Nearest N (`fetch-nearest`) | `resources().fetchNearest` | `resources.fetch_nearest` | `resources.fetch_nearest` |
| [Export / import a graph](#graph-transfer) | HTTP only | HTTP only | HTTP only |

Relations have their own client surface in all three clients — `edges()` in Java, `edges` in
Python and Rust. [Edges → client coverage](./edges#client-coverage)
