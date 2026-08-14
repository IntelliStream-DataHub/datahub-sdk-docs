---
sidebar_position: 8
title: Files
---
import Tabs from '@theme/Tabs';
import TabItem from '@theme/TabItem';

# Files

List directories, upload files, and download content. File metadata travels in
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
    name="q2.csv",
    data_set_id=42,
    description="Q2 production")

uploaded = client.files.upload_file(upload)   # -> list[INode]
```

</TabItem>
<TabItem value="rust" label="Rust">

```rust
use dataplatform_rust_sdk::files::FileUpload;

// mime type is inferred from the file content
let mut upload = FileUpload::new_with_destination_path("report.csv", "/reports/2026/");
upload.set_external_id("report_2026_q2".into());
upload.set_file_name("q2.csv".into());
upload.set_data_set_id(42);
upload.set_description("Q2 production".into());
let uploaded = api.files.upload_file(upload).await?;
```

</TabItem>
</Tabs>

## Download {#download}

All three clients download a file's raw bytes by id. Python and Rust add a streaming variant
that writes straight to a path, so a large file never has to sit in memory whole.

<Tabs groupId="lang">
<TabItem value="java" label="Java">

```java
byte[] bytes = client.files().download("99");
Files.write(Path.of("q2.csv"), bytes);
```

</TabItem>
<TabItem value="python" label="Python">

```python
download = client.files.download(99)
print(download.file_name, download.mime_type, len(download))
Path("q2.csv").write_bytes(download.content)

# or stream it to disk, which returns the byte count
written = client.files.download_to_path(99, "q2.csv")
```

</TabItem>
<TabItem value="rust" label="Rust">

```rust
let download = api.files.download(99).await?;
std::fs::write("q2.csv", &download.bytes)?;

// or stream it to disk, which returns the byte count
let written = api.files.download_to_path(99, "q2.csv").await?;
```

</TabItem>
</Tabs>

## Delete

<Tabs groupId="lang">
<TabItem value="java" label="Java">

```java
client.files().delete(List.of(IdCollection.createFromExternalId("report_2026_q2")));
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

## What each client covers {#client-coverage}

| Operation | Java | Python | Rust |
| --- | --- | --- | --- |
| List root | `files().list()` | `files.list_root_directory` | `files.list_root_directory` |
| List a path | `files().list(path)` | `files.list_directory_by_path` | `files.list_directory_by_path` |
| Upload | `files().upload` | `files.upload_file` | `files.upload_file` |
| Download | `files().download` | `files.download` / `files.download_to_path` | `files.download` / `files.download_to_path` |
| Delete | `files().delete` | `files.delete` | `files.delete` |

Python and Rust add `download_to_path`, which streams to disk instead of holding the whole
file in memory — see [Download](#download).
