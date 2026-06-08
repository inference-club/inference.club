"""Server-side validation for the agent service manifest.

The agent ships parsed JSON (it already parsed the YAML on its side); we
re-validate the structure here. Mirrors the agent's checks. Pure-Python,
no external deps.

See `docs/plans/service-manifest.md` for the YAML shape and field
semantics.
"""

from __future__ import annotations

from urllib.parse import urlparse

GPU_VENDORS = {"nvidia", "amd", "apple", "intel"}
ENGINES = {"vllm", "lmstudio", "ollama", "sglang", "llamacpp", "tgi", "other"}
# What a service provides (orthogonal to engine). Defaults to "llm" when a
# service omits ``type``, so manifests written before this field stay valid.
# "tts" is accepted now — the agent and server stay in lockstep for the next
# modality — even though no TTS endpoint ships yet. "mesh" is image-to-3D
# (e.g. TRELLIS.2): one image in, a textured GLB out.
SERVICE_TYPES = {"llm", "stt", "tts", "image", "mesh", "music"}

# Limits — see `docs/plans/service-manifest.md` §6.
MAX_RAW_YAML_BYTES = 64 * 1024
MAX_HOSTS = 50
MAX_SERVICES = 100
MAX_STRING_LEN = 1024
SUPPORTED_SCHEMA_VERSIONS = {1}


class ManifestError(str):
    """Marker — currently we just collect plain strings, but kept as a type
    hint for callers that want to grep for error origins."""


