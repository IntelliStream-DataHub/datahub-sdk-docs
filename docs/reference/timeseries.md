---
sidebar_position: 4
title: Time-series
---
import Tabs from '@theme/Tabs';
import TabItem from '@theme/TabItem';

# Time-series

Time-series metadata, datapoint retrieval, and datapoint ingestion (single-request or
high-throughput).

A series' `externalId` identifies it: unique per tenant, compared without case, and stored
exactly as you send it. [External ids & naming →](./external-ids)

## Create a series

<Tabs groupId="lang">
<TabItem value="java" label="Java">

```java
Timeseries series = new Timeseries()
        .setExternalId("engine_temperature")
        .setName("Engine temperature");
series.setUnit("celsius");

client.timeseries().create(List.of(series));
```

</TabItem>
<TabItem value="python" label="Python">

```python
import intellistream_datahub_sdk

ts = intellistream_datahub_sdk.TimeSeries(
    external_id="engine_temperature",
    name="Engine temperature",
    unit="celsius")

client.timeseries.create([ts])
```

</TabItem>
<TabItem value="rust" label="Rust">

```rust
use intellistream_datahub_sdk::timeseries::TimeSeries;

let mut ts = TimeSeries::new("engine_temperature", "Engine temperature");
ts.unit = Some("celsius".into());
api.time_series.create_one(&ts).await?;
```

</TabItem>
</Tabs>

## Value types

Every series has a **value type** that decides how its datapoints are stored. Leave it
unset and the series is floating-point (`float32`) — right for most sensor readings, so
the create above accepts decimal values as-is. Set it explicitly when you need something
else:

| Value type | Use it for |
| --- | --- |
| `float32` *(default)* | Sensor readings — 32-bit precision is plenty. |
| `float` | Double-precision floating point. |
| `numeric` / `decimal32` | **Exact decimals** — money, lab values — stored without floating-point rounding. Pass the values as strings. |
| `bigint` | Whole numbers (counts, integer statuses). |
| `text` | Non-numeric string values. |
| `mixed` | Heterogeneous values in one series. |

A float written to a `bigint` series is rejected, so pick the type that matches the data.
For a value that must reconcile exactly, use `numeric`:

<Tabs groupId="lang">
<TabItem value="java" label="Java">

```java
Timeseries price = new Timeseries()
        .setExternalId("book_value_usd")
        .setName("Book value (USD)");
price.setUnit("usd");
price.setValueType("numeric");        // exact decimals, no float rounding

client.timeseries().create(List.of(price));
```

</TabItem>
<TabItem value="python" label="Python">

```python
client.timeseries.create([intellistream_datahub_sdk.TimeSeries(
    external_id="book_value_usd", name="Book value (USD)",
    unit="usd", value_type="numeric")])
```

</TabItem>
<TabItem value="rust" label="Rust">

```rust
let mut price = TimeSeries::new("book_value_usd", "Book value (USD)");
price.unit = Some("usd".into());
price.value_type = "numeric".into();  // exact decimals, no float rounding
api.time_series.create_one(&price).await?;
```

</TabItem>
</Tabs>

## Filter series

`POST /timeseries/filter` finds series by structured criteria. Everything you supply is
combined with AND — a series must match every criterion to be included.

| Criterion | Matching |
| --- | --- |
| `dataSetId` | The data set **and every data set beneath it** in the data set hierarchy, so a series attached to a child (or grandchild, …) data set matches too. Each entry is `{"id": …}` or `{"externalId": …}`. |
| `unit` | Pattern, case-insensitive. `*` and `%` are wildcards, `_` is literal (`"cel%"`). |
| `unitExternalId` | Pattern on the unit-catalogue external id (e.g. `temperature_deg_c`), on the same rules. |
| `valueType` | Exact, case-insensitive, against the closed catalogue: `BIGINT`, `FLOAT`, `FLOAT32`, `NUMERIC`, `DECIMAL32`, `TEXT`, `MIXED`. Not a pattern. |
| `id`, `externalId`, `name`, `source` | The shared node criteria. Patterns, on the same rules as `unit`. |
| `labels` | Series carrying **all** of these labels. |
| `metadata` | Every key/value pair given must be present. **A null value matches the key alone**, whatever it holds. |
| `createdTime`, `lastUpdatedTime` | `{ "min": …, "max": … }` bounds. |

Each field above except `labels` and `metadata` takes **either a bare value or an array**, and the
entries of an array are combined with **OR**. That is why they are named in the singular:
`"unit": "celsius"` is the common case, and `"unit": ["celsius", "kelvin"]` asks for either.
`labels` and `metadata` require **all** entries to match and keep their plural names for that
reason.

