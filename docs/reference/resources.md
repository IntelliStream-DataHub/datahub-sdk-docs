---
sidebar_position: 2
title: Resources
---
import Tabs from '@theme/Tabs';
import TabItem from '@theme/TabItem';

# Resources

Hierarchical, asset-like entities and the relationships between them. Create resources
and the edges between them in one call; the server returns the persisted graph.

## Look up

Fetch by numeric id or external id (you can mix them).

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

## Create resources and relations

Pass the resource forms (nodes) and the relation forms (edges); the call returns the
created graph — nodes plus server-assigned edges. Each resource needs **at least one
label** (a type tag such as `Plant` or `Pump`) — a node with none is rejected with
`400 resource.needs.at.least.one.label`. Labels and relationship types are both
upper-cased by the server.

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

## Search

Free-text / fuzzy search across resources.

<Tabs groupId="lang">
<TabItem value="java" label="Java">

```java
ResourceSearch search = new ResourceSearch();
search.setLimit(10);
search.getSearch().setQuery("pump");
DataWrapper<Resource> matches = client.resources().search(search);
```

Use `filter(new ResourceRetreiver())` for structured filters (labels, metadata, parent).

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

## Delete

Delete by id or external id; returns the removed graph.

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
