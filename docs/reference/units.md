---
sidebar_position: 7
title: Units
---
import Tabs from '@theme/Tabs';
import TabItem from '@theme/TabItem';

# Units

Units of measure (read-only reference data).

## List all units

<Tabs groupId="lang">
<TabItem value="java" label="Java">

```java
DataWrapper<UnitModel> units = client.units().list();
for (UnitModel unit : units.getItems()) {
    System.out.println(unit.getExternalId() + " — " + unit.getName() + " (" + unit.getSymbol() + ")");
}
```

</TabItem>
<TabItem value="python" label="Python">

```python
for unit in client.units.list():
    print(unit.external_id, unit.name, unit.symbol)
```

</TabItem>
<TabItem value="rust" label="Rust">

```rust
for unit in api.units.list().await?.get_items() {
    println!("{} — {} ({})", unit.external_id, unit.name, unit.symbol);
}
```

</TabItem>
</Tabs>

## Look up

<Tabs groupId="lang">
<TabItem value="java" label="Java">

`byIds` takes `UnitModel`s with their `id` set:

```java
UnitModel lookup = new UnitModel();
lookup.setId(7L);

DataWrapper<UnitModel> result = client.units().byIds(List.of(lookup));
```

</TabItem>
<TabItem value="python" label="Python">

```python
import intellistream_datahub_sdk

by_ext = client.units.by_external_ids("celsius")
by_id = client.units.by_ids([intellistream_datahub_sdk.IdCollection(id=7)])
```

</TabItem>
<TabItem value="rust" label="Rust">

```rust
use intellistream_datahub_sdk::generic::{DataWrapper, IdAndExtId};

let by_ext = api.units.by_external_id("celsius").await?;
let by_id = api.units.by_ids(&DataWrapper::from(vec![IdAndExtId::from_id(7)])).await?;
```

</TabItem>
</Tabs>

## What each client covers {#client-coverage}

| Operation | Java | Python | Rust |
| --- | --- | --- | --- |
| List all | `units().list` | `units.list` | `units.list` |
| Look up by id | `units().byIds` | `units.by_ids` | `units.by_ids` |
| Look up by external id | HTTP | `units.by_external_ids` | `units.by_external_id` |

The unit catalogue is read-only in every client: units are platform-managed, not tenant data.
