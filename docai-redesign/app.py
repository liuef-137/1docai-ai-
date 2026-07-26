from flask import Flask, render_template, send_from_directory, jsonify
from config import Config
from models import db, User
from routes import api_bp
from auth import decode_token
from i18n_translations import I18N_DATA
import os, json


def create_app():
    return _create_app()


def _auto_migrate(db):
    """Add new columns to existing tables (SQLite safe)."""
    import sqlite3
    db_uri = db.engine.url.database if db.engine.url.drivername == 'sqlite' else None
    if not db_uri:
        return
    conn = sqlite3.connect(db_uri)
    cursor = conn.cursor()
    
    # Get existing columns for 'analysis' table
    existing = set()
    try:
        cursor.execute("PRAGMA table_info(analysis)")
        existing = {row[1] for row in cursor.fetchall()}
    except Exception:
        pass
    
    # Add missing columns
    migrations = [
        ("analysis", "text_hash", "VARCHAR(16)"),
        ("analysis", "contract_type", "VARCHAR(20)"),
    ]
    for table, col, col_type in migrations:
        if col not in existing:
            try:
                cursor.execute(f"ALTER TABLE {table} ADD COLUMN {col} {col_type}")
                print(f'[DocAI Migration] Added {table}.{col}')
            except Exception as e:
                print(f'[DocAI Migration] Error adding {table}.{col}: {e}')
    
    conn.commit()
    conn.close()


def _create_app():
    app = Flask(
        __name__,
        static_folder=os.path.abspath(os.path.join(os.path.dirname(__file__), '..')),
        static_url_path='',
        template_folder=os.path.abspath(os.path.join(os.path.dirname(__file__), 'templates')),
    )
    app.config.from_object(Config)

    db.init_app(app)
    app.register_blueprint(api_bp)

    # Create upload folder
    upload_folder = app.config.get('UPLOAD_FOLDER', 'uploads')
    os.makedirs(upload_folder, exist_ok=True)

    @app.context_processor
    def inject_app_state():
        """Inject auth state into all Jinja2 templates."""
        token = None
        user = None
        from flask import request
        # Try to get token from cookie
        auth_cookie = request.cookies.get('token')
        if auth_cookie:
            try:
                user = decode_token(auth_cookie)
                token = auth_cookie
            except Exception:
                pass
        # Also try Authorization header
        if not user:
            auth_header = request.headers.get('Authorization', '')
            if auth_header.startswith('Bearer '):
                try:
                    user = decode_token(auth_header[7:])
                    token = auth_header[7:]
                except Exception:
                    pass

        app_state = {
            'token': token,
            'isLoggedIn': user is not None,
            'user': {
                'id': user.id,
                'username': user.username,
                'email': user.email,
                'role': user.role,
            } if user else None,
        }
        return {'app_state': app_state, 'current_user': user, 'i18n_data': json.dumps(I18N_DATA)}

    # i18n.js endpoint
    @app.route('/i18n.js')
    def serve_i18n_js():
        return render_template('i18n.js', i18n_data=json.dumps(I18N_DATA))

    # Serve static files from project root (for CSS, images, etc.)
    @app.route('/assets/<path:filename>')
    def serve_assets(filename):
        return send_from_directory(
            os.path.join(os.path.dirname(__file__), '..', 'assets'),
            filename
        )

    @app.route('/colors_and_type.css')
    def serve_brand_css():
        return send_from_directory(
            os.path.join(os.path.dirname(__file__), '..'),
            'colors_and_type.css'
        )

    with app.app_context():
        db.create_all()
        # Auto-migrate: add new columns if they don't exist (SQLite compatible)
        _auto_migrate(db)
        # Create default admin if not exists
        admin = User.query.filter_by(username='admin').first()
        if not admin:
            admin = User(
                username=app.config.get('ADMIN_USERNAME', 'admin'),
                email='admin@docai.com',
                role='admin',
            )
            admin.set_password(app.config.get('ADMIN_PASSWORD', 'admin123'))
            db.session.add(admin)
            db.session.commit()
            print('[DocAI] Default admin created: admin / admin123')

    return app


if __name__ == '__main__':
    app = create_app()
    port = int(os.environ.get('PORT', 7777))
    app.run(host='0.0.0.0', port=port, debug=True)

# Gunicorn entry point: gunicorn will use "app:app"
app = create_app()
