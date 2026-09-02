---
sidebar_position: 1
slug: /
title: DataHub SDK
---

# DataHub SDK

A thin, fast client for the **DataHub Platform** — manage resources, time-series,
events, files, and stream live data from your own application.

The SDK is available for **Java**, **Python** and **Rust**. Pick your language once
(top-right of any code block) and every example on the site gives you a working
guide in your language of choice.

:::tip Five-minute start
Head to the [Quick start](/quickstart) to create a client and write your first
datapoint, or jump to [high-throughput ingestion](/guides/ingest-timeseries) to ingest data at scale.
:::

## What you can do

- **Time-series** — create series, ingest datapoints in parallel, query raw values and aggregates.
- **Resources** — model assets and their relationships as a graph.
- **Events** — record and query operational events.
- **Files** — attach documents and images to your assets.
- **Subscriptions** — tail live data over a streaming connection.

## Licence

The three SDKs, and the Java wire-contract model the Java SDK depends on, are
[Apache-2.0](https://www.apache.org/licenses/LICENSE-2.0). They were placed under that licence
so that linking one into your application carries no copyleft obligation into your code. The
platform they talk to is [AGPL-3.0](https://www.gnu.org/licenses/agpl-3.0.html); that licence
covers the server, and using the server over its API is not what it restricts.

## Where to go next

- **[Tutorial](/tutorial)** — build a small metrics agent end to end: create series, ingest on a schedule, and survive API outages.
- **[Examples](/guides/ingest-timeseries)** — task recipes: ingestion, graph modeling, querying & aggregation, live consumption, and event detection.
- **[Industry scenarios](/industries/oil-and-gas/production)** — end-to-end walkthroughs for oil & gas, energy grids, finance, and IT operations.
- **[API reference](/reference/client)** — every service, method and option, in Java, Python and Rust.
