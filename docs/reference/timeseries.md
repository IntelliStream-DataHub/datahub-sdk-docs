---
sidebar_position: 3
title: Time-series
---
import Tabs from '@theme/Tabs';
import TabItem from '@theme/TabItem';

# Time-series

Time-series metadata, datapoint retrieval, and datapoint ingestion (single-request or
high-throughput).

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
import datahub_sdk

ts = datahub_sdk.TimeSeries(
    external_id="engine_temperature",
    name="Engine temperature",
    unit="celsius")

client.timeseries.create([ts])
```

</TabItem>
<TabItem value="rust" label="Rust">

```rust
use dataplatform_rust_sdk::timeseries::TimeSeries;

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
client.timeseries.create([datahub_sdk.TimeSeries(
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

## Delete a series

Deletes the series and its datapoints. Remove any referencing subscriptions (and edges) first, or
the backend responds 409.

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
use dataplatform_rust_sdk::generic::{DataWrapper, IdAndExtId};

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
use dataplatform_rust_sdk::generic::{DataWrapper, DatapointsCollection, DatapointString};

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

rf = datahub_sdk.RetrieveFilter(
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
use dataplatform_rust_sdk::generic::{DataWrapper, RetrieveFilter};

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
