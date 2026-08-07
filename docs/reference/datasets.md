---
sidebar_position: 4
title: Datasets
---
import Tabs from '@theme/Tabs';
import TabItem from '@theme/TabItem';

# Datasets

Logical groupings of resources and time-series.

:::note External ids are canonicalized
A dataset external id is normalized to snake_case (lower-cased, special characters →
`_`), so a name of `"Plant A"` yields the external id `plant_a`. Use the canonical form
when you look the dataset up again.
:::

## Dataset fields

| Field | Type | Meaning |
| --- | --- | --- |
| `externalId` | string | **Required.** Stable snake_case id, 3–256 chars. Derived from `name` in Rust. |
| `name` | string | **Required.** Display name, 3–512 chars. |
| `description` | string | Optional description. |
| `metadata` | map | String-to-string. |
| `policies` | list&lt;string&gt; | External ids of policy resources to apply. |
| `connectedDataSets` | list&lt;integer&gt; | Ids of datasets this one is part of. |

`labels` is inherited but defaulted to `DATASET`, so you never set it here.

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
`update(List<DataSetForm>)`; the Rust client offers
[`filter(&DatasetFilter)`](./filters.md#datasetfilter) and `search(&DatasetSearch)`.
