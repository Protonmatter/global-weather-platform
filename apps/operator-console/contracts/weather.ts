export const WEATHER_CONTRACT_VERSION = "1.0.0";

export const guidanceOrigins = [
  "official_warning",
  "imported",
  "platform",
  "experimental",
] as const;

export const qualityDispositions = [
  "accept",
  "accept_with_flags",
  "quarantine",
] as const;

export type GuidanceOrigin = (typeof guidanceOrigins)[number];
export type QualityDisposition = (typeof qualityDispositions)[number];

export type CanonicalObservation = {
  schemaVersion: "1.0.0";
  id: string;
  phenomenon: string;
  value: number | null;
  unit: string;
  uncertainty: number | null;
  longitude: number;
  latitude: number;
  observedAt: string;
  ingestedAt: string;
  qualityDisposition: QualityDisposition;
  qualityFlags: string[];
  sourceId: string;
  sourceDigest: string;
  decoderVersion: string;
  recordIndex: number;
  contentDigest: string;
};

export const edrConformanceClasses = [
  "http://www.opengis.net/spec/ogcapi-common-1/1.0/conf/core",
  "http://www.opengis.net/spec/ogcapi-edr-1/1.1/conf/core",
  "http://www.opengis.net/spec/ogcapi-edr-1/1.1/conf/position",
] as const;
