# Cấu hình cho FPL League Analyzer

# API Settings
FPL_BASE_URL = "https://fantasy.premierleague.com/api"
REQUEST_TIMEOUT = 10
MAX_RETRIES = 3
REQUEST_DELAY = 0.3  # Delay giữa các request (seconds)

# Threading Settings
MAX_WORKERS = 6  # Số thread tối đa cho concurrent requests

# Cache Settings
CACHE_DIR = "./cache"  # Directory for disk-based cache
CACHE_TYPE = "FileSystemCache"  # Use disk-based cache for persistence
CACHE_THRESHOLD = 1000  # Maximum number of cached items
CACHE_DEFAULT_TIMEOUT = 300  # Default timeout: 5 minutes

# TTL Settings - Different values for different data types
BOOTSTRAP_CACHE_TTL = 86400  # 24 hours (static player data)
LEAGUE_CACHE_TTL = 3600  # 1 hour (semi-static league standings)
GW_DATA_CACHE_TTL = 900  # 15 minutes (dynamic GW points)
API_CACHE_TTL = 300  # 5 minutes (general API responses)

# Default Values
DEFAULT_LEAGUE_ID = 1042917
DEFAULT_PHASE = 1
DEFAULT_MONTH_MAPPING = "1-4,5-9,10-13,14-17,18-21,22-26,27-30,31-34,35-38"

# UI Settings
PAGE_TITLE = "RSC Fantasy League"
PAGE_ICON = "⚽"

# Export Settings
CSV_ENCODING = "utf-8"
CSV_INDEX = False
