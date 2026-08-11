from flask import Flask, render_template, send_from_directory, jsonify, request
from config import Config
from models import db, User
from routes import api_bp
from auth import decode_token
from i18n_translations import I18N_DATA
import os, json, shutil
from datetime import datetime


def create_app():
    return _create_app()


def _backup_sqlite_database(db, keep=20):
    """Create a timestamped SQLite backup before migrations touch user data."""
    db_uri = db.engine.url.database if db.engine.url.drivername == 'sqlite' else None
    if not db_uri:
        return

    db_path = os.path.abspath(db_uri)
    if not os.path.exists(db_path):
        return

    backup_dir = os.path.join(os.path.dirname(db_path), 'backups')
    os.makedirs(backup_dir, exist_ok=True)

    timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S_%f')
    backup_path = os.path.join(backup_dir, f'{os.path.basename(db_path)}.{timestamp}.bak')

    try:
        shutil.copy2(db_path, backup_path)
        print(f'[DocAI Backup] SQLite database backed up to {backup_path}')
    except Exception as e:
        print(f'[DocAI Backup] Failed to back up SQLite database: {e}')
        return

    try:
        backups = sorted(
            [
                os.path.join(backup_dir, name)
                for name in os.listdir(backup_dir)
                if name.startswith(os.path.basename(db_path) + '.') and name.endswith('.bak')
            ],
            key=os.path.getmtime,
            reverse=True,
        )
        for old_backup in backups[keep:]:
            os.remove(old_backup)
    except Exception as e:
        print(f'[DocAI Backup] Failed to prune old backups: {e}')


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

    # Get existing columns for 'user' table
    user_existing = set()
    try:
        cursor.execute("PRAGMA table_info(user)")
        user_existing = {row[1] for row in cursor.fetchall()}
    except Exception:
        pass

    # Add missing columns
    migrations = [
        ("analysis", "text_hash", "VARCHAR(16)"),
        ("analysis", "contract_type", "VARCHAR(20)"),
        ("analysis", "language", "VARCHAR(10)"),
        ("user", "avatar", "VARCHAR(256)"),
        ("user", "invite_code", "VARCHAR(32)"),
        ("user", "referred_by_user_id", "INTEGER"),
        ("user_quota", "bonus_credits", "INTEGER"),
        ("user_quota", "bonus_granted_date", "DATE"),
    ]
    for table, col, col_type in migrations:
        cols = existing if table == 'analysis' else user_existing
        if col not in cols:
            try:
                cursor.execute(f"ALTER TABLE {table} ADD COLUMN {col} {col_type}")
                print(f'[DocAI Migration] Added {table}.{col}')
            except Exception as e:
                print(f'[DocAI Migration] Error adding {table}.{col}: {e}')
    
    conn.commit()
    conn.close()


def _ensure_sqlite_parent(db):
    """Ensure the SQLite parent directory exists before SQLAlchemy opens it."""
    db_uri = db.engine.url.database if db.engine.url.drivername == 'sqlite' else None
    if not db_uri:
        return
    db_path = os.path.abspath(db_uri)
    db_dir = os.path.dirname(db_path)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)


def _create_app():
    base_dir = os.path.abspath(os.path.dirname(__file__))
    app = Flask(
        __name__,
        static_folder=base_dir,
        static_url_path='',
        template_folder=os.path.join(base_dir, 'templates'),
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
            'adminContactEmail': app.config.get('ADMIN_CONTACT_EMAIL', 'admin@docai.com'),
            'user': {
                'id': user.id,
                'username': user.username,
                'email': user.email,
                'role': user.role,
                'avatar': getattr(user, 'avatar', None),
            } if user else None,
        }
        return {'app_state': app_state, 'current_user': user, 'i18n_data': json.dumps(I18N_DATA)}

    @app.errorhandler(Exception)
    def handle_unexpected_error(error):
        app.logger.exception('Unhandled error: %s', error)
        if request.path.startswith('/api/'):
            return jsonify({'error': f'服务器内部错误: {str(error)}'}), 500
        raise error

    # i18n.js endpoint
    @app.route('/i18n.js')
    def serve_i18n_js():
        return render_template('i18n.js', i18n_data=json.dumps(I18N_DATA))

    # Serve static files from project root (for CSS, images, etc.)
    @app.route('/assets/<path:filename>')
    def serve_assets(filename):
        return send_from_directory(
            os.path.join(base_dir, 'assets'),
            filename
        )

    @app.route('/colors_and_type.css')
    def serve_brand_css():
        return send_from_directory(
            base_dir,
            'colors_and_type.css'
        )

    # -----------------------------------------------------------------------
    # Page routes (serve Jinja2 templates for the SPA-like frontend)
    # -----------------------------------------------------------------------
    @app.route('/')
    def index():
        return render_template('index.html', active_nav='home')

    @app.route('/dashboard')
    def dashboard():
        return render_template('dashboard.html', active_nav='dashboard')

    @app.route('/analyze')
    def analyze_page():
        return render_template('analyze.html', active_nav='analyze')

    @app.route('/archive')
    def archive_page():
        return render_template('archive.html', active_nav='archive')

    @app.route('/compare')
    def compare_page():
        return render_template('compare.html', active_nav='compare')

    @app.route('/pricing')
    def pricing_page():
        return render_template('pricing.html', active_nav='pricing')

    @app.route('/about')
    def about_page():
        return render_template('about.html', active_nav='about')

    @app.route('/login')
    def login_page():
        return render_template('login.html', active_nav=None)

    @app.route('/admin')
    def admin_page():
        return render_template('admin.html', active_nav='admin')

    @app.route('/detail/<int:analysis_id>')
    def detail_page(analysis_id):
        return render_template('detail.html', analysis_id=analysis_id, active_nav='archive')

    with app.app_context():
        _ensure_sqlite_parent(db)
        _backup_sqlite_database(db)
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

        # Seed default notifications if table is empty, plus the current release note.
        from models import Notification
        if Notification.query.count() == 0:
            release_version = app.config.get('APP_VERSION', '0.4.1')
            release_summary = app.config.get(
                'APP_RELEASE_SUMMARY',
                '本次更新修复了合同对比页报错，新增版本更新通知，并加入每日额度控制。',
            )
            default_notifs = [
                Notification(title=f'版本更新：{release_version}', summary=release_summary, notif_type='release', icon='rocket'),
                Notification(title='新功能上线：合同对比', summary='合同对比功能现已支持双文档智能比对，立即体验差异检测与风险评估。', notif_type='release', icon='git-compare'),
                Notification(title='系统维护通知', summary='系统将于本周日凌晨 2:00-4:00 进行例行维护升级，期间服务可能短暂中断。', notif_type='alert', icon='megaphone'),
            ]
            for n in default_notifs:
                db.session.add(n)
            db.session.commit()
            print('[DocAI] Default notifications seeded')
        else:
            release_version = app.config.get('APP_VERSION', '0.4.1')
            release_summary = app.config.get(
                'APP_RELEASE_SUMMARY',
                '本次更新修复了合同对比页报错，新增版本更新通知，并加入每日额度控制。',
            )
            release_title = f'版本更新：{release_version}'
            if not Notification.query.filter_by(title=release_title).first():
                db.session.add(Notification(
                    title=release_title,
                    summary=release_summary,
                    notif_type='release',
                    icon='rocket',
                ))
                db.session.commit()
                print(f'[DocAI] Release notification seeded for {release_version}')

    return app


app = create_app()


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 7777))
    app.run(host='0.0.0.0', port=port, debug=True)
