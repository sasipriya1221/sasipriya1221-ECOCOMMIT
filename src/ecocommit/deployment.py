from __future__ import annotations

import importlib
import ipaddress
import json
import os
import re
from dataclasses import dataclass
from http import HTTPStatus
from pathlib import Path
from typing import Iterable, Mapping, Protocol

from .api import MAX_JSON_BODY_BYTES
from .audit import AppendOnlyAuditLog


TLS_TERMINATION_POLICY = "TRUSTED_REVERSE_PROXY"
EDGE_RATE_LIMIT_POLICY = "EXTERNAL_SHARED_LIMITER_REQUIRED"
SUPPORTED_PROVIDER_MODES = frozenset({"DISABLED", "RAZORPAY_TEST_MODE"})
_SHA256_HEX = re.compile(r"^[0-9a-f]{64}$")
_DNS_LABEL = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
_EVIDENCE_ENVIRONMENT = (
    "ECOCOMMIT_D_EVIDENCE_ROOT",
    "ECOCOMMIT_D_PINS_PATH",
    "ECOCOMMIT_D_PINS_SHA256",
)
_PREPARED_ENVIRONMENT = (
    "ECOCOMMIT_D_PREPARED_OPERATION_PATH",
    "ECOCOMMIT_D_PREPARED_OPERATION_SHA256",
    "ECOCOMMIT_D_STATE_DB_PATH",
)


class DeploymentConfigurationError(ValueError):
    """Raised when the hosted deployment contract is incomplete or unsafe."""


class WSGIApplication(Protocol):
    def __call__(self, environ: Mapping[str, object], start_response) -> Iterable[bytes]: ...


def _required_value(environment: Mapping[str, str], name: str) -> str:
    value = environment.get(name)
    if value is None or value == "":
        raise DeploymentConfigurationError(f"{name} is required")
    if value != value.strip():
        raise DeploymentConfigurationError(
            f"{name} must not contain leading or trailing whitespace"
        )
    return value


def _optional_group(
    environment: Mapping[str, str],
    names: tuple[str, ...],
) -> tuple[str | None, ...]:
    values: tuple[str | None, ...] = tuple(
        environment.get(name) if environment.get(name) not in (None, "") else None
        for name in names
    )
    if any(value is not None for value in values) and not all(
        value is not None for value in values
    ):
        raise DeploymentConfigurationError(
            f"{', '.join(names)} must be supplied together"
        )
    for name, value in zip(names, values, strict=True):
        if value is not None and value != value.strip():
            raise DeploymentConfigurationError(
                f"{name} must not contain leading or trailing whitespace"
            )
    return values


def _absolute_path(value: str, name: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        raise DeploymentConfigurationError(f"{name} must be an absolute path")
    return path.absolute()


def _validate_sha256(value: str, name: str) -> str:
    if not _SHA256_HEX.fullmatch(value):
        raise DeploymentConfigurationError(
            f"{name} must be a lowercase 64-character SHA-256 digest"
        )
    return value


def _validate_public_host(value: str) -> str:
    if value != value.lower() or value.endswith("."):
        raise DeploymentConfigurationError(
            "ECOCOMMIT_D_PUBLIC_HOST must be a lowercase DNS hostname without a trailing dot"
        )
    if any(character in value for character in ("*", ":", "/", "@")):
        raise DeploymentConfigurationError(
            "ECOCOMMIT_D_PUBLIC_HOST must be one exact DNS hostname without scheme, wildcard, or port"
        )
    labels = value.split(".")
    if len(value) > 253 or len(labels) < 2 or not all(
        _DNS_LABEL.fullmatch(label) for label in labels
    ):
        raise DeploymentConfigurationError(
            "ECOCOMMIT_D_PUBLIC_HOST must be one valid multi-label DNS hostname"
        )
    return value


def _trusted_proxy_networks(value: str) -> tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...]:
    networks: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = []
    for item in value.split(","):
        candidate = item.strip()
        if not candidate:
            raise DeploymentConfigurationError(
                "ECOCOMMIT_D_TRUSTED_PROXY_CIDRS contains an empty CIDR"
            )
        try:
            network = ipaddress.ip_network(candidate, strict=True)
        except ValueError as exc:
            raise DeploymentConfigurationError(
                "ECOCOMMIT_D_TRUSTED_PROXY_CIDRS must contain canonical CIDRs"
            ) from exc
        if network.prefixlen == 0:
            raise DeploymentConfigurationError(
                "ECOCOMMIT_D_TRUSTED_PROXY_CIDRS must not trust the entire Internet"
            )
        if network in networks:
            raise DeploymentConfigurationError(
                "ECOCOMMIT_D_TRUSTED_PROXY_CIDRS must not contain duplicates"
            )
        networks.append(network)
    return tuple(networks)


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


