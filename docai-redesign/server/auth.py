from functools import wraps
from flask import request, jsonify, current_app
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from models import db, User

TOKEN_MAX_AGE = 60 * 60 * 24 * 7  # 7 days


def _get_serializer():
    return URLSafeTimedSerializer(current_app.config['SECRET_KEY'])


def create_token(user_id):
    """Generate a timed token for the given user_id."""
    s = _get_serializer()
    return s.dumps(str(user_id))


def _decode_token(token):
    """Decode token, return user_id or None."""
    try:
        s = _get_serializer()
        user_id = s.loads(token, max_age=TOKEN_MAX_AGE)
        return int(user_id)
    except (BadSignature, SignatureExpired, ValueError, TypeError):
        return None


def decode_token(token):
    """Public token decoder: returns User object or None."""
    user_id = _decode_token(token)
    if not user_id:
        return None
    return db.session.get(User, user_id)


def get_current_user():
    """Decorator: inject `current_user` into kwargs if authenticated, else 401."""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            token = None

            # Try cookie first
            token = request.cookies.get('token')

            # Fallback to Authorization header
            if not token:
                auth_header = request.headers.get('Authorization', '')
                if auth_header.startswith('Bearer '):
                    token = auth_header[7:]

            if not token:
                return jsonify({'error': '未登录，请先登录'}), 401

            user_id = _decode_token(token)
            if not user_id:
                return jsonify({'error': '登录已过期，请重新登录'}), 401

            user = db.session.get(User, user_id)
            if not user:
                return jsonify({'error': '用户不存在'}), 401

            kwargs['current_user'] = user
            return f(*args, **kwargs)
        return decorated_function
    return decorator


def admin_required(f):
    """Decorator: require current_user to have admin role. Must be used after get_current_user."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        current_user = kwargs.get('current_user')
        if not current_user or current_user.role != 'admin':
            return jsonify({'error': '权限不足，需要管理员权限'}), 403
        return f(*args, **kwargs)
    return decorated_function