---
sidebar_position: 5
title: Datasets
---
import Tabs from '@theme/Tabs';
import TabItem from '@theme/TabItem';

# Datasets

Logical groupings of resources and time-series. Datasets can be nested (a dataset can
belong to a parent dataset), and that hierarchy is live in queries: filtering time-series
by a dataset also matches everything beneath it.
[Filter series →](./timeseries#filter-series)

The hierarchy is built from `BELONGS_TO` edges, and the server enforces that: a relation
pointing at a dataset must be `BELONGS_TO`, and a dataset can only claim a time-series
that isn't already in another dataset.
[Edge rules →](./resources#create-resources-and-relations)

:::note External ids are stored exactly as you send them
The server does not rewrite a dataset external id: `Plant-A` stays `Plant-A`. Some clients
*derive* one from the name as a convenience (the Rust `Dataset::new` below), and that
derivation is snake_case — but it is a client-side default, not a server rule.

Uniqueness and lookup both ignore case, so `plant_a` collides with `PLANT_A` and either
spelling finds the same dataset. Datasets are also subject to the
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

client.datasets().create(List.of(dataset));
```

</TabItem>
<TabItem value="python" label="Python">

```python
import datahub_sdk

dataset = datahub_sdk.Dataset(external_id="plant_a", name="Plant A")
client.datasets.create([dataset])
```

</TabItem>
<TabItem value="rust" label="Rust">

```rust
use dataplatform_rust_sdk::datasets::Dataset;

// external_id is derived as snake_case of the name → "plant_a"
let dataset = Dataset::new("Plant A".into());
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
use dataplatform_rust_sdk::generic::IdAndExtId;

let some = api.datasets.by_ids(&vec![IdAndExtId::from_external_id("plant_a")]).await?;
api.datasets.delete(&vec![IdAndExtId::from_external_id("plant_a")]).await?;
```

</TabItem>
</Tabs>

The Java client additionally offers `getById(long)`, `list(DataSetRetreiver)`,
`search(DataSetSearch)` and `update(List<DataSetForm>)`.

## Filter {#filter}

`POST /datasets/filter` finds datasets by structured criteria. Every criterion is optional and
they AND together, so a dataset must match all of them; an empty `filter` returns everything.

| Criterion | Matching |
| --- | --- |
| `ids` | Datasets named directly by id. |
| `externalIds` / `names` / `sources` | Pattern lists, OR-ed within each list. See the wildcard note below. |
| `labels` | Datasets carrying **all** of these labels. Names are canonicalised, so `pump a` finds the label stored as `PUMP_A`. |
| `metadata` | Every key/value pair you give must be present on the dataset. |
| `createdTime` / `lastUpdatedTime` | Inclusive `min`/`max` instants; either bound alone works. |

An empty list places no restriction rather than matching nothing, so building `ids` from a
possibly-empty selection is safe — `null` means the same. For free-text matching over name and
description use `POST /datasets/search` instead.

:::note One list covers exact, prefix and contains
`externalIds`, `names` and `sources` take patterns, not just literals. `*` and `%` are both
wildcards, and an entry without one matches exactly — so a single list mixes all three kinds of
lookup: `["sap_work_orders", "plant_*", "*_archive"]` is an exact id, a prefix search and a
suffix search at once.

`_` is **literal**, unlike raw SQL `LIKE`. External ids are built out of underscores, so asking
for `sap_work_orders` means that id and not `sapXwork_orders`. Matching is case-insensitive
throughout.
:::

```http
POST /datasets/filter
{
  "limit": 1000,
  "filter": {
    "externalIds": ["sap_*"],
    "names": ["Plant A", "Plant B"],
    "labels": ["production"],
    "metadata": { "owner": "plant-a" }
  },
  "sort": { "property": ["name"], "order": "asc" }
}
```

`limit` defaults to **1000** and is capped at 10000; a value of zero or less falls back to the
default rather than returning nothing. `POST /datasets/list` takes the same body and behaves
identically — `/filter` is the name the resource, time-series and event endpoints use for the
same operation.

### Sorting and paging {#paging}

Results come newest created first unless you say otherwise. `sort` takes one property — `id`,
`externalId`, `name`, `source`, `description`, `createdTime`, `lastUpdatedTime` or `dataSetId` —
with an `order` of `asc` or `desc`. `id` is always appended to whatever you pick, so the
ordering is total and two datasets sharing a name never swap places between pages.

The response carries `nextCursor` when there may be more. Send it back as `cursor` with the
**same `sort` it came from** and keep going while it is present. This is keyset paging, not
`OFFSET`, so the thousandth page costs what the first one did. The cursor is opaque — base64
over the sort, the last row's value and its id — so don't build or parse one. An unreadable
cursor silently restarts from the first page rather than erroring.

<Tabs groupId="lang">
<TabItem value="java" label="Java">

```java
import ai.intellistream.datahub.models.datafilters.DataSetFilter;

DataSetFilter criteria = new DataSetFilter();
criteria.setExternalIds(List.of("sap_*"));
criteria.setLabels(List.of("production"));

DataWrapper<DataSetModel> datasets = client.datasets().filter(criteria);
```

Pass a `DataSetRetreiver` instead of the bare criteria to set an explicit `limit`, a `sort` or
a `cursor`.

</TabItem>
<TabItem value="python" label="Python">

```python
import datahub_sdk

page = client.datasets.filter(datahub_sdk.DatasetFilter(
    filter=datahub_sdk.BasicDatasetFilter(
        external_ids=["sap_*"],
        labels=["production"],
    ),
    limit=1000,
    sort_by="name",
))

while True:
    for dataset in page:
        print(dataset.external_id)
    if page.next_cursor is None:
        break
    page = client.datasets.filter(datahub_sdk.DatasetFilter(cursor=page.next_cursor, sort_by="name"))
```

`filter` returns a `Page`, which behaves as a list — `len()`, indexing and iteration all work —
and adds `next_cursor`.

</TabItem>
<TabItem value="rust" label="Rust">

```rust
use dataplatform_rust_sdk::datasets::{BasicDatasetFilter, DatasetFilter};
use dataplatform_rust_sdk::filters::PageRequest;

let mut criteria = BasicDatasetFilter::new();
criteria.set_external_ids(vec!["sap_*".into()]);
criteria.set_labels(vec!["production".into()]);

let mut request = DatasetFilter::from_filter(criteria.build());
request.set_limit(1000).set_paging(PageRequest::asc("name"));

let datasets = api.datasets.filter(&request).await?;
```

`PageRequest::asc` / `desc` name the sort; `.after(cursor)` continues from a previous page.

</TabItem>
</Tabs>

Filtering a dataset does **not** expand the dataset hierarchy — it matches the datasets
themselves, not their descendants. That expansion is what naming a data set does in the *other*
filters, where `dataSetIds` now covers a parent and everything beneath it.
[Filter series →](./timeseries#filter-series)

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
- **Managing a data set itself is stricter.** Creating, updating or deleting a data set
  (as opposed to the data in it) requires the `/datasets/*/write` grant or `DATAHUB_ADMIN`;
  grants on individual data sets are never enough, deliberately: a data set is the unit
  access is granted on, so renaming or re-parenting one changes what existing grants
  cover. The `403` detail spells this out.

The API reads grants from the identity provider's UserInfo endpoint, not from the token,
so a changed grant takes effect within about a minute, without a new token.

## What each client covers {#client-coverage}

| Operation | Java | Python | Rust |
| --- | --- | --- | --- |
| Create | `datasets().create` | `datasets.create` | `datasets.create` |
| Look up by id / external id | `datasets().byIds` | `datasets.by_ids` | `datasets.by_ids` |
| List | `datasets().list` | `datasets.list` | `datasets.list` |
| [Filter](#filter) | `datasets().filter` | `datasets.filter` | `datasets.filter` |
| Search | `datasets().search` | `datasets.search` | `datasets.search` |
| Update | `datasets().update` | `datasets.update` | `datasets.update` |
| Delete | `datasets().delete` | `datasets.delete` | `datasets.delete` |
| Access policies | HTTP | `datasets.policies` | `datasets.policies` |

All three clients now cover the endpoint surface. Python and Rust unwrap the results — Python
hands back plain lists, or a `Page` from `filter`; Java returns the `DataWrapper` the API sends,
so the items come out of `getItems()`.

:::caution The `filter` on `datasets.search` is ignored
`POST /datasets/search` declares filter criteria alongside the query, and the server does not
apply them. Both the Python and Rust clients expose the parameter because the endpoint does.
Use [`filter`](#filter) when you need criteria, and treat search as free text only.
:::
