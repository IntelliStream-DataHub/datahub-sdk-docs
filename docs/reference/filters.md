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
| `start` / `end` | timestamp | The time window. |
| `limit` | integer | Maximum datapoints returned. Defaults to `0`. |
| `aggregates` | list&lt;string&gt; | Aggregate functions to compute instead of raw points. |
| `granularity` | string | Bucket size for `aggregates` (e.g. `1h`). |
| `includeOutsidePoints` | boolean | Include the points bracketing the window. Defaults to `false`. |
| `mergeDuplicates` | boolean | Collapse points sharing a timestamp. Defaults to `false`. |
| `cursor` | string | Continuation token from a previous page. |
| `minCreatedTime` / `maxCreatedTime` | integer | Epoch-millis bounds on creation time. |
| `minLastUpdatedTime` / `maxLastUpdatedTime` | integer | Epoch-millis bounds on last update. |

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
| `limit` | outer | Maximum events returned. Defaults to `100`. |
| `sort` | outer | Sort `property`, `order` and `nulls` handling. |
| `cursor` | outer | Page continuation: `<eventTime epoch millis>_<event id>`. |
| `advancedFilter` | outer | Advanced predicate tree, for queries the basic filter can't express. |
| `id` | basic | Exact match on the event id. |
| `type` | basic | Exact match on event type. |
| `subType` | basic | Exact match on event subtype. |
| `source` | basic | Exact match on originating system. |
| `status` | basic | Exact match on lifecycle status. |
| `externalIdPrefix` | basic | Prefix match on `externalId`, 3–256 chars. |
| `eventTime` | basic | `{min, max}` window on when the event occurred. |
| `createdTime` / `lastUpdatedTime` | basic | `{min, max}` windows on record timestamps. |
| `metadata` | basic | Match metadata keys, each with an optional value. |
| `relatedResources` | basic | The event must relate to **all** of these resources. |
| `dataSetIds` | basic | Restrict to these data sets — see below. |
| `cursor` | basic | Fetches beyond 10 000 events; when set, all other predicates are ignored. |

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

| Field | Meaning |
| --- | --- |
| `externalIdPrefix` | Prefix match on `externalId`, max 255 chars. |
| `metadata` | Match metadata keys, each with an optional value. |
| `createdTime` / `lastUpdatedTime` | `{min, max}` windows on record timestamps. |
| `writeProtected` | Restrict to write-protected datasets. |
| `deactivated` | Restrict to deactivated datasets. |

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

Over the wire that is `[{"id": "43"}, {"externalId": "data_set_sap"}]` — ids serialize as
JSON strings, since 64-bit values exceed JavaScript's safe integer range.
