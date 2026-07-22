# Network boundary

## Policy

Production workloads are deny-by-default for ingress and egress. External acquisition is isolated to approved refresh workers. Forecast, API, model, calibration, and visualization services do not make arbitrary provider calls.

## Capable transports

The boundary inventory includes:

- DNS and NTP;
- HTTP and HTTPS;
- MQTT and MQTT over TLS;
- SSH, SFTP, and SCP;
- SMTP when explicitly enabled;
- object-store APIs;
- OCI registry traffic;
- package-manager traffic;
- Git traffic;
- OpenTelemetry exporters;
- webhooks;
- cloud metadata endpoints;
- database protocols;
- message-broker protocols.

## Telemetry

Third-party telemetry is disabled. OpenTelemetry is opt-in and valid only when `WEATHER_INTERNAL_OTEL_ENDPOINT` identifies an approved internal collector. The application does not fall back to a public collector.

## Credentials

Credentials must be short-lived where supported, redacted from logs, and never embedded in source data, model artifacts, traces, metrics labels, or provenance records.

## Acquisition transport verification

Acquisition workers verify each source's observed TLS issuer chain against a per-source pin and reject any unpinned issuer as an interception indicator, refuse unauthenticated schemes, and verify the upstream-published checksum before retention (`weather_platform.ingestion.transport_trust`). The verification core is implemented and tested; the live MQTT/HTTPS wiring that supplies the observed chain is deployment-specific and not yet wired.