def _same_file_target(first: Path, second: Path) -> bool:
    """Detect both lexical aliases and existing hard-link aliases.

    ``resolve`` alone cannot distinguish two different path names backed by the
    same inode/file ID.  That distinction matters here because the append-only
    audit stream must never share storage with the mutable SQLite state file.
    """

    if first.resolve() == second.resolve():
        return True
    if not first.exists() or not second.exists():
        return False
    try:
        return os.path.samefile(first, second)
    except OSError as exc:
        raise DeploymentConfigurationError(
            "state database and audit log identity could not be verified"
        ) from exc


@dataclass(frozen=True)
class DeploymentConfig:
    """Provider-neutral host contract for the current single-host D runtime.

    Passing this contract proves only that local configuration is coherent. It
    does not prove DNS, public routing, TLS, backup, monitoring, or Checkpoint D.
    """

    public_host: str
    trusted_proxy_networks: tuple[
        ipaddress.IPv4Network | ipaddress.IPv6Network, ...
    ]
    persistent_root: Path
    audit_path: Path
    provider_mode: str
    evidence_root: Path | None = None
    pins_path: Path | None = None
    pins_sha256: str | None = None
    prepared_operation_path: Path | None = None
    prepared_operation_sha256: str | None = None
    state_db_path: Path | None = None

    @classmethod
    def from_environment(cls, environment: Mapping[str, str]) -> DeploymentConfig:
        if _required_value(environment, "ECOCOMMIT_D_TLS_TERMINATION") != TLS_TERMINATION_POLICY:
            raise DeploymentConfigurationError(
                f"ECOCOMMIT_D_TLS_TERMINATION must equal {TLS_TERMINATION_POLICY}"
            )
        if _required_value(environment, "ECOCOMMIT_D_EDGE_RATE_LIMITING") != EDGE_RATE_LIMIT_POLICY:
            raise DeploymentConfigurationError(
                "ECOCOMMIT_D_EDGE_RATE_LIMITING must acknowledge the required external shared limiter"
            )
        numeric_values = {
            name: _required_value(environment, name)
            for name in (
                "ECOCOMMIT_D_WORKER_COUNT",
                "ECOCOMMIT_D_INSTANCE_COUNT",
                "ECOCOMMIT_D_MAX_REQUEST_BODY_BYTES",
            )
        }
        if any(
            re.fullmatch(r"(?:0|[1-9][0-9]*)", value) is None
            for value in numeric_values.values()
        ):
            raise DeploymentConfigurationError(
                "worker, instance, and request-size values must be canonical decimal integers"
            )
        worker_count = int(numeric_values["ECOCOMMIT_D_WORKER_COUNT"])
        instance_count = int(numeric_values["ECOCOMMIT_D_INSTANCE_COUNT"])
        max_body_bytes = int(numeric_values["ECOCOMMIT_D_MAX_REQUEST_BODY_BYTES"])
        if worker_count != 1 or instance_count != 1:
            raise DeploymentConfigurationError(
                "the current SQLite and in-process limiter boundary requires exactly one instance and one WSGI worker"
            )
        if max_body_bytes != MAX_JSON_BODY_BYTES:
            raise DeploymentConfigurationError(
                f"ECOCOMMIT_D_MAX_REQUEST_BODY_BYTES must equal {MAX_JSON_BODY_BYTES}"
            )

        public_host = _validate_public_host(
            _required_value(environment, "ECOCOMMIT_D_PUBLIC_HOST")
        )
        proxy_networks = _trusted_proxy_networks(
            _required_value(environment, "ECOCOMMIT_D_TRUSTED_PROXY_CIDRS")
        )
        persistent_root_value = _required_value(
            environment,
            "ECOCOMMIT_D_PERSISTENT_ROOT",
        )
        persistent_root_requested = Path(persistent_root_value)
        if persistent_root_requested.is_symlink():
            raise DeploymentConfigurationError(
                "ECOCOMMIT_D_PERSISTENT_ROOT must be an existing non-symlink directory"
            )
        persistent_root = _absolute_path(
            persistent_root_value,
            "ECOCOMMIT_D_PERSISTENT_ROOT",
        ).resolve()
        if not persistent_root.is_dir():
            raise DeploymentConfigurationError(
                "ECOCOMMIT_D_PERSISTENT_ROOT must be an existing non-symlink directory"
            )
        audit_path = _absolute_path(
            _required_value(environment, "ECOCOMMIT_D_AUDIT_PATH"),
            "ECOCOMMIT_D_AUDIT_PATH",
        )
        if not _is_within(audit_path, persistent_root) or audit_path == persistent_root:
            raise DeploymentConfigurationError(
                "ECOCOMMIT_D_AUDIT_PATH must be a file below ECOCOMMIT_D_PERSISTENT_ROOT"
            )
        if audit_path.exists() and audit_path.is_symlink():
            raise DeploymentConfigurationError("symlinked audit paths are forbidden")

        provider_mode = _required_value(environment, "ECOCOMMIT_D_PROVIDER_MODE")
        if provider_mode not in SUPPORTED_PROVIDER_MODES:
            raise DeploymentConfigurationError(
                "ECOCOMMIT_D_PROVIDER_MODE supports only DISABLED or RAZORPAY_TEST_MODE"
            )

        evidence = _optional_group(environment, _EVIDENCE_ENVIRONMENT)
        prepared = _optional_group(environment, _PREPARED_ENVIRONMENT)
        evidence_root = (
            _absolute_path(str(evidence[0]), _EVIDENCE_ENVIRONMENT[0])
            if evidence[0] is not None
            else None
        )
        pins_path = (
            _absolute_path(str(evidence[1]), _EVIDENCE_ENVIRONMENT[1])
            if evidence[1] is not None
            else None
        )
        pins_sha256 = (
            _validate_sha256(str(evidence[2]), _EVIDENCE_ENVIRONMENT[2])
            if evidence[2] is not None
            else None
        )
        prepared_operation_path = (
            _absolute_path(str(prepared[0]), _PREPARED_ENVIRONMENT[0])
            if prepared[0] is not None
            else None
        )
        prepared_operation_sha256 = (
            _validate_sha256(str(prepared[1]), _PREPARED_ENVIRONMENT[1])
            if prepared[1] is not None
            else None
        )
        state_db_path = (
            _absolute_path(str(prepared[2]), _PREPARED_ENVIRONMENT[2])
            if prepared[2] is not None
            else None
        )

        if provider_mode == "DISABLED" and prepared_operation_path is not None:
            raise DeploymentConfigurationError(
                "prepared operation configuration is forbidden when the provider is disabled"
            )
        if provider_mode == "RAZORPAY_TEST_MODE":
            if evidence_root is None or prepared_operation_path is None:
                raise DeploymentConfigurationError(
                    "RAZORPAY_TEST_MODE requires complete pinned evidence and prepared operation configuration"
                )
            if state_db_path is None or not _is_within(state_db_path, persistent_root):
                raise DeploymentConfigurationError(
                    "ECOCOMMIT_D_STATE_DB_PATH must be below ECOCOMMIT_D_PERSISTENT_ROOT"
                )
            if state_db_path == persistent_root:
                raise DeploymentConfigurationError(
                    "ECOCOMMIT_D_STATE_DB_PATH must name a file below the persistent root"
                )
            if state_db_path.exists() and state_db_path.is_symlink():
                raise DeploymentConfigurationError("symlinked state database paths are forbidden")
            if _same_file_target(state_db_path, audit_path):
                raise DeploymentConfigurationError(
                    "state database and audit log must use different files"
                )

        return cls(
            public_host=public_host,
            trusted_proxy_networks=proxy_networks,
            persistent_root=persistent_root,
            audit_path=audit_path,
            provider_mode=provider_mode,
            evidence_root=evidence_root,
            pins_path=pins_path,
            pins_sha256=pins_sha256,
            prepared_operation_path=prepared_operation_path,
            prepared_operation_sha256=prepared_operation_sha256,
            state_db_path=state_db_path,
        )


