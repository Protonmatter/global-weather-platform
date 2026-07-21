# Immutable raw object store

## Purpose

Every acquired source record is preserved before a decoder, quality-control rule, or canonical transformation can modify its interpretation. The first implementation uses a local filesystem backend with the same behavioral contract required from later object-storage backends.

## Addressing

The content address is:

```text
sha256:<64 lowercase hexadecimal characters>
```

The canonical provenance URI is:

```text
cas://sha256/<64 lowercase hexadecimal characters>
```

Filesystem objects are sharded as:

```text
<root>/sha256/<hex[0:2]>/<hex[2:4]>/<hex[4:]>
```

## Invariants

1. The exact input bytes are hashed before decoding.
2. Object creation uses exclusive creation and never overwrites an existing path.
3. Reusing an existing digest re-reads and verifies the complete object.
4. Symlinks and non-regular files are rejected.
5. Objects are made read-only after a durable write and parent-directory synchronization.
6. Canonical observations carry both the digest and `cas://` URI.
7. Canonical observation IDs are deterministic over source digest, decoder version, and record index.
8. Replaying the same source bytes with the same decoder version does not append a duplicate canonical observation.
9. Decoder failure does not remove the retained source object.

## Corruption response

A digest mismatch, content mismatch, unsafe file type, or unsafe open operation raises `RawObjectCorruptionError`. The caller must quarantine the affected object path and prevent derived products from using it. The implementation does not silently repair or overwrite corrupted evidence.

## Backend migration contract

An S3-compatible or distributed backend may replace the filesystem implementation only when it preserves:

- SHA-256 addressing;
- write-once semantics;
- full-object integrity verification;
- deterministic `cas://sha256/` references;
- idempotent duplicate ingestion;
- retention of failed-to-decode source records;
- auditable storage and retrieval failures.
