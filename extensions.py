"""
Flask Extensions
Centralized initialization of Flask extensions
"""

from flask_caching import Cache
from flask_cors import CORS

# Initialize extensions (will be configured in app factory)
cache = Cache()
cors = CORS()