def validate(parsed: dict, raw_yaml: str = "") -> list[str]:
    """Validate a parsed manifest. Returns a list of human-readable error
    strings. Empty list ⇒ valid.

    Always inspects the whole structure rather than short-circuiting on the
    first error, so the operator gets one round-trip with everything wrong
    instead of fix-one-find-next.
    """
    errors: list[str] = []

    if raw_yaml and len(raw_yaml.encode("utf-8")) > MAX_RAW_YAML_BYTES:
        errors.append(
            f"raw_yaml exceeds {MAX_RAW_YAML_BYTES} bytes "
            f"(got {len(raw_yaml.encode('utf-8'))})"
        )

    if not isinstance(parsed, dict):
        return [f"manifest root must be an object, got {type(parsed).__name__}"]

    schema_version = parsed.get("schema_version")
    if schema_version not in SUPPORTED_SCHEMA_VERSIONS:
        errors.append(
            f"schema_version must be one of {sorted(SUPPORTED_SCHEMA_VERSIONS)}, "
            f"got {schema_version!r}"
        )

    agent = parsed.get("agent")
    if not isinstance(agent, dict):
        errors.append("agent: required object missing")
    else:
        name = agent.get("name")
        if not isinstance(name, str) or not name.strip():
            errors.append("agent.name: required non-empty string")
        elif len(name) > MAX_STRING_LEN:
            errors.append(f"agent.name: exceeds {MAX_STRING_LEN} chars")

    hosts = parsed.get("hosts")
    if not isinstance(hosts, list):
        errors.append("hosts: required list (may be empty)")
        return errors  # nothing else we can check

    if len(hosts) > MAX_HOSTS:
        errors.append(f"hosts: exceeds {MAX_HOSTS} entries (got {len(hosts)})")

    seen_host_ids: set[str] = set()
    seen_service_names: set[str] = set()
    total_services = 0

    for h_idx, host in enumerate(hosts):
        prefix = f"hosts[{h_idx}]"
        if not isinstance(host, dict):
            errors.append(f"{prefix}: must be an object")
            continue

        host_id = host.get("id")
        if not isinstance(host_id, str) or not host_id.strip():
            errors.append(f"{prefix}.id: required non-empty string")
        elif len(host_id) > MAX_STRING_LEN:
            errors.append(f"{prefix}.id: exceeds {MAX_STRING_LEN} chars")
        elif host_id in seen_host_ids:
            errors.append(f"{prefix}.id: duplicate host id {host_id!r}")
        else:
            seen_host_ids.add(host_id)

        gpu = host.get("gpu")
        if gpu is not None:
            if not isinstance(gpu, dict):
                errors.append(f"{prefix}.gpu: must be an object if present")
            else:
                vendor = gpu.get("vendor")
                if vendor is not None and vendor not in GPU_VENDORS:
                    errors.append(
                        f"{prefix}.gpu.vendor: must be one of "
                        f"{sorted(GPU_VENDORS)}, got {vendor!r}"
                    )
                vram = gpu.get("vram_gb")
                if vram is not None and (not isinstance(vram, (int, float)) or vram < 0):
                    errors.append(f"{prefix}.gpu.vram_gb: must be a non-negative number")
                count = gpu.get("count", 1)
                if not isinstance(count, int) or count < 1:
                    errors.append(f"{prefix}.gpu.count: must be a positive integer")

        for field in ("hostname", "address", "notes"):
            val = host.get(field)
            if val is not None and (
                not isinstance(val, str) or len(val) > MAX_STRING_LEN
            ):
                errors.append(
                    f"{prefix}.{field}: must be a string up to {MAX_STRING_LEN} chars"
                )

        services = host.get("services", [])
        if not isinstance(services, list):
            errors.append(f"{prefix}.services: must be a list (may be empty)")
            continue

        for s_idx, svc in enumerate(services):
            total_services += 1
            sprefix = f"{prefix}.services[{s_idx}]"
            if not isinstance(svc, dict):
                errors.append(f"{sprefix}: must be an object")
                continue

            sname = svc.get("name")
            if not isinstance(sname, str) or not sname.strip():
                errors.append(f"{sprefix}.name: required non-empty string")
            elif len(sname) > MAX_STRING_LEN:
                errors.append(f"{sprefix}.name: exceeds {MAX_STRING_LEN} chars")
            elif sname in seen_service_names:
                errors.append(
                    f"{sprefix}.name: duplicate service name {sname!r} "
                    "(must be unique across the whole manifest)"
                )
            else:
                seen_service_names.add(sname)

            engine = svc.get("engine")
            if engine not in ENGINES:
                errors.append(
                    f"{sprefix}.engine: must be one of {sorted(ENGINES)}, "
                    f"got {engine!r}"
                )

            # ``type`` is optional and defaults to "llm"; only an explicit
            # out-of-set value is an error.
            svc_type = svc.get("type")
            if svc_type is not None and svc_type not in SERVICE_TYPES:
                errors.append(
                    f"{sprefix}.type: must be one of {sorted(SERVICE_TYPES)}, "
                    f"got {svc_type!r}"
                )

            # ``features`` is optional — a list of capability strings the
            # operator declares for this deployment (e.g. ["timestamps"]).
            features = svc.get("features")
            if features is not None:
                if not isinstance(features, list) or not all(
                    isinstance(f, str) for f in features
                ):
                    errors.append(f"{sprefix}.features: must be a list of strings")

            url = svc.get("url")
            if not isinstance(url, str) or not url.strip():
                errors.append(f"{sprefix}.url: required non-empty string")
            else:
                parsed_url = urlparse(url)
                if not parsed_url.scheme or not parsed_url.netloc:
                    errors.append(
                        f"{sprefix}.url: must be an absolute URL with scheme "
                        f"and host (got {url!r})"
                    )

            models = svc.get("models")
            if models is not None:
                if not isinstance(models, list):
                    errors.append(f"{sprefix}.models: must be a list if present")
                else:
                    for m_idx, m in enumerate(models):
                        mprefix = f"{sprefix}.models[{m_idx}]"
                        mid = m.get("id") if isinstance(m, dict) else None
                        hf = m.get("hf") if isinstance(m, dict) else None
                        has_id = isinstance(mid, str) and mid.strip()
                        has_hf = isinstance(hf, str) and hf.strip()
                        if not isinstance(m, dict) or not (has_id or has_hf):
                            errors.append(
                                f"{mprefix}: each entry needs a "
                                "string `id` or `hf` (HuggingFace repo id)"
                            )
                            continue
                        if hf is not None and not isinstance(hf, str):
                            errors.append(f"{mprefix}.hf: must be a string")

                        # --- operator-declared capabilities (all optional) ---
                        for field in ("name", "quantization"):
                            val = m.get(field)
                            if val is not None and (
                                not isinstance(val, str) or len(val) > MAX_STRING_LEN
                            ):
                                errors.append(
                                    f"{mprefix}.{field}: must be a string up to "
                                    f"{MAX_STRING_LEN} chars"
                                )
                        for field in ("input_modalities", "output_modalities", "features"):
                            val = m.get(field)
                            if val is not None and (
                                not isinstance(val, list)
                                or not all(
                                    isinstance(x, str) and len(x) <= MAX_STRING_LEN
                                    for x in val
                                )
                            ):
                                errors.append(
                                    f"{mprefix}.{field}: must be a list of strings"
                                )
                        ctx = m.get("context_length")
                        if ctx is not None and (not isinstance(ctx, int) or ctx < 0):
                            errors.append(
                                f"{mprefix}.context_length: must be a non-negative integer"
                            )

            for field in ("command",):
                val = svc.get(field)
                if val is not None and (
                    not isinstance(val, str) or len(val) > MAX_STRING_LEN
                ):
                    errors.append(
                        f"{sprefix}.{field}: must be a string up to "
                        f"{MAX_STRING_LEN} chars"
                    )

            extra = svc.get("extra")
            if extra is not None and not isinstance(extra, dict):
                errors.append(f"{sprefix}.extra: must be an object if present")

    if total_services > MAX_SERVICES:
        errors.append(
            f"services: exceeds {MAX_SERVICES} entries across all hosts "
            f"(got {total_services})"
        )

    return errors
