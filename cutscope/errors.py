class CutscopeError(Exception):
    """A user-actionable CUTSCOPE failure."""


class ConfigurationError(CutscopeError):
    """Required local configuration is missing or malformed."""


class TelemetryUnavailable(CutscopeError):
    """Grafana OTLP could not accept a required telemetry signal."""


class VertexCredentialsUnavailable(CutscopeError):
    """Application Default Credentials were not available to Vertex AI."""