class StrictTLSProxyMiddleware:
    """Accept requests only from an explicitly trusted TLS reverse proxy.

    The proxy must replace, rather than append to, every forwarded header. The
    middleware never uses the forwarded client address for authorization or the
    application-level rate limiter.
    """

    def __init__(
        self,
        application: WSGIApplication,
        *,
        public_host: str,
        trusted_proxy_networks: tuple[
            ipaddress.IPv4Network | ipaddress.IPv6Network, ...
        ],
    ) -> None:
        self.application = application
        self.public_host = _validate_public_host(public_host)
        if not trusted_proxy_networks:
            raise DeploymentConfigurationError("at least one trusted proxy CIDR is required")
        if any(network.prefixlen == 0 for network in trusted_proxy_networks):
            raise DeploymentConfigurationError("the entire Internet cannot be a trusted proxy")
        self.trusted_proxy_networks = trusted_proxy_networks

    @staticmethod
    def _reject(start_response, status_code: int, reason: str) -> Iterable[bytes]:
        payload = json.dumps(
            {
                "error": "DEPLOYMENT_BOUNDARY_REJECTED",
                "reason": reason,
                "provider_called": False,
                "money_moved": False,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        status = HTTPStatus(status_code)
        start_response(
            f"{status.value} {status.phrase}",
            [
                ("Content-Type", "application/json; charset=utf-8"),
                ("Content-Length", str(len(payload))),
                ("Cache-Control", "no-store"),
                ("X-Content-Type-Options", "nosniff"),
            ],
        )
        return [payload]

    def _proxy_is_trusted(self, value: object) -> bool:
        try:
            address = ipaddress.ip_address(str(value))
        except ValueError:
            return False
        return any(address in network for network in self.trusted_proxy_networks)

    def __call__(self, environ: Mapping[str, object], start_response) -> Iterable[bytes]:
        if not self._proxy_is_trusted(environ.get("REMOTE_ADDR", "")):
            return self._reject(start_response, 403, "UNTRUSTED_REVERSE_PROXY")
        if str(environ.get("HTTP_FORWARDED", "")):
            return self._reject(start_response, 400, "AMBIGUOUS_FORWARDED_HEADERS")
        if str(environ.get("HTTP_HOST", "")).lower() != self.public_host:
            return self._reject(start_response, 421, "PUBLIC_HOST_MISMATCH")
        if str(environ.get("HTTP_X_FORWARDED_HOST", "")).lower() != self.public_host:
            return self._reject(start_response, 400, "FORWARDED_HOST_MISMATCH")
        if str(environ.get("HTTP_X_FORWARDED_PROTO", "")).lower() != "https":
            return self._reject(start_response, 400, "FORWARDED_TLS_REQUIRED")
        if str(environ.get("HTTP_X_FORWARDED_PORT", "")) != "443":
            return self._reject(start_response, 400, "FORWARDED_TLS_PORT_REQUIRED")
        try:
            ipaddress.ip_address(str(environ.get("HTTP_X_FORWARDED_FOR", "")))
        except ValueError:
            return self._reject(start_response, 400, "SINGLE_FORWARDED_CLIENT_IP_REQUIRED")

        if str(environ.get("HTTP_TRANSFER_ENCODING", "")):
            return self._reject(start_response, 400, "TRANSFER_ENCODING_FORBIDDEN")

        declared_length = str(environ.get("CONTENT_LENGTH") or "0")
        if re.fullmatch(r"(?:0|[1-9][0-9]*)", declared_length) is None:
            return self._reject(start_response, 400, "INVALID_CONTENT_LENGTH")
        body_length = int(declared_length)
        if body_length > MAX_JSON_BODY_BYTES:
            return self._reject(start_response, 413, "REQUEST_BODY_TOO_LARGE")

        secured_environ = dict(environ)
        secured_environ.update(
            {
                "wsgi.url_scheme": "https",
                "HTTPS": "on",
                "SERVER_NAME": self.public_host,
                "SERVER_PORT": "443",
            }
        )

        def hardened_start_response(status, headers, exc_info=None):
            forbidden = {
                "strict-transport-security",
                "permissions-policy",
                "x-frame-options",
            }
            retained = [
                (name, value)
                for name, value in headers
                if name.lower() not in forbidden
            ]
            retained.extend(
                [
                    ("Strict-Transport-Security", "max-age=31536000"),
                    (
                        "Permissions-Policy",
                        "camera=(), geolocation=(), microphone=(), payment=()",
                    ),
                    ("X-Frame-Options", "DENY"),
                ]
            )
            if exc_info is None:
                return start_response(status, retained)
            return start_response(status, retained, exc_info)

        return self.application(secured_environ, hardened_start_response)


def _validate_api_token(environment: Mapping[str, str]) -> str:
    token = environment.get("ECOCOMMIT_D_API_TOKEN", "")
    if not 32 <= len(token) <= 256 or any(
        ord(character) < 33 or ord(character) > 126 for character in token
    ):
        raise DeploymentConfigurationError(
            "ECOCOMMIT_D_API_TOKEN must contain 32 to 256 visible ASCII bytes"
        )
    return token


def _load_authoritative_server_module():
    try:
        return importlib.import_module("scripts.checkpoint_d_server")
    except ModuleNotFoundError as exc:
        raise DeploymentConfigurationError(
            "the production entrypoint must run from the exact ECOCOMMIT source checkout"
        ) from exc


def create_application_from_environment(
    environment: Mapping[str, str] | None = None,
    *,
    server_module=None,
) -> StrictTLSProxyMiddleware:
    """Build the hosted WSGI app without starting a listener or terminating TLS.

    In Test provider mode, the existing runtime performs its read-only provider
    preflight during construction. Callers must therefore build this app only as
    an explicitly authorized deployment startup action.
    """

    source = os.environ if environment is None else environment
    config = DeploymentConfig.from_environment(source)
    server = server_module or _load_authoritative_server_module()

    if config.evidence_root is not None:
        server.load_authoritative_evidence(
            config.evidence_root,
            config.pins_path,
            expected_pins_file_sha256=config.pins_sha256,
        )

    audit_log = AppendOnlyAuditLog(config.audit_path)
    execution_adapter = None
    webhook_processor = None
    provider_credentials_verified = False
    api_bearer_token = None

    if config.provider_mode == "RAZORPAY_TEST_MODE":
        if environment is not None and environment is not os.environ:
            raise DeploymentConfigurationError(
                "RAZORPAY_TEST_MODE must read secrets from the real process environment"
            )
        api_bearer_token = _validate_api_token(source)
        runtime = server.build_prepared_execution_runtime(
            config.prepared_operation_path,
            config.prepared_operation_sha256,
            config.state_db_path,
            audit_log=audit_log,
        )
        execution_adapter = runtime.adapter
        webhook_processor = runtime.webhook_processor
        provider_credentials_verified = True

    application = server.build_application(
        config.audit_path,
        evidence_root=config.evidence_root,
        pins_path=config.pins_path,
        pins_sha256=config.pins_sha256,
        execution_adapter=execution_adapter,
        provider_credentials_verified=provider_credentials_verified,
        api_bearer_token=api_bearer_token,
        webhook_processor=webhook_processor,
        audit_log=audit_log,
    )
    return StrictTLSProxyMiddleware(
        application,
        public_host=config.public_host,
        trusted_proxy_networks=config.trusted_proxy_networks,
    )
