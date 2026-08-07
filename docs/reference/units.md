---
sidebar_position: 6
title: Units
---
import Tabs from '@theme/Tabs';
import TabItem from '@theme/TabItem';

# Units

Units of measure (read-only reference data). The catalogue is managed centrally and small
— typically a few hundred entries.

## Unit fields

| Field | Type | Meaning |
| --- | --- | --- |
| `id` | integer | Server-assigned numeric id. |
| `externalId` | string | **Required.** Stable id, 3–256 chars — use as a series' `unitExternalId`. |
| `name` | string | **Required.** Display name, 1–64 chars (e.g. `Celsius`). |
| `longName` | string | Full name, 1–256 chars. |
| `symbol` | string | Symbol, 1–32 chars (e.g. `°C`). |
| `quantity` | string | Physical quantity measured (e.g. `Temperature`). |
| `aliasNames` | list&lt;string&gt; | Alternative names (e.g. `["c", "C", "Celsius"]`). |
| `conversion` | object | Multiplier and offset for converting between units. |
| `description` | string | Optional description. |
| `source` / `sourceReference` | string | Specification source (e.g. `qudt.org`) and its URL. |

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
import datahub_sdk

by_ext = client.units.by_external_ids("celsius")
by_id = client.units.by_ids([datahub_sdk.IdCollection(id=7)])
```

</TabItem>
<TabItem value="rust" label="Rust">

```rust
use dataplatform_rust_sdk::generic::{DataWrapper, IdAndExtId};

let by_ext = api.units.by_external_id("celsius").await?;
let by_id = api.units.by_ids(&DataWrapper::from(vec![IdAndExtId::from_id(7)])).await?;
```

</TabItem>
</Tabs>
