---
sidebar_position: 7
title: Units
---
import Tabs from '@theme/Tabs';
import TabItem from '@theme/TabItem';

# Units

Units of measure (read-only reference data). The endpoints are `GET /units`,
`GET /units/{externalId}` and `POST /units/byids`.

## The unit object {#body}

| Field | Type | Notes |
| --- | --- | --- |
| `id` | number | Crosses the wire as a JSON string, like every other id. |
| `externalId` | string, 3–256 | The catalogue key, `<quantity>_<unit>` in snake_case: `temperature_deg_c`, `pressure_bar`, `mass_flow_rate_kghr`. This is what a series' `unitExternalId` names. |
| `name` | string, 1–64 | Short code (`DEG_C`). |
| `longName` | string | `degree Celsius`. |
| `symbol` | string | `°C`. |
| `description` | string | Prose. |
| `aliasNames` | string[] | Other spellings (`C`, `degC`). |
| `quantity` | string | What it measures (`Temperature`). |
| `conversion` | `{ multiplier, offset }` | To the quantity's base unit. |
| `source`, `sourceReference` | string | Where the definition comes from (`qudt.org` and its URL). |

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

by_ext = client.units.by_external_ids("temperature_deg_c")
by_id = client.units.by_ids([intellistream_datahub_sdk.IdCollection(id=7)])
```

</TabItem>
<TabItem value="rust" label="Rust">

```rust
use intellistream_datahub_sdk::generic::{DataWrapper, IdAndExtId};

let by_ext = api.units.by_external_id("temperature_deg_c").await?;
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
