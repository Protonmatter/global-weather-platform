import { proxyToControlPlane } from "../../../../../lib/weather";

const observationsCollection = {
  id: "observations",
  title: "Canonical observations",
  description:
    "Provenance-bound point observations queryable by position and datetime.",
  crs: ["http://www.opengis.net/def/crs/OGC/1.3/CRS84"],
  output_formats: ["application/geo+json"],
  data_queries: {
    position: {
      link: {
        href: "/api/v1/edr/collections/observations/position",
        rel: "data",
        variables: {
          query_type: "position",
          output_formats: ["application/geo+json"],
        },
      },
    },
  },
};

export async function GET(request: Request) {
  return (
    (await proxyToControlPlane(request, "/v1/edr/collections")) ??
    Response.json({ collections: [observationsCollection] })
  );
}
