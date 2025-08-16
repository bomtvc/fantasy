# Cấu hình cho FPL League Analyzer

# API Settings
FPL_BASE_URL = "https://fantasy.premierleague.com/api"
REQUEST_TIMEOUT = 10
MAX_RETRIES = 3
REQUEST_DELAY = 0.3  # Delay giữa các request (seconds)

# Threading Settings
MAX_WORKERS = 6  # Số thread tối đa cho concurrent requests

# Cache Settings
BOOTSTRAP_CACHE_TTL = 600  # 10 phút
API_CACHE_TTL = 300  # 5 phút

# Default Values
DEFAULT_LEAGUE_ID = 1042917
DEFAULT_PHASE = 1
DEFAULT_MONTH_MAPPING = "1-4,5-8,9-12,13-16,17-20,21-24,25-28,29-32,33-36,37-38"

# UI Settings
PAGE_TITLE = "RSC Fantasy League"
PAGE_ICON = "⚽"

# Export Settings
CSV_ENCODING = "utf-8"
CSV_INDEX = False
