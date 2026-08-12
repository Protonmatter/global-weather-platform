from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]


def documents(path: str) -> list[dict[str, Any]]:
    loaded = list(yaml.safe_load_all((ROOT / path).read_text(encoding="utf-8")))
    return [item for item in loaded if isinstance(item, dict)]


def find(items: list[dict[str, Any]], kind: str, name: str) -> dict[str, Any]:
    for item in items:
        metadata = item.get("metadata", {})
        if item.get("kind") == kind and metadata.get("name") == name:
            return item
    raise AssertionError(f"missing {kind}/{name}")


def test_acquisition_workload_is_hardened_and_resource_bounded() -> None:
    items = documents("deploy/k8s/weather-acquisition.yaml")
    deployment = find(items, "Deployment", "weather-gfs-acquisition")
    pod_spec = deployment["spec"]["template"]["spec"]
    container = pod_spec["containers"][0]

    assert pod_spec["serviceAccountName"] == "weather-acquisition"
    assert pod_spec["securityContext"]["runAsNonRoot"] is True
    assert pod_spec["securityContext"]["seccompProfile"]["type"] == "RuntimeDefault"

    security = container["securityContext"]
    assert security["allowPrivilegeEscalation"] is False
    assert security["readOnlyRootFilesystem"] is True
    assert security["capabilities"]["drop"] == ["ALL"]

    resources = container["resources"]
    assert resources["requests"]["cpu"]
    assert resources["requests"]["memory"]
    assert resources["limits"]["cpu"]
    assert resources["limits"]["memory"]


def test_acquisition_egress_is_limited_to_declared_provider_names() -> None:
    items = documents("deploy/k8s/weather-acquisition.yaml")
    policy = find(items, "CiliumNetworkPolicy", "weather-acquisition-provider-egress")
    egress = policy["spec"]["egress"]
    names = {
        item["matchName"]
        for rule in egress
        for item in rule.get("toFQDNs", [])
        if "matchName" in item
    }
    assert names == {
        "noaa-gfs-bdp-pds.s3.amazonaws.com",
        "noaa-gefs-pds.s3.amazonaws.com",
        "api.openweathermap.org",
    }
    assert all(rule.get("toPorts") for rule in egress)


def test_serving_namespace_denies_arbitrary_egress() -> None:
    items = documents("deploy/k8s/weather-serving-network-policy.yaml")
    deny = find(items, "NetworkPolicy", "weather-serving-default-deny")
    assert deny["metadata"]["namespace"] == "weather-serving"
    assert deny["spec"]["podSelector"] == {}
    assert deny["spec"]["policyTypes"] == ["Ingress", "Egress"]
    assert deny["spec"]["ingress"] == []
    assert deny["spec"]["egress"] == []
