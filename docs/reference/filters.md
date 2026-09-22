---
sidebar_position: 2.5
title: Filters
---
import Tabs from '@theme/Tabs';
import TabItem from '@theme/TabItem';

# Filters

Every collection read takes a filter object rather than a list of query parameters. The same
few shapes recur across the node types, so this page describes the shared grammar once; the
per-endpoint pages say which filter each call takes and what it returns.

The examples here only build filters. Nothing on this page calls the API, so none of it needs
a seeded tenant; [Events](./events#filtering) has the worked queries.

## How a field is shaped {#field-shape}

A filter field that ORs its entries is named in the **singular** and takes either a bare value
or a list, so `"type": "Alarm"` and `"type": ["Alarm", "Warning"]` are both valid and mean
"either". The two exceptions, `labels` and `relatedResources`, keep plural names because their
entries **AND** together: a second entry narrows the result where a second `type` would widen
it. `metadata` behaves the same way.

Text entries are literal or wildcard:

| Character | Meaning |
| --- | --- |
| `*` | Any run of characters |
| `%` | The same, so a caller who thinks in SQL is not surprised |
| `_` | **Literal.** External ids are built out of underscores, so `sap_work_orders` means that id and not `sapXwork_orders` |

One list mixes both freely — `["sap_work_orders", "plant_*", "*_archive"]` is exact lookup,
prefix search and contains search in a single call. Entries without a wildcard resolve through
an index; only the patterns need a scan, so an exact lookup keeps its index however many
patterns share the list. Every OR'd text list is capped at 1000 entries.

Case sensitivity differs in one place, and it is worth knowing which:

| Filter | Literal entry | Wildcard entry |
| --- | --- | --- |
| Node filters (`externalId`, `name`, `source`) | Case-**in**sensitive | Case-insensitive |
| `EventFilter.externalId` | Case-**sensitive** | Case-insensitive, through `ILIKE` |

Events are the odd one out because every event writer hashes the external id verbatim, so the
stored key for `shift_report_1` is not the key for `SHIFT_REPORT_1`; nodes lowercase before
hashing and match either. Writing the entry as a wildcard — `"SHIFT_REPORT_1*"` — is the way to
ask an event question case-insensitively.

## The node filter family {#node-filters}

Every node filter inherits the same eight fields.

| Field | Type | Combines | Meaning |
| --- | --- | --- | --- |
| `id` | list&lt;long&gt; | OR | Node ids. Serialised as strings on the wire, so a JavaScript client cannot round them through a double. |
| `externalId` | list&lt;string&gt; | OR | Pattern list over external ids. |
| `name` | list&lt;string&gt; | OR | Pattern list over names. |
| `source` | list&lt;string&gt; | OR | Pattern list over originating systems. |
| `labels` | list&lt;string&gt; | **AND** | Labels the node must carry, all of them. Names are canonicalised, so `"pump a"` finds the label stored as `PUMP_A`. A name matching no label matches no nodes. |
| `metadata` | map&lt;string, string&gt; | **AND** | Entries that must all be present. A null value matches the key alone. |
| `createdTime` | [`TimeFilter`](#timefilter) | AND | Window on record creation. |
| `lastUpdatedTime` | [`TimeFilter`](#timefilter) | AND | Window on last update. |

Two things build on that base:

- **`DataSetFilter` adds nothing.** A data set *is* the scope other nodes are filtered by, so it
  has no `dataSetId` of its own — the eight fields above are the whole filter.
- **Resource, time-series and function filters add `dataSetId`**, a list of
  [`IdCollection`](#idcollection) references. A data set stands in for everything beneath it in
  the `BELONGS_TO` hierarchy, so naming a parent covers its children — the same expansion the
  data set ACL applies. An external id naming no data set contributes nothing.

<Tabs groupId="lang">
<TabItem value="java" label="Java">

```java
DataSetFilter plants = new DataSetFilter();
plants.setName(List.of("Plant A*"));            // OR: a pattern list
plants.setLabels(List.of("PRODUCTION"));        // AND: every label must be carried
```

</TabItem>
<TabItem value="python" label="Python">

```python
import intellistream_datahub_sdk

plants = intellistream_datahub_sdk.DatasetFilter(
    name="Plant A*",                            # a bare string is a one-entry list
    labels=["PRODUCTION"])
```

</TabItem>
<TabItem value="rust" label="Rust">

```rust
use intellistream_datahub_sdk::datasets::DatasetFilter;

let mut plants = DatasetFilter::new();
plants.set_name(vec!["Plant A*".to_string()])
      .set_labels(vec!["PRODUCTION".to_string()]);
let plants = plants.build();
```

</TabItem>
</Tabs>

There is no Python `NodeFilter` class: the shared fields are inlined into each filter, so
`DatasetFilter`, `ResourceFilter` and `TimeSeriesFilter` each declare them directly.

`dataSetId` is the one list where **null and empty mean opposite things**:

| Sent | Meaning |
| --- | --- |
| Field omitted, or `null` | No data set restriction |
| `[]` | Narrow to no data sets — matches nothing |

The field was once a scalar `Long`, so the old shape still fails loudly rather than quietly:
`"dataSetId": 43` is a bare number where an object is expected and the request is rejected.
Send `{"id": "43"}` or an external id instead.

## Event filters {#event-filters}

An event query has two layers: an outer retriever carrying paging and ordering, and an inner
`EventFilter` carrying the predicates.

The inner filter shares `externalId`, `source`, `metadata`, `createdTime`, `lastUpdatedTime`
and `dataSetId` with the node filters above — same names, same types, same semantics, pinned by
a parity test since the compiler cannot enforce it. On top of those it adds:

| Field | Type | Combines | Meaning |
| --- | --- | --- | --- |
| `type` | list&lt;string&gt; | OR | Pattern list over event types. |
| `subType` | list&lt;string&gt; | OR | Pattern list over sub-types. |
| `status` | list&lt;string&gt; | OR | Pattern list over lifecycle statuses. |
| `eventTime` | [`TimeFilter`](#timefilter) | AND | Window on when the event occurred, as distinct from when the record was written. |
| `relatedResources` | list&lt;[`IdCollection`](#idcollection)&gt; | **AND** | The event must relate to all of these. Each entry may carry an `id`, an `externalId`, or both. |

There is **no `id` field on an event filter**. Look an event up by id through
[`byIds`](./events#lookup) instead.

<Tabs groupId="lang">
<TabItem value="java" label="Java">

```java
EventFilter alarms = new EventFilter();
alarms.setType(List.of("Alarm", "Warning"));    // either
alarms.setStatus(List.of("OPEN"));
alarms.setRelatedResources(List.of(IdCollection.createFromExternalId("pump_1")));

EventRetreiver retriever = new EventRetreiver();
retriever.setFilter(alarms);
retriever.setLimit(100);
```

</TabItem>
<TabItem value="python" label="Python">

```python
import intellistream_datahub_sdk

alarms = intellistream_datahub_sdk.EventFilter(
    type=["Alarm", "Warning"],
    status="OPEN",
    related_resources=[intellistream_datahub_sdk.IdCollection(external_id="pump_1")])

# There is no outer form in Python: limit, sort_by, sort_order and cursor are
# keyword arguments of events.filter(), which lets one filter be reused across calls.
```

</TabItem>
<TabItem value="rust" label="Rust">

```rust
use intellistream_datahub_sdk::filters::{DataSort, EventFilter, EventFilterForm};

let mut criteria = EventFilter::new();
criteria.set_type(&["Alarm", "Warning"])
        .set_status(&["OPEN"])
        .set_related_resource_external_ids(&["pump_1"]);

let mut form = EventFilterForm::new(criteria.build());
form.set_limit(100).set_sort(DataSort::asc("eventTime"));
```

</TabItem>
</Tabs>

The outer layer has a different name in each client: `EventRetreiver` in Java, `EventFilterForm`
in Rust, and in Python no type at all — `limit`, `sort_by`, `sort_order`, `cursor` and
`advanced_filter` are keyword arguments of `events.filter()`.

The outer retriever carries `limit`, `cursor`, `sort` and `advancedFilter` — a PostgreSQL-flavoured
boolean expression that is AND-combined with the inner filter.
[Events](./events#filtering) documents all four, with the query examples.

## Retrieving datapoints {#retrievefilter}

Datapoint retrieval is not a node filter: it selects points within one series by time window
rather than nodes by their columns. One filter is one series, so reading several means passing
several filters.

| Field | Type | Meaning |
| --- | --- | --- |
| `externalId` | string | The series, by external id. |
| `id` | long | The series, by numeric id. Serialised as a string. |
| `start` / `end` | timestamp | The window. **At least one is required.** |
| `limit` | integer | Maximum datapoints, 0 to 100 000. Defaults to `0`; an explicit null becomes 100. |
| `aggregates` | list&lt;string&gt; | Aggregates to compute instead of raw points. |
| `granularity` | string | Bucket size for `aggregates`, e.g. `1h`. |
| `includeOutsidePoints` | boolean | Include the points bracketing the window. Defaults to `false`. |
| `mergeDuplicates` | boolean | Collapse points sharing a timestamp. Defaults to `false`. |
| `cursor` | string | Continuation from a previous page, see [paging](#paging). |

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
import datetime
import intellistream_datahub_sdk

now = datetime.datetime.now(datetime.timezone.utc)
series = intellistream_datahub_sdk.RetrieveFilter(
    ts="engine_temperature",                    # id or external id, positional and required
    start=now - datetime.timedelta(hours=1),
    end=now,
    limit=1000)
```

</TabItem>
<TabItem value="rust" label="Rust">

```rust
use chrono::Utc;
use intellistream_datahub_sdk::generic::RetrieveFilter;

// The constructor and setters are crate-private, so build the struct directly.
let series = RetrieveFilter {
    external_id: Some("engine_temperature".to_string()),
    start: Some(Utc::now() - chrono::Duration::hours(1)),
    end: Some(Utc::now()),
    limit: Some(1000),
    ..Default::default()
};
```

</TabItem>
</Tabs>

Python names the series `ts` and takes it first; it accepts an id, an external id or a
`TimeSeries`. Java and Rust carry `id` and `externalId` as separate fields.

## Shared pieces {#shared}

### IdCollection {#idcollection}

Wherever a filter references another entity, it does so by id or by external id, in the same
shape:

```json
[{"id": "43"}, {"externalId": "data_set_sap"}]
```

`id` travels as a JSON string even though it is a number, for the precision reason above.

The type is named differently per client: `IdCollection` in Java and Python, `IdAndExtId` in
Rust. Java and Rust offer `createFromId`/`createFromExternalId` and `from_id`/`from_external_id`;
Python constructs it with keywords and refuses one carrying neither. Most Python call sites also
accept a bare `int` or external-id `str` where a reference is expected.

Events are keyed by UUID rather than a numeric id, so they use a separate `EventIdCollection`.

### TimeFilter {#timefilter}

A window on the wire, both bounds optional and **both inclusive** — subtract a millisecond to
exclude the top:

```json
{"min": 1754476522104, "max": 1754480122104}
```

The clients spell it differently: Java sets `min` and `max`, Python takes `start` and `end` and
refuses a filter with neither, and Rust models it as `Between`, `After` or `Before`. All three
send `min`/`max`.

### Sorting {#sorting}

`sort` carries a `property` list and an `order`. There is deliberately **no `nulls` option** on
a filter sort — where nulls sit follows the direction. A `nulls` field did exist and was removed,
so sending one now is an unknown field and a `400`.

Nodes default to `createdTime` descending and events to `eventTime` ascending. An unsortable
property falls back to the default rather than failing, and any `order` that is not exactly
`desc` sorts ascending.

Subscriptions are the exception: their own sort type is separate and still carries `nulls`. It is
not reachable from `events.filter`, `datasets.filter`, `timeseries.filter` or `resources.filter`,
which take a sort property and direction and build the filter sort internally.

### Default sizes {#defaults}

| | Value |
| --- | --- |
| Server default, when no limit is sent | 1000 |
| Maximum page size | 10 000 |

Asking for more than the maximum is a `400`. The cap is on one page, not on how much you can
read — walk past it with a cursor.

The SDKs do not rely on the server default: the Python and Rust clients send `limit` on every
filter call and default it to **100**, so a call that says nothing about paging returns 100 rows
rather than 1000.

## Paging with a cursor {#paging}

A listing that has more to give returns a cursor on the envelope. It is **opaque**: base64, no
version tag, and its contents are ours to change. Echo back exactly what you were handed rather
than assembling one.

A cursor is only meaningful against the order it was produced in, so it must travel with the
same `sort`. Three things are refused with a `400`
[`.../errors/malformed-cursor`](./client#problem-documents):

- a value that is not readable as a cursor,
- one whose row reference is not a valid id,
- one produced by a different sort than the request asks for.

None of them restarts the walk silently, which would loop a paging client or skip rows.

Sorting by `subType` or `status` cannot be paged at all: neither is selective enough to order a
keyset on, so a cursor carrying one is refused. Sort by something else if you need to walk the
whole result.

A full page does not mean there is more — a walk ends with one request that comes back empty.
[Events](./events#paging) has the walk.
