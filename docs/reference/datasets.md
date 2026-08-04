---
sidebar_position: 5
title: Datasets
---
import Tabs from '@theme/Tabs';
import TabItem from '@theme/TabItem';

# Datasets

Logical groupings of resources and time-series. Datasets can be nested (a dataset can
belong to a parent dataset), and that hierarchy is live in queries: filtering time-series
by a dataset also matches everything beneath it.
[Filter series →](./timeseries#filter-series)

:::note External ids are stored exactly as you send them
The server does not rewrite a dataset external id: `Plant-A` stays `Plant-A`. Some clients
*derive* one from the name as a convenience (the Rust `Dataset::new` below), and that
derivation is snake_case — but it is a client-side default, not a server rule.

Uniqueness and lookup both ignore case, so `plant_a` collides with `PLANT_A` and either
spelling finds the same dataset. Datasets are also subject to the
[naming policy](./external-ids#the-naming-policy) if an administrator has set one.
[External ids & naming →](./external-ids)
:::

## Create

<Tabs groupId="lang">
<TabItem value="java" label="Java">

```java
DataSetModel dataset = new DataSetModel();
dataset.setExternalId("plant_a");
dataset.setName("Plant A");

client.datasets().create(List.of(dataset));
```

</TabItem>
<TabItem value="python" label="Python">

```python
import datahub_sdk

dataset = datahub_sdk.Dataset(external_id="plant_a", name="Plant A")
client.datasets.create([dataset])
```

</TabItem>
<TabItem value="rust" label="Rust">

```rust
use dataplatform_rust_sdk::datasets::Dataset;

// external_id is derived as snake_case of the name → "plant_a"
let dataset = Dataset::new("Plant A".into());
api.datasets.create(&vec![dataset]).await?;
```

</TabItem>
</Tabs>

## Look up & delete

<Tabs groupId="lang">
<TabItem value="java" label="Java">

```java
DataWrapper<DataSetModel> some = client.datasets()
        .byIds(List.of(IdCollection.createFromExternalId("plant_a")));

client.datasets().delete(List.of(IdCollection.createFromExternalId("plant_a")));
```

</TabItem>
<TabItem value="python" label="Python">

```python
some = client.datasets.by_ids(["plant_a"])
client.datasets.delete(["plant_a"])
```

</TabItem>
<TabItem value="rust" label="Rust">

```rust
use dataplatform_rust_sdk::generic::IdAndExtId;

let some = api.datasets.by_ids(&vec![IdAndExtId::from_external_id("plant_a")]).await?;
api.datasets.delete(&vec![IdAndExtId::from_external_id("plant_a")]).await?;
```

</TabItem>
</Tabs>

The Java client additionally offers `list(DataSetRetreiver)`, `search(DataSetSearch)` and
`update(List<DataSetForm>)`; the Rust client offers `filter(&DatasetFilter)` and
`search(&DatasetSearch)`.
