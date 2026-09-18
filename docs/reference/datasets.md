---
sidebar_position: 5
title: Data sets
---
import Tabs from '@theme/Tabs';
import TabItem from '@theme/TabItem';

# Data sets

Logical groupings of resources and time series. Data sets can be nested (a data set can
belong to a parent data set), and that hierarchy is live in queries: filtering time series
by a data set also matches everything beneath it.
[Filter series →](./timeseries#filter-series)

The hierarchy is built from `BELONGS_TO` relationships, and the server enforces that: a
relationship pointing at a data set must be `BELONGS_TO`, and a data set can only claim a
time series that isn't already in another data set. Despite the name, the edge runs from the
parent to the child, and the dependable way to build it is to create that edge explicitly rather
than setting `connectedDataSets` (`connected_data_sets` in Python and Rust) on the new data set.
[Relationship rules →](./resources#create-resources-and-relations)

:::note External ids are stored exactly as you send them. In the Rust sdk
`Dataset::new` derives one from the name, in snake_case; that is a client-side default,
not a server rule.

Uniqueness and lookup both ignore case, so `plant_a` collides with `PLANT_A` and either
spelling finds the same data set. Data sets are also subject to the
[naming policy](./external-ids#the-naming-policy) if an administrator has set one.
[External ids & naming →](./external-ids)
:::

## Create

<Tabs groupId="lang">
<TabItem value="java" label="Java">

```java
DataSetModel dataset = new DataSetModel();
dataset.setExternalId("plant_a");
dataset.setName("Plant A");
dataset.setMetadata(Map.of("tier", "gold"));

client.datasets().create(List.of(dataset));
```

</TabItem>
<TabItem value="python" label="Python">

```python
import intellistream_datahub_sdk

dataset = intellistream_datahub_sdk.Dataset(
    external_id="plant_a", name="Plant A", metadata={"tier": "gold"})
client.datasets.create([dataset])
```

</TabItem>
<TabItem value="rust" label="Rust">

```rust
use intellistream_datahub_sdk::datasets::Dataset;

// external_id is derived as snake_case of the name → "plant_a"
let mut dataset = Dataset::new("Plant A".into());
dataset.add_metadata("tier".into(), "gold".into());
api.datasets.create(&vec![dataset]).await?;
```

</TabItem>
</Tabs>

## Look up & delete

<Tabs groupId="lang">
<TabItem value="java" label="Java">

```java
DataWrapper<DataSetModel> some = client.datasets()
        .byIds(List.of(IdCollection.createFromExternalId("plant_a")));

client.datasets().delete(List.of(IdCollection.createFromExternalId("plant_a")));
```

</TabItem>
<TabItem value="python" label="Python">

```python
some = client.datasets.by_ids(["plant_a"])
client.datasets.delete(["plant_a"])
```

</TabItem>
<TabItem value="rust" label="Rust">

```rust
use intellistream_datahub_sdk::generic::IdAndExtId;

let some = api.datasets.by_ids(&vec![IdAndExtId::from_external_id("plant_a")]).await?;
api.datasets.delete(&vec![IdAndExtId::from_external_id("plant_a")]).await?;
```

</TabItem>
</Tabs>

## Filter {#filter}

`POST /datasets/filter` finds data sets by structured criteria, combined with AND. It is exactly
the criteria every node type shares, a data set has no `dataSetId` of its own, being the thing
other nodes are scoped *by*:

| Criterion | Matching |
| --- | --- |
| `id` | Numeric ids, matched exactly. |
| `externalId`, `name`, `source` | Patterns, case-insensitive. `*` and `%` are wildcards, `_` is literal, and an entry with no wildcard matches exactly. |
| `labels` | Data sets carrying **all** of these labels. |
| `metadata` | Every key/value pair given must be present. **A null value matches the key alone**, whatever it holds. |
| `createdTime`, `lastUpdatedTime` | `{ "min": …, "max": … }` bounds. |

Each field except `labels` and `metadata` takes **either a bare value or an array**, whose
entries are combined with OR, which is why they are named in the singular. `limit` is capped at
10000, and the page can be ordered and walked exactly as
[timeseries](./timeseries#sorting-and-paging) can. The server's default `limit` is 1000, but
not every client leaves it to the server:

<Tabs groupId="lang">
<TabItem value="java" label="Java">

```java
DataSetFilter criteria = new DataSetFilter();
criteria.setName(List.of("Plant *"));
criteria.setMetadata(Map.of("tier", "gold"));

DataWrapper<DataSetModel> matches = client.datasets().filter(criteria);
```

Pass a `DataSetRetreiver` instead of the bare criteria to set `limit`, `sort` or `cursor`.

</TabItem>
<TabItem value="python" label="Python">

```python
matches = client.datasets.filter(name="Plant *", metadata={"tier": "gold"}, limit=100)
```

Or build the criteria once as a `DatasetFilter` and pass it as `filter=`, keeping `limit`,
`sort_by`, `sort_order` and `cursor` on the call. Either way it returns a list-like
[`Page`](./timeseries#sorting-and-paging) carrying `.next_cursor`.

</TabItem>
<TabItem value="rust" label="Rust">

```rust
use intellistream_datahub_sdk::datasets::{DatasetFilter, DatasetFilterForm};
use std::collections::HashMap;

let criteria = DatasetFilter::new()
    .set_name(vec!["Plant *".to_string()])
    .set_metadata(HashMap::from([("tier".to_string(), Some("gold".to_string()))]))
    .build();
let mut form = DatasetFilterForm::from_filter(criteria);
form.set_limit(100);
let matches = api.datasets.filter(&form).await?;
```

`DatasetFilter` is the criteria and `DatasetFilterForm` the request body around it, which also
takes `set_paging` for `sort` and `cursor`.

</TabItem>
</Tabs>

:::note There is no `writeProtected` or `deactivated` criterion
A filter carrying either, or any other unknown field, is refused with a `400` as an
[unknown field](./client#unknown-fields).
:::

## Search {#search}

`POST /datasets/search` is a free-text search over data sets. The phrase is matched against
`name`, `externalId` and `description`, fuzzily and word-aware. `limit` defaults to 100 and caps at
**1 000**, lower than the 10 000 of `filter`, and `query` must be 3 to 140 characters.

Results are **ranked by relevance** (`ts_rank`), strongest match first, with `id` as a tie-break so
equal-scoring rows keep a stable order and repeated identical searches agree. Ranking means the
database scores and sorts every match before applying `limit`, so a very broad phrase costs more
than a narrow one.

`filter` is optional and takes the same criteria as [`POST /datasets/filter`](#filter). It only
ever removes matches: the phrase decides what the candidates are.

```json
{
  "search": { "query": "work order" },
  "filter": { "metadata": { "source_system": "sap" } },
  "limit": 50
}
```

No match is an empty list, not a `404`.

## Access control {#access-control}

Access to a data set is administered in Keycloak (or the directory behind it), not in
DataHub. A grant is membership of an **organization group**, scoped to one organization:

| Group | Grants |
| --- | --- |
| `/datasets/<externalId>/read` | Read everything in that data set, and in every data set beneath it. |
| `/datasets/<externalId>/write` | Write, with the same inheritance. |
| `/datasets/*/read` | Read every data set. |
| `/datasets/*/write` | Write every data set. |

Read and write are independent: a write grant does not imply read, the wildcard included.
The `DATAHUB_ADMIN` realm role grants read and write to everything (an operator escape
hatch). Entities outside any data set follow the wildcard too: reading them needs
`/datasets/*/read`, writing or creating them needs `/datasets/*/write` (or admin).

Two consequences worth knowing when you code against this:

- **A missing grant is a `403`** with an `application/problem+json` body naming the
  `dataSetId` and the `permission` (read or write) you lack. List, filter and search
  endpoints never 403 on grants: rows in data sets you cannot read are silently
  omitted instead.
- **Relationship reads hide rather than refuse too.** Reading a relationship needs read
  on both endpoints' data sets. One you may not read is a `404` from `GET /edges/{id}`
  and omitted from `/edges/byids`, as if it did not exist.
- **Managing a data set itself is stricter.** Creating, updating or deleting a data set
  (as opposed to the data in it) requires the `/datasets/*/write` grant or `DATAHUB_ADMIN`.
  Grants on individual data sets are never enough, deliberately: a data set is the unit
  access is granted on, so renaming or re-parenting one changes what existing grants
  cover.
- **The rule follows the node, not the endpoint.** A `DATASET`- or `POLICY`-labelled
  node reached through `/resources` answers the same way. The `403` detail spells this
  out.

The API reads grants from the identity provider's UserInfo endpoint, not from the token, and
caches them: the grant cache refreshes after 45 seconds, behind a 10-second in-process cache.
A changed grant therefore takes effect within about a minute, without a new token.

## What each client covers {#client-coverage}

| Operation | Java | Python | Rust |
| --- | --- | --- | --- |
| Create | `datasets().create` | `datasets.create` | `datasets.create` |
| Look up by id / external id | `datasets().byIds` | `datasets.by_ids` | `datasets.by_ids` |
| List (`GET /datasets`) | `datasets().list(limit)` | `datasets.list(limit=None)` | `datasets.list(limit)` |
| Filter | `datasets().filter` | `datasets.filter` | `datasets.filter` |
| Search | `datasets().search` | `datasets.search(query, filter, limit)` | `datasets.search` / `search_by_query` |
| Update | `datasets().update` | `datasets.update` (`DatasetUpdate`) | `datasets.update` (`DatasetUpdate`) |
| Delete | `datasets().delete` | `datasets.delete` | `datasets.delete` |
| Policies (`GET /datasets/policies`) | `datasets().policies` | `datasets.policies` | `datasets.policies` |

`policies()` returns every policy in the tenant that a data set can be associated with, as
graph resources. It is the dataset-facing view of the catalogue the
[policy service](./policies) manages:

```java
DataWrapper<Resource> choices = client.datasets().policies();
```

It has been seen answering `200` with an empty body while `GET /policies` held rows, so don't
read an empty result as "no policies".
