import os
from dotenv import load_dotenv

load_dotenv()

basedir = os.path.abspath(os.path.dirname(__file__))


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'docai-secret-key-change-in-production-2024')
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE', f'sqlite:///{os.path.join(basedir, "docai.db")}')
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    DEEPSEEK_API_KEY = os.environ.get('DEEPSEEK_API_KEY', '')
    DEEPSEEK_BASE_URL = os.environ.get('DEEPSEEK_BASE_URL', 'https://api.deepseek.com')
    DEEPSEEK_MODEL = os.environ.get('DEEPSEEK_MODEL', 'deepseek-chat')

    MAX_TEXT_LENGTH = 10000
    UPLOAD_FOLDER = os.path.join(basedir, 'uploads')
    MAX_CONTENT_LENGTH = 10 * 1024 * 1024  # 10MB

    ADMIN_USERNAME = os.environ.get('ADMIN_USERNAME', 'admin')
    ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'admin123')

    APP_VERSION = os.environ.get('APP_VERSION', '0.4.1')
    APP_RELEASE_SUMMARY = os.environ.get(
        'APP_RELEASE_SUMMARY',
        '本次更新修复了合同对比页报错，新增版本更新通知，并加入每日额度控制。',
    )
    REGISTRATION_BONUS_CREDITS = int(os.environ.get('REGISTRATION_BONUS_CREDITS', 2))
    LOGIN_BONUS_CREDITS = int(os.environ.get('LOGIN_BONUS_CREDITS', 0))
    REFERRAL_BONUS_CREDITS = int(os.environ.get('REFERRAL_BONUS_CREDITS', 3))
    REFERRAL_CODE_PREFIX = os.environ.get('REFERRAL_CODE_PREFIX', 'DCAI')
    ADMIN_CONTACT_EMAIL = os.environ.get('ADMIN_CONTACT_EMAIL', 'admin@docai.com')
