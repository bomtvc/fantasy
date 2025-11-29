"""
FPL League Analyzer - Flask Application
Modern web application for analyzing Fantasy Premier League leagues
"""

from flask import Flask
from extensions import cache, cors
from routes import main_bp, api_bp
import config
import os


def create_app(config_object=None):
    """
    Application factory pattern
    
    Args:
        config_object: Configuration object or module
        
    Returns:
        Flask application instance
    """
    app = Flask(__name__)
    
    # Load configuration
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
    
    # Cache configuration - disk-based for persistence across restarts
    app.config['CACHE_TYPE'] = 'FileSystemCache'
    app.config['CACHE_DIR'] = config.CACHE_DIR
    app.config['CACHE_DEFAULT_TIMEOUT'] = config.CACHE_DEFAULT_TIMEOUT
    app.config['CACHE_THRESHOLD'] = config.CACHE_THRESHOLD
    
    # Create cache directory if it doesn't exist
    os.makedirs(config.CACHE_DIR, exist_ok=True)
    
    # Initialize extensions
    cache.init_app(app)
    cors.init_app(app, resources={r"/api/*": {"origins": "*"}})
    
    # Register blueprints
    app.register_blueprint(main_bp)
    app.register_blueprint(api_bp)
    
    # Register error handlers
    @app.errorhandler(404)
    def not_found(error):
        return {"error": "Not found"}, 404
    
    @app.errorhandler(500)
    def internal_error(error):
        return {"error": "Internal server error"}, 500
    
    # Add template globals
    @app.context_processor
    def inject_config():
        return {'config': config}
    
    return app


if __name__ == '__main__':
    app = create_app()
    app.run(debug=True, host='0.0.0.0', port=5000)
