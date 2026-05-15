"""Constants for the PromQL integration."""

DOMAIN = "promql"

CONF_PROMETHEUS_URL = "prometheus_url"
CONF_SCAN_INTERVAL = "scan_interval"
CONF_QUERY_ID = "query_id"
CONF_QUERIES = "queries"
CONF_QUERY = "query"
CONF_UNIT = "unit"
CONF_DEVICE_CLASS = "device_class"
CONF_AUTH_TYPE = "auth_type"
CONF_TOKEN = "token"

AUTH_TYPE_NONE = "none"
AUTH_TYPE_BASIC = "basic"
AUTH_TYPE_BEARER = "bearer"
AUTH_TYPES = (AUTH_TYPE_NONE, AUTH_TYPE_BASIC, AUTH_TYPE_BEARER)

DEFAULT_SCAN_INTERVAL = 30
