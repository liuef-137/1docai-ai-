import os
from dotenv import load_dotenv

load_dotenv()

basedir = os.path.abspath(os.path.dirname(__file__))


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'docai-secret-key-change-in-production-2024')
    # Prefer an externally managed database in deployment; local SQLite remains the development fallback.
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE') or os.environ.get('DATABASE_URL') or f'sqlite:///{os.path.join(basedir, "docai.db")}'
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    DEEPSEEK_API_KEY = os.environ.get('DEEPSEEK_API_KEY', '')
    DEEPSEEK_BASE_URL = os.environ.get('DEEPSEEK_BASE_URL', 'https://api.deepseek.com')
    DEEPSEEK_MODEL = os.environ.get('DEEPSEEK_MODEL', 'deepseek-v4-flash')
    RELAY_API_BASE_URL = os.environ.get('RELAY_API_BASE_URL', '').rstrip('/')
    RELAY_API_KEY = os.environ.get('RELAY_API_KEY', '')
    RELAY_MODEL = os.environ.get('RELAY_MODEL', 'deepseek-v4-flash')
    RELAY_TIMEOUT_SECONDS = int(os.environ.get('RELAY_TIMEOUT_SECONDS', 20))
    RELAY_MAX_RETRIES = int(os.environ.get('RELAY_MAX_RETRIES', 2))

    MAX_TEXT_LENGTH = 20000
    FREE_MAX_TEXT_LENGTH = int(os.environ.get('FREE_MAX_TEXT_LENGTH', 1000))
    STANDARD_MAX_TEXT_LENGTH = int(os.environ.get('STANDARD_MAX_TEXT_LENGTH', 5000))
    GUEST_MAX_TEXT_LENGTH = int(os.environ.get('GUEST_MAX_TEXT_LENGTH', 1000))
    GUEST_RATE_LIMIT_PER_MINUTE = int(os.environ.get('GUEST_RATE_LIMIT_PER_MINUTE', 5))
    TRUSTED_PROXY_HOPS = int(os.environ.get('TRUSTED_PROXY_HOPS', 0))
    UPLOAD_FOLDER = os.path.join(basedir, 'uploads')
    MAX_CONTENT_LENGTH = 10 * 1024 * 1024  # 10MB

    ADMIN_USERNAME = os.environ.get('ADMIN_USERNAME', 'admin')
    ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'admin123')

    APP_VERSION = os.environ.get('APP_VERSION', '0.4.9')
    APP_RELEASE_SUMMARY = os.environ.get(
        'APP_RELEASE_SUMMARY',
        '本次更新优化拖拽识别，并调整免费额度与付费套餐限制。',
    )
    REGISTRATION_BONUS_CREDITS = int(os.environ.get('REGISTRATION_BONUS_CREDITS', 2))
    LOGIN_BONUS_CREDITS = int(os.environ.get('LOGIN_BONUS_CREDITS', 2))
    REFERRAL_BONUS_CREDITS = int(os.environ.get('REFERRAL_BONUS_CREDITS', 2))
    REFERRAL_CODE_PREFIX = os.environ.get('REFERRAL_CODE_PREFIX', 'DCAI')
    ADMIN_CONTACT_EMAIL = os.environ.get('ADMIN_CONTACT_EMAIL', 'admin@docai.com')
    PUBLIC_BASE_URL = os.environ.get('PUBLIC_BASE_URL', '')
    SMTP_HOST = os.environ.get('SMTP_HOST', '')
    SMTP_PORT = int(os.environ.get('SMTP_PORT', 587))
    SMTP_USERNAME = os.environ.get('SMTP_USERNAME', '')
    SMTP_PASSWORD = os.environ.get('SMTP_PASSWORD', '')
    SMTP_FROM = os.environ.get('SMTP_FROM', '')