Results come newest first unless you ask for another order — see
[sorting and paging](#sorting-and-paging) — capped by `limit` (default 1000, max 10000; a value
`<= 0` falls back to the default, and above the ceiling is a 400). Series in data sets you lack
read access to are silently omitted — the result is what your token may see, not an error. For
free-text lookups use `POST /timeseries/search` instead.

:::note The `metadataKey` / `metadataValue` pair is gone
It existed only because `metadata` could not express "has this key, whatever its value". A null
value in the map says that now, and `{"health": "good", "tier": null}` asks for both conditions at
once.
:::

<Tabs groupId="lang">
<TabItem value="java" label="Java">

```java
import ai.intellistream.datahub.models.datafilters.TimeseriesFilter;

TimeseriesFilter criteria = new TimeseriesFilter();
criteria.setDataSetId(List.of(IdCollection.createFromId(12L)));   // and every data set beneath it
criteria.setUnit(List.of("celsius"));

DataWrapper<Timeseries> series = client.timeseries().filter(criteria);
```

Pass a `TimeseriesRetreiver` instead of the bare criteria to set an explicit `limit`.

</TabItem>
<TabItem value="python" label="Python">

```python
form = intellistream_datahub_sdk.TimeSeriesFilterForm(
    data_set_id=[12],            # this data set and every data set beneath it
    unit="celsius",              # a pattern field also takes a bare value
    limit=100)

series = client.timeseries.filter(form)
```

</TabItem>
<TabItem value="rust" label="Rust">

```rust
use intellistream_datahub_sdk::generic::IdAndExtId;
use intellistream_datahub_sdk::{TimeSeriesFilter, TimeSeriesFilterForm};

let criteria = TimeSeriesFilter {
    data_set_id: Some(vec![IdAndExtId::from_id(12)]),   // and every data set beneath it
    unit: Some(vec!["celsius".into()]),
    ..Default::default()
};
let series = api.time_series.filter(&TimeSeriesFilterForm::new(criteria, Some(100))).await?;
```

</TabItem>
</Tabs>

The hierarchy expansion is what makes "master" data sets useful: filter on the top-level
data set of a site or project and you get the series of the whole family beneath it, without
knowing (or maintaining a list of) the sub-data sets.

## Search series {#search}

