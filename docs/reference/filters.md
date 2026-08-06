---
sidebar_position: 9
title: Filters
---
import Tabs from '@theme/Tabs';
import TabItem from '@theme/TabItem';

# Filters

Queries are expressed as filter objects rather than method arguments, so a query can be
built up, passed around and reused. This page is the field reference for each filter
type and for the id reference they share; the service pages show them in use.

## RetrieveFilter

Selects datapoints from one series over a time window — see
[Retrieve datapoints](./timeseries.md#retrieve-datapoints) for the surrounding call. One
filter addresses one series, so retrieving from several means passing several filters.

| Field | Type | Meaning |
| --- | --- | --- |
| `externalId` | string | External id of the series. Required unless `id` is set. |
| `id` | integer | Numeric id of the series. Alternative to `externalId`. |
| `start` | timestamp | Start of the window, inclusive. |
| `end` | timestamp | End of the window, exclusive. |
| `limit` | integer | Maximum datapoints returned. |

:::note The series field is named differently in Python
Java and Rust name it `externalId`/`external_id`; the Python constructor takes `ts=`,
which accepts an external-id string. Same field, different spelling.
:::

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

Selects events — see [Query](./events.md#query) for the surrounding call. It has two
layers: an outer filter carrying query-wide options like `limit`, and an inner basic
filter carrying the field predicates. Every field is optional; an empty filter matches
everything you are allowed to read.

Predicates are exact and case-sensitive, and combine with AND. Because `type`, `subType`
and `source` are tenant-defined free-form strings, discover the values in use rather
than guessing at them.

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

`dataSetIds` takes a list of [`IdCollection`](#idcollection) references, naming each data
set by id or external id:

```java
retriever.getFilter().setDataSetIds(List.of(
        IdCollection.createFromId(43L),
        IdCollection.createFromExternalId("data_set_sap")));
```

A reference matches that data set **exactly** — unlike a read grant, it does not extend
to data sets beneath it in the hierarchy, so list every one you want. Omitting the field
applies no restriction (you still only see data sets you may read), whereas an explicit
empty list `[]` narrows to nothing and matches no events.

## DatasetFilter

Selects datasets. The Rust client exposes `filter(&DatasetFilter)` and
`search(&DatasetSearch)`; the Java client offers the equivalent `list(DataSetRetreiver)`
and `search(DataSetSearch)`. See [Datasets](./datasets.md) for the surrounding calls.

## IdCollection

Most `byIds` and `delete` calls take a list of id references rather than raw ids, so one
call can mix numeric ids and external ids freely. Java and Rust have an explicit type for
this; Python takes the strings and integers directly.

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
# entity objects, external-id strings and numeric ids are all accepted
["pump_1", 5677892]
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

:::note Send large ids as strings from browsers
Numeric ids exceed JavaScript's safe integer range, so browser clients should send them
as strings. Over the wire an `IdCollection` list is
`[{"id": 43}, {"externalId": "data_set_sap"}]`.
:::
