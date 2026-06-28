---
sidebar_position: 7
title: Files
---
import Tabs from '@theme/Tabs';
import TabItem from '@theme/TabItem';

# Files

List directories, upload files, and (Java) download content. File metadata travels in
`X-Datahub-*` headers, which the SDK percent-encodes for you.

## List

<Tabs groupId="lang">
<TabItem value="java" label="Java">

```java
DataWrapper<IndexNode> root = client.files().list();
DataWrapper<IndexNode> reports = client.files().list("/reports/2026");
```

</TabItem>
<TabItem value="python" label="Python">

```python
roots = client.files.list_root_directory()
listing = client.files.list_directory_by_path("/reports/2026")
```

</TabItem>
<TabItem value="rust" label="Rust">

```rust
let roots = api.files.list_root_directory().await?;
let listing = api.files.list_directory_by_path("/reports/2026").await?;
```

</TabItem>
</Tabs>

## Upload

The Java client uploads raw `content` bytes to a destination `path`; the Python and Rust
clients upload a local file and a `destination_path`.

<Tabs groupId="lang">
<TabItem value="java" label="Java">

```java
byte[] content = Files.readAllBytes(Path.of("report.csv"));

DataWrapper<IndexNode> uploaded = client.files().upload(
        FileUploadRequest.builder()
                .path("reports/2026/q2.csv")
                .content(content)
                .contentType("text/csv")        // default: application/octet-stream
                .externalId("report_2026_q2")   // optional
                .dataSetId(42L)                 // optional
                .description("Q2 production")   // optional
                .build());
```

</TabItem>
<TabItem value="python" label="Python">

```python
import datahub_sdk

upload = datahub_sdk.FileUpload(
    path="report.csv",                 # local file
    destination_path="/reports/2026/",
    external_id="report_2026_q2",
    name="q2.csv")

uploaded = client.files.upload_file(upload)   # -> list[INode]
```

</TabItem>
<TabItem value="rust" label="Rust">

```rust
use dataplatform_rust_sdk::files::FileUpload;

// external id + mime type are inferred from the file; or use FileUpload::new(path)
let upload = FileUpload::new_with_destination_path("report.csv", "/reports/2026/");
let uploaded = api.files.upload_file(upload).await?;
```

</TabItem>
</Tabs>

## Download (Java)

The Java client downloads a file's raw bytes by id:

```java
byte[] bytes = client.files().download("99");
Files.write(Path.of("q2.csv"), bytes);
```

## Delete

<Tabs groupId="lang">
<TabItem value="java" label="Java">

```java
client.files().delete(List.of(IdCollection.createFromId(99)));
```

</TabItem>
<TabItem value="python" label="Python">

```python
client.files.delete(["report_2026_q2"])
```

</TabItem>
<TabItem value="rust" label="Rust">

```rust
use dataplatform_rust_sdk::generic::{DataWrapper, IdAndExtId};

api.files.delete(&DataWrapper::from(vec![IdAndExtId::from_external_id("report_2026_q2")])).await?;
```

</TabItem>
</Tabs>
