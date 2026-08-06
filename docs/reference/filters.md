---
sidebar_position: 9
title: Filters
---
import Tabs from '@theme/Tabs';
import TabItem from '@theme/TabItem';

# Filters

Queries are built as filter objects rather than method arguments.

## RetrieveFilter

One series over a time window — retrieving from several means passing several filters.
Used by [Retrieve datapoints](./timeseries.md#retrieve-datapoints).

| Field | Type | Meaning |
| --- | --- | --- |
| `externalId` | string | External id of the series. Required unless `id` is set. Named `ts` in Python. |
| `id` | integer | Numeric id of the series. Alternative to `externalId`. |
| `start` | timestamp | Start of the window, inclusive. |
| `end` | timestamp | End of the window, exclusive. |
| `limit` | integer | Maximum datapoints returned. |

<Tabs groupId="lang">
<TabItem value="java" label="Java">

```java
RetrieveFilter series = new RetrieveFilter();
series.setExternalId("engine_temperature");
series.setStart(ZonedDateTime.now().minusHours(1));
series.setEnd(ZonedDateTime.now());
series.setLimit(1000);
```

</TabItem>
<TabItem value="python" label="Python">

```python
rf = datahub_sdk.RetrieveFilter(
    ts="engine_temperature",
    start=pd.Timestamp.now(tz="UTC") - pd.Timedelta(hours=1),
    end=pd.Timestamp.now(tz="UTC"),
    limit=1000)
```

</TabItem>
<TabItem value="rust" label="Rust">

```rust
let filter = RetrieveFilter {
    external_id: Some("engine_temperature".into()),
    start: Some(Utc::now() - chrono::Duration::hours(1)),
    end: Some(Utc::now()),
    limit: Some(1000),
    ..Default::default()
};
```

</TabItem>
</Tabs>

## EventFilter

Used by [Query](./events.md#query). All fields optional; predicates are exact,
case-sensitive and AND-combined. `type`, `subType` and `source` are tenant-defined, so
discover values rather than guess them.

| Field | Layer | Meaning |
| --- | --- | --- |
| `limit` | outer | Maximum events returned. |
| `type` | basic | Exact match on event type. |
| `subType` | basic | Exact match on event subtype. |
| `source` | basic | Exact match on originating system. |
| `status` | basic | Exact match on lifecycle status. |
| `externalIdPrefix` | basic | Prefix match on `externalId`. |
| `start` / `end` | basic | Window on `eventTime`, `start` inclusive, `end` exclusive. |
| `dataSetIds` | basic | Restrict to these data sets — see below. |

<Tabs groupId="lang">
<TabItem value="java" label="Java">

```java
EventRetreiver retriever = new EventRetreiver();
retriever.setLimit(50);
retriever.getFilter().setType("alarm");
```

</TabItem>
<TabItem value="python" label="Python">

```python
filter = datahub_sdk.EventFilter(
    basic_filter=datahub_sdk.BasicEventFilter(type="alarm"),
    limit=50)
```

</TabItem>
<TabItem value="rust" label="Rust">

```rust
use dataplatform_rust_sdk::filters::{BasicEventFilter, EventFilter};

let filter = EventFilter::default()
    .set_filter(BasicEventFilter { r#type: Some("alarm".into()), ..Default::default() })
    .set_limit(50)
    .build();
```

</TabItem>
</Tabs>

### Restricting to data sets

`dataSetIds` takes [`IdCollection`](#idcollection) references. Each matches that data set
exactly — it does not extend down the hierarchy, so list every one you want. Omitting the
field applies no restriction; an explicit `[]` matches nothing.

```java
retriever.getFilter().setDataSetIds(List.of(
        IdCollection.createFromId(43L),
        IdCollection.createFromExternalId("data_set_sap")));
```

## DatasetFilter

Rust exposes `filter(&DatasetFilter)` and `search(&DatasetSearch)`; Java the equivalent
`list(DataSetRetreiver)` and `search(DataSetSearch)`. See [Datasets](./datasets.md).

## IdCollection

`byIds` and `delete` take id references, so one call can mix numeric and external ids.

<Tabs groupId="lang">
<TabItem value="java" label="Java">

```java
import ai.intellistream.datahub.models.IdCollection;

List.of(IdCollection.createFromExternalId("pump_1"),
        IdCollection.createFromId(5677892));
```

</TabItem>
<TabItem value="python" label="Python">

```python
["pump_1", 5677892]   # entity objects, external-id strings and numeric ids
```

</TabItem>
<TabItem value="rust" label="Rust">

```rust
use dataplatform_rust_sdk::generic::IdAndExtId;

vec![IdAndExtId::from_external_id("pump_1"),
     IdAndExtId::from_id(5677892)];
```

</TabItem>
</Tabs>

Over the wire that is `[{"id": 43}, {"externalId": "data_set_sap"}]`. Browser clients
should send ids as strings, since they exceed JavaScript's safe integer range.
