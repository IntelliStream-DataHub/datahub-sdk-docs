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

The server takes one path, `X-Datahub-Path`: the full path of the file including its name
(`/reports/2026/q2.csv`), from which it splits the name off the last `/`. The Java client
sends the `path` you give it as-is, so include the file name and a leading `/`. The Python
and Rust clients take a `destination_path` folder plus a `name` (defaulting to the local
file's name) and join the two into that same full path. The Java client uploads raw `content`
bytes; the Python and Rust clients read a local file.

<Tabs groupId="lang">
<TabItem value="java" label="Java">

```java
byte[] content = Files.readAllBytes(Path.of("report.csv"));

DataWrapper<IndexNode> uploaded = client.files().upload(
        FileUploadRequest.builder()
                .path("/reports/2026/q2.csv")
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
import intellistream_datahub_sdk

upload = intellistream_datahub_sdk.FileUpload(
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
use intellistream_datahub_sdk::files::FileUpload;

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

The upload echo carries the stored node, id included. Read it back from the folder listing:

<Tabs groupId="lang">
<TabItem value="java" label="Java">

```java
client.files().list("/reports/2026").getItems()
        .forEach(n -> System.out.println(n.getId() + "  " + n.getName() + "  " + n.getSize()));
```

</TabItem>
<TabItem value="python" label="Python">

```python
for node in client.files.list_directory_by_path("/reports/2026"):
    print(node.id, node.name, node.size)
```

</TabItem>
<TabItem value="rust" label="Rust">

```rust
for node in api.files.list_directory_by_path("/reports/2026").await?.get_items() {
    println!("{:?}  {}  {}", node.id, node.name, node.size);
}
```

</TabItem>
</Tabs>

### When it fails {#errors}

| Status | Means |
| --- | --- |
| `403` | You lack write access to the data set named in `dataSetId`, or to the parent folder's data set. |
| `404` | On download: no file with that id, or a file in a data set you may not read. The two are not distinguished, so a hidden file's existence is not leaked. |
| `409` | A file with that path, or that `externalId`, already exists. Uniqueness is tenant-wide, not per data set. |

There is no size cap on `PUT /files`: the upload streams to disk and is exempt from the
[request-body limit](./limits#request-body-size).

## Download {#download}

All three clients download a file's raw bytes by id. The id is numeric: Python and Rust take
it as an integer, Java as a string, because the endpoint also accepts an external id in that
position (`download("report_2026_q2")` works in Java). Python and Rust add a streaming variant
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
use intellistream_datahub_sdk::generic::{DataWrapper, IdAndExtId};

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
file in memory, see [Download](#download).
