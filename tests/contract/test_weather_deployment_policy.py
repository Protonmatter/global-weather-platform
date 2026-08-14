import os
import shutil
import subprocess
from importlib import import_module
from pathlib import Path
from typing import Any

import pytest
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


def test_ingestion_namespace_denies_unapproved_pod_egress_by_default() -> None:
    items = documents("deploy/k8s/weather-acquisition.yaml")
    deny = find(items, "CiliumNetworkPolicy", "weather-ingestion-default-deny")
    assert deny["metadata"]["namespace"] == "weather-ingestion"
    assert deny["spec"]["endpointSelector"] == {}
    assert deny["spec"]["ingress"] == []
    assert deny["spec"]["egress"] == []


def test_acquisition_egress_is_limited_to_declared_provider_names() -> None:
    items = documents("deploy/k8s/weather-acquisition.yaml")
    policy = find(items, "CiliumNetworkPolicy", "weather-acquisition-provider-egress")
    egress = policy["spec"]["egress"]
    provider_rules = [rule for rule in egress if rule.get("toFQDNs")]
    assert len(provider_rules) == 1

    provider_rule = provider_rules[0]
    names = {item["matchName"] for item in provider_rule["toFQDNs"]}
    assert names == {
        "noaa-gfs-bdp-pds.s3.amazonaws.com",
        "noaa-gefs-pds.s3.amazonaws.com",
        "api.openweathermap.org",
    }

    to_ports = provider_rule["toPorts"]
    assert to_ports == [
        {
            "ports": [
                {
                    "port": "443",
                    "protocol": "TCP",
                }
            ]
        }
    ]
    assert all("rules" not in port_rule for port_rule in to_ports)


def test_acquisition_dns_queries_are_observed_by_cilium_proxy() -> None:
    items = documents("deploy/k8s/weather-acquisition.yaml")
    policy = find(items, "CiliumNetworkPolicy", "weather-acquisition-provider-egress")
    egress = policy["spec"]["egress"]
    dns_rules = [
        rule
        for rule in egress
        if any(
            endpoint.get("matchLabels", {}).get("k8s:k8s-app") == "kube-dns"
            for endpoint in rule.get("toEndpoints", [])
        )
    ]
    assert len(dns_rules) == 1

    dns_port_rule = dns_rules[0]["toPorts"][0]
    assert "rules" in dns_port_rule
    dns = dns_port_rule["rules"]["dns"]
    assert {item["matchName"] for item in dns if "matchName" in item} == {
        "noaa-gfs-bdp-pds.s3.amazonaws.com",
        "noaa-gefs-pds.s3.amazonaws.com",
        "api.openweathermap.org",
    }
    assert {"matchPattern": "*.cluster.local"} in dns


def test_serving_namespace_denies_arbitrary_egress() -> None:
    items = documents("deploy/k8s/weather-serving-network-policy.yaml")
    deny = find(items, "NetworkPolicy", "weather-serving-default-deny")
    assert deny["metadata"]["namespace"] == "weather-serving"
    assert deny["spec"]["podSelector"] == {}
    assert deny["spec"]["policyTypes"] == ["Ingress", "Egress"]
    assert deny["spec"]["ingress"] == []
    assert deny["spec"]["egress"] == []


def test_acquisition_manifest_uses_an_immutable_image_placeholder() -> None:
    items = documents("deploy/k8s/weather-acquisition.yaml")
    deployment = find(items, "Deployment", "weather-gfs-acquisition")
    image = deployment["spec"]["template"]["spec"]["containers"][0]["image"]
    assert image == "weather-platform-runtime@sha256:" + "0" * 64
    assert ":0.1.0" not in image


def test_release_renderer_requires_a_real_digest(tmp_path) -> None:
    module = import_module("scripts.render_release_manifest")
    source = tmp_path / "source.yaml"
    output = tmp_path / "output.yaml"
    source.write_text(
        "image: weather-platform-runtime@sha256:" + "0" * 64 + "\n",
        encoding="utf-8",
    )
    image = "registry.example/weather/platform@sha256:" + "b" * 64
    module.render_manifest(source, output, image)
    assert f"image: {image}" in output.read_text(encoding="utf-8")
    for invalid in (
        "registry.example/weather/platform:latest",
        "registry.example/weather/platform@sha256:" + "0" * 64,
        "https://registry.example/weather/platform@sha256:" + "b" * 64,
        "registry.example//weather/platform@sha256:" + "b" * 64,
    ):
        with pytest.raises(ValueError):
            module.validate_image_reference(invalid)

    with pytest.raises(ValueError, match="expected repository"):
        module.validate_image_reference(
            image,
            expected_repository="registry.example/other/platform",
        )