`POST /timeseries/search` is a free-text search over series. The phrase is matched against `name`,
`externalId` and `description`, fuzzily and word-aware, so `temp` also finds `temperature` and
`tempered`. `limit` defaults to 100 and caps at **1 000**, lower than the 10 000 of
[`filter`](#filter-series), and `query` must be 3 to 140 characters.

Results are **ranked by relevance** (`ts_rank`), strongest match first, with `id` as a tie-break so
equal-scoring rows keep a stable order and repeated identical searches agree. Ranking means the
database scores and sorts every match before applying `limit`, so a very broad phrase costs more
than a narrow one.

`filter` is optional and takes the same `TimeseriesFilter` as `POST /timeseries/filter`. It only
ever removes matches: the phrase decides what the candidates are. `dataSetId` is applied by the
search query itself, everything else is applied to the hits afterwards.

```json
{
  "search": { "query": "temperature" },
  "filter": { "unit": ["deg_*"], "valueType": ["FLOAT"] },
  "limit": 50
}
```

:::warning `search.name` and `search.description` are gone
The phrase block is now a single `query`, the same shape the other three searches take. The two
alternatives it used to carry were removed rather than kept: `name` matched by **exact equality**
under an endpoint documented as full-text, and `description` ran a differently configured query
over one column.

Both have a better replacement. `filter.name` matches names as a case-insensitive pattern list
(`["pump_*", "PMP-1"]`), which is more than `search.name` could do, and `query` already covers the
description column.

Clients exposing these as separate calls (`search_by_name`, `search_by_description`) need updating
to match.
:::

## Sorting and paging {#sorting-and-paging}

The three node filters — `/timeseries/filter`, `/resources/filter` and `/datasets/filter` —
share this contract. (`/events/filter` works the same way over its own columns; see
[events](./events#paging).)

Order a page with `sort`, over `id`, `externalId`, `name`, `source`, `description`,
`createdTime`, `lastUpdatedTime` or `dataSetId`. The default is `createdTime` descending —
newest created first.

```json
{ "filter": { "unit": "celsius" },
  "sort": { "property": ["name"], "order": "asc" },
  "limit": 100 }
```

Only the **first** `property` is used, and `id` is appended behind it: a sort column alone is not
a position unless it is unique, and a page boundary inside a run of equal values repeats or drops
exactly those rows. An unrecognised property falls back to the default rather than being
rejected, and any `order` that is not exactly `desc` sorts ascending. Nulls sort last ascending,
first descending — most of these columns are nullable, since every node type shares one table.

A page that has a successor carries a `nextCursor`. Echo it back as `cursor` to continue:

```json
{ "filter": { "unit": "celsius" },
  "sort": { "property": ["name"], "order": "asc" },
  "cursor": "djE6bmFtZXxhc2N8N3x2YQ",
  "limit": 100 }
```

The cursor is **opaque** — base64 of a versioned encoding carrying the sort, the boundary value
and the id — so do not build or parse one. Send it with the **same** sort that produced it; a
cursor is a position in one particular order, and continuing it under another is refused. One
that does not decode restarts the walk from the first page rather than failing.

`nextCursor` is absent on a short page, so "keep going while it is present" is the whole loop. A
full page may still be the last, so a complete walk ends with one empty request.

<Tabs groupId="lang">
<TabItem value="java" label="Java">

```java
TimeseriesRetreiver retriever = new TimeseriesRetreiver();
retriever.getSort().setProperty(List.of("name"));
retriever.getSort().setOrder("asc");

DataWrapper<Timeseries> page = client.timeseries().filter(retriever);
while (page.getNextCursor() != null) {
    retriever.setCursor(page.getNextCursor());
    page = client.timeseries().filter(retriever);
}
```

</TabItem>
<TabItem value="python" label="Python">

```python
cursor = None
while True:
    page = client.timeseries.filter(intellistream_datahub_sdk.TimeSeriesFilterForm(
        unit="celsius", limit=100, sort_by="name", sort_order="asc", cursor=cursor))
    for ts in page:
        ...
    cursor = page.next_cursor
    if cursor is None:
        break
```

`filter()` returns a `Page` — a list, so existing code is unaffected, carrying `.next_cursor`.

</TabItem>
<TabItem value="rust" label="Rust">

```rust
use intellistream_datahub_sdk::filters::PageRequest;
use intellistream_datahub_sdk::{TimeSeriesFilter, TimeSeriesFilterForm};

let mut paging = PageRequest::asc("name");
loop {
    let form = TimeSeriesFilterForm::new(TimeSeriesFilter::default(), Some(100))
        .with_paging(paging.clone());
    let page = api.time_series.filter(&form).await?;
    // ... use page.get_items()
    match page.next_cursor() {
        Some(cursor) => paging = PageRequest::asc("name").after(cursor),
        None => break,
    }
}
```

</TabItem>
</Tabs>

## Delete a series

Deletes the series and its datapoints. Remove any referencing subscriptions (and edges) first, or
the backend responds 409.

The definition is gone when the call returns; the datapoint purge is handed off and completes
shortly after. Nothing can read those datapoints in the meantime, because every read resolves the
series first.

<Tabs groupId="lang">
<TabItem value="java" label="Java">

```java
import ai.intellistream.datahub.models.IdCollection;

client.timeseries().delete(List.of(IdCollection.createFromExternalId("engine_temperature")));
```

</TabItem>
<TabItem value="python" label="Python">

```python
client.timeseries.delete(["engine_temperature"])
```

</TabItem>
<TabItem value="rust" label="Rust">

```rust
use intellistream_datahub_sdk::generic::{DataWrapper, IdAndExtId};

api.time_series
    .delete(&DataWrapper::from_vec(vec![IdAndExtId::from_external_id("engine_temperature")]))
    .await?;
```

</TabItem>
</Tabs>

## Write datapoints

A datapoint is a `(timestamp, value)` pair grouped under a series' external id.

<Tabs groupId="lang">
<TabItem value="java" label="Java">

Timestamps are **epoch milliseconds** as strings:

```java
DatapointsCollection collection = new DatapointsCollection();
collection.setExternalId("engine_temperature");
collection.setDatapoints(List.of(
        new DatapointString(String.valueOf(System.currentTimeMillis()), "92.4")));

client.timeseries().insertDatapoints(List.of(collection));
```

</TabItem>
<TabItem value="python" label="Python">

Pass timezone-aware timestamps (pandas or `datetime`); the SDK converts to UTC:

```python
import pandas as pd

client.timeseries.insert_from_lists(
    timestamps=pd.date_range("2026-01-01", periods=3, freq="h", tz="UTC"),
    values=[92.4, 92.6, 92.1],
    ts=ts)
```

</TabItem>
<TabItem value="rust" label="Rust">

```rust
use chrono::Utc;

api.time_series
    .insert_datapoint(None, Some("engine_temperature".into()), Utc::now(), "92.4".into())
    .await?;
```

</TabItem>
</Tabs>

## High-throughput ingestion

For large or unbounded volumes the SDK chunks and sends in bulk. See the
[ingestion guide](/guides/ingest-timeseries) for the full story.

:::tip Survive outages with durable buffering
Enable [durable buffering](/reference/client#durable-ingest-buffering) on the client and datapoint
ingestion that can't reach the API spools to disk and flushes on the next call, bounded by a time
and/or size window. Retries are idempotent (datapoints dedup on `(series, timestamp)`).
:::

<Tabs groupId="lang">
<TabItem value="java" label="Java">

`ingest` chunks, parallelises and retries, returning an [`IngestResult`](#ingestresult)
tuned with [`IngestOptions`](#ingestoptions):

```java
IngestResult result = client.timeseries().ingest(data,
        IngestOptions.builder()
                .batchSize(10_000)   // datapoints per request
                .parallelism(16)     // concurrent in-flight requests
                .maxRetries(3)
                .build());

System.out.printf("ingested %,d, failed %,d%n", result.succeeded(), result.failed());
```

</TabItem>
<TabItem value="python" label="Python">

`insert_from_lists` takes whole arrays (NumPy / pandas) and handles batching for you:

```python
import numpy as np, pandas as pd

client.timeseries.insert_from_lists(
    timestamps=pd.date_range("2026-01-01", periods=1_000_000, freq="s", tz="UTC"),
    values=np.random.rand(1_000_000),
    ts=ts)
```

</TabItem>
<TabItem value="rust" label="Rust">

`insert_datapoints` auto-batches large inputs (chunks above ~100k points):

```rust
use intellistream_datahub_sdk::generic::{DataWrapper, DatapointsCollection, DatapointString};

let mut dw = DataWrapper::new();
dw.add_item(DatapointsCollection {
    external_id: Some("engine_temperature".into()),
    datapoints: points,          // Vec<DatapointString { timestamp, value }>
    ..Default::default()
});
api.time_series.insert_datapoints(&mut dw).await?;
```

</TabItem>
</Tabs>

## Retrieve datapoints

Identify a series (external id or id) and a time window.

<Tabs groupId="lang">
<TabItem value="java" label="Java">

```java
import java.time.ZonedDateTime;

RetrieveFilter series = new RetrieveFilter();
series.setExternalId("engine_temperature");
series.setStart(ZonedDateTime.now().minusHours(1));
series.setEnd(ZonedDateTime.now());
series.setLimit(1000);

DataRetriever<RetrieveFilter> request = new DataRetriever<>();
request.setItems(List.of(series));

DataWrapper<DatapointsCollection> points = client.timeseries().retrieve(request);
points.getItems().forEach(c ->
        System.out.println(c.getExternalId() + ": " + c.getDatapoints().size() + " points"));
```

</TabItem>
<TabItem value="python" label="Python">

```python
import pandas as pd

rf = intellistream_datahub_sdk.RetrieveFilter(
    ts="engine_temperature",
    start=pd.Timestamp.now(tz="UTC") - pd.Timedelta(hours=1),
    end=pd.Timestamp.now(tz="UTC"),
    limit=1000)

collection = client.timeseries.retrieve_datapoints(rf)[0]
for dp in collection.get_datapoints():
    print(dp.timestamp, dp.value)
```

</TabItem>
<TabItem value="rust" label="Rust">

```rust
use chrono::Utc;
use intellistream_datahub_sdk::generic::{DataWrapper, RetrieveFilter};

let filter = RetrieveFilter {
    external_id: Some("engine_temperature".into()),
    start: Some(Utc::now() - chrono::Duration::hours(1)),
    end: Some(Utc::now()),
    limit: Some(1000),
    ..Default::default()
};
let points = api.time_series
    .retrieve_datapoints(&DataWrapper::from(vec![filter]))
    .await?;
for c in points.get_items() {
    println!("{} points", c.datapoints.len());
}
```

</TabItem>
</Tabs>

## Delete datapoints

Clears part of a series and leaves the definition alone. To remove the series itself, see
[delete a series](#delete-a-series).

Each item names one series by `externalId` or `id`, and both window bounds are optional:

| Bounds given | What is deleted |
| --- | --- |
| `inclusiveBegin` and `exclusiveEnd` | The half-open window between them |
| `inclusiveBegin` only | Everything from that instant onward |
| `exclusiveEnd` only | Everything before that instant |
| Neither | Every datapoint of the series, leaving its definition, edges and subscriptions |

A bound is either ISO-8601 or epoch milliseconds; anything else is a 400 naming the field, as is
a series that does not exist. Python, Rust and Java's `Instant` overload take real datetimes, so
those always send the ISO form.

Like a series delete, this is handed off and completes shortly after the call returns, and it
cannot be undone.

<Tabs groupId="lang">
<TabItem value="java" label="Java">

```java
import java.time.Instant;

client.timeseries().deleteDatapoints(
        "engine_temperature",
        Instant.parse("2026-01-01T00:00:00Z"),
        Instant.parse("2026-02-01T00:00:00Z"));

// A null bound leaves that side open, so two nulls empty the series:
client.timeseries().deleteDatapoints("engine_temperature", null, null);
```

For several series at once, or to name one by id, pass `DeleteDatapoint` items instead:

```java
DeleteDatapoint window = new DeleteDatapoint();
window.setId(7L);
window.setInclusiveBegin("1767225600000");     // epoch millis is the other accepted form

client.timeseries().deleteDatapoints(List.of(window));
```

</TabItem>
<TabItem value="python" label="Python">

```python
import pandas as pd

client.timeseries.delete_datapoints([
    intellistream_datahub_sdk.DeleteFilter(
        ts="engine_temperature",
        inclusive_begin=pd.Timestamp("2026-01-01", tz="UTC"),
        exclusive_end=pd.Timestamp("2026-02-01", tz="UTC"))])
```

</TabItem>
<TabItem value="rust" label="Rust">

```rust
use chrono::{TimeZone, Utc};
use intellistream_datahub_sdk::generic::{DataWrapper, DeleteFilter};

let filter = DeleteFilter::from_external_id(
    "engine_temperature".to_string(),
    Some(Utc.with_ymd_and_hms(2026, 1, 1, 0, 0, 0).unwrap()),
    Some(Utc.with_ymd_and_hms(2026, 2, 1, 0, 0, 0).unwrap()));

api.time_series.delete_datapoints(&DataWrapper::from_vec(vec![filter])).await?;
```

</TabItem>
</Tabs>

## IngestOptions

The Java `ingest` tuning knobs (Python's `insert_from_lists` and Rust's
`insert_datapoints` batch internally):

| Option | Default | Meaning |
| --- | --- | --- |
| `batchSize` | `10_000` | Maximum items per request. |
| `parallelism` | `8` | Concurrent in-flight requests. |
| `maxRetries` | `3` | Retries for transient failures (HTTP 429/5xx, network). |
| `failFast` | `false` | If `true`, abort on the first failed batch instead of collecting errors. |

`IngestOptions.defaults()` returns the defaults; `ingest(data)` (no options) uses them.

## IngestResult

```java
long              succeeded()    // items ingested
long              failed()       // items that could not be ingested
long              buffered()     // items spooled to the durable buffer (0 unless buffering is on)
boolean           isComplete()   // true when nothing failed and nothing was buffered
List<BatchError>  errors()       // one entry per failed batch
```

`BatchError` is a record `(int datapointCount, int statusCode, String message)` —
`statusCode` is `0` when the failure was a network error rather than an HTTP status.

```java
if (!result.isComplete()) {
    result.errors().forEach(e ->
            System.err.println(e.statusCode() + " on " + e.datapointCount() + " items: " + e.message()));
}
```

## What each client covers {#client-coverage}

| Operation | Java | Python | Rust |
| --- | --- | --- | --- |
| Create | `timeseries().create` | `timeseries.create` | `time_series.create` / `create_one` |
| Look up by id / external id | `timeseries().byIds` | `timeseries.by_ids` | `time_series.by_ids` |
| Filter | `timeseries().filter` | `timeseries.filter` | `time_series.filter` |
| Search | `timeseries().search` | `timeseries.search` | `time_series.search` |
| List | HTTP | `timeseries.list` | `time_series.list` / `list_with_limit` |
| Update | HTTP | `timeseries.update` | `time_series.update` |
| Delete | `timeseries().delete` | `timeseries.delete` | `time_series.delete` |
| Write datapoints | `insertDatapoints` / `ingest` | `insert_datapoints` / `insert_from_lists` | `insert_datapoint` / `insert_datapoints` |
| Read datapoints | `retrieve` / `retrieveAggregated` | `retrieve_datapoints` / `retrieve_latest_datapoints` | `retrieve_datapoints` / `retrieve_latest_datapoint` |
| Delete datapoints | `deleteDatapoints` | `timeseries.delete_datapoints` | `time_series.delete_datapoints` |

Java is the one with `ingest`, the chunking, parallelising, retrying path described above.
It is missing `list` and `update`, so reach for the endpoint there. It gained `search` alongside
the resource, data set and event searches it already had.
