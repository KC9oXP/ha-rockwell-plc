"""Constants for the Rockwell PLC integration."""

DOMAIN = "rockwell_plc"

CONF_PATH = "path"
CONF_PLC_TYPE = "plc_type"
CONF_SCAN_INTERVAL = "scan_interval"
CONF_TAGS = "tags"
CONF_ALLOW_WRITES = "allow_writes"
CONF_ALLOW_SERVICE_WRITES = "allow_service_writes"

PLC_LOGIX = "logix"  # ControlLogix / CompactLogix / GuardLogix (Logix 5000, CIP tags)
PLC_SLC = "slc"  # SLC 5/05, MicroLogix 1100/1400 (PCCC data-table addresses)
PLC_TYPES = [PLC_LOGIX, PLC_SLC]

DEFAULT_SCAN_INTERVAL = 5  # seconds
MIN_SCAN_INTERVAL = 0.5

SERVICE_WRITE_TAG = "write_tag"
SERVICE_READ_TAG = "read_tag"
ATTR_CONFIG_ENTRY_ID = "config_entry_id"
ATTR_TAG = "tag"
ATTR_VALUE = "value"