def test_release_workflow_binds_evidence_to_the_built_repository() -> None:
    workflow = yaml.safe_load((ROOT / ".github/workflows/build-image.yml").read_text("utf-8"))
    render_step = next(
        step
        for step in workflow["jobs"]["build"]["steps"]
        if step["name"] == "Render immutable release evidence"
    )
    assert "--expected-repository" in render_step["run"]
    assert "${{ vars.INTERNAL_REGISTRY }}/weather/platform" in render_step["run"]


def test_integration_workflow_installs_from_the_checked_lock() -> None:
    workflow = yaml.safe_load(
        (ROOT / ".github/workflows/weather-integration.yml").read_text("utf-8")
    )
    install_step = next(
        step
        for step in workflow["jobs"]["integration"]["steps"]
        if step["name"] == "Install with ecCodes"
    )
    command = install_step["run"]
    assert "--require-hashes" in command
    assert "requirements/ci.lock" in command
    assert "--no-build-isolation" in command
    assert "--no-deps" in command


def test_runtime_image_installs_the_locked_eccodes_extra() -> None:
    dockerfile = (ROOT / "deploy/docker/Dockerfile").read_text(encoding="utf-8")
    assert "global-weather-platform[eccodes]" in dockerfile


def test_image_build_uses_a_job_local_python_environment(tmp_path: Path) -> None:
    bash_override = os.environ.get("GWP_TEST_BASH")
    if os.name == "nt" and bash_override is None:
        pytest.skip("set GWP_TEST_BASH to a Git Bash executable on Windows")
    bash = bash_override or shutil.which("bash")
    if bash is None:
        pytest.skip("bash is required to execute the Linux image-build contract")

    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    command_log = tmp_path / "commands.log"
    fake_python = fake_bin / "python3.12"
    fake_python.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
printf 'system:%s\\n' "$*" >> "$COMMAND_LOG"
if [[ "${1:-}" == "-m" && "${2:-}" == "venv" ]]; then
  mkdir -p "$3/bin"
  cat > "$3/bin/python" <<'PYTHON'
#!/usr/bin/env bash
set -euo pipefail
printf 'venv:%s\\n' "$*" >> "$COMMAND_LOG"
PYTHON
  chmod +x "$3/bin/python"
fi
""",
        encoding="utf-8",
        newline="\n",
    )
    fake_python.chmod(0o755)
    fake_docker = fake_bin / "docker"
    fake_docker.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
printf 'docker:%s\\n' "$*" >> "$COMMAND_LOG"
""",
        encoding="utf-8",
        newline="\n",
    )
    fake_docker.chmod(0o755)
    requirements = tmp_path / "requirements"
    requirements.mkdir()
    (requirements / "production.lock").write_text("", encoding="utf-8")

    environment = os.environ.copy()
    environment.update(
        {
            "BASE_IMAGE": "registry.example/python@sha256:" + "a" * 64,
            "IMAGE": "registry.example/weather/platform:test",
            "PIP_INDEX_URL": "https://packages.example/simple",
        }
    )
    build_script = ROOT / "scripts/build_image.sh"
    if os.name == "nt":
        environment.update(
            {
                "BUILD_SCRIPT_WINDOWS": str(build_script),
                "COMMAND_LOG_WINDOWS": str(command_log),
                "FAKE_BIN_WINDOWS": str(fake_bin),
            }
        )
        command = [
            bash,
            "-lc",
            'export COMMAND_LOG="$(cygpath -u "$COMMAND_LOG_WINDOWS")"; '
            'export PATH="$(cygpath -u "$FAKE_BIN_WINDOWS"):$PATH"; '
            'bash "$(cygpath -u "$BUILD_SCRIPT_WINDOWS")"',
        ]
    else:
        environment["COMMAND_LOG"] = str(command_log)
        environment["PATH"] = f"{fake_bin}{os.pathsep}{environment['PATH']}"
        command = [bash, str(build_script)]

    subprocess.run(command, cwd=tmp_path, env=environment, check=True)

    commands = command_log.read_text(encoding="utf-8").splitlines()
    assert commands[0].startswith("system:-m venv ")
    assert not any(command.startswith("system:-m pip ") for command in commands)
    assert sum(command.startswith("venv:-m pip ") for command in commands) == 3
    assert any(command.startswith("docker:build ") for command in commands)
