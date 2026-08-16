import json

from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, date

db = SQLAlchemy()


class User(db.Model):
    __tablename__ = 'user'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(20), default='user')  # 'admin' or 'user'
    avatar = db.Column(db.String(256), default=None)  # 头像图片 URL，无则用首字母占位
    invite_code = db.Column(db.String(32), unique=True, index=True)
    referred_by_user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    analyses = db.relationship('Analysis', backref='user', lazy=True)
    referrer = db.relationship('User', remote_side=[id], backref='referrals', lazy=True)
    preferences = db.relationship(
        'RiskPreference', backref='user', lazy=True, uselist=False
    )

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def to_dict(self):
        return {
            'id': self.id,
            'username': self.username,
            'email': self.email,
            'role': self.role,
            'avatar': self.avatar,
            'invite_code': self.invite_code,
            'referred_by_user_id': self.referred_by_user_id,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class Analysis(db.Model):
    __tablename__ = 'analysis'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    filename = db.Column(db.String(256))
    contract_text = db.Column(db.Text, nullable=False)
    text_hash = db.Column(db.String(16))
    contract_type = db.Column(db.String(20))
    language = db.Column(db.String(10), default='zh')  # 'zh' or 'en'
    analysis_mode = db.Column(db.String(50), nullable=False)  # 'risk', 'summary', 'plain'
    result = db.Column(db.Text)  # JSON string of full analysis result
    score = db.Column(db.Integer)
    risk_level = db.Column(db.String(20))  # 'high', 'medium', 'low'
    one_line_summary = db.Column(db.Text)
    suggestions = db.Column(db.Text)  # JSON list
    risk_items = db.Column(db.Text)  # JSON list
    is_favorited = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'filename': self.filename,
            'contract_text': self.contract_text,
            'text_hash': self.text_hash,
            'contract_type': self.contract_type,
            'language': self.language or 'zh',
            'analysis_mode': self.analysis_mode,
            'result': self.result,
            'score': self.score,
            'risk_level': self.risk_level,
            'one_line_summary': self.one_line_summary,
            'suggestions': self.suggestions,
            'risk_items': self.risk_items,
            'is_favorited': self.is_favorited,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class RiskPreference(db.Model):
    __tablename__ = 'risk_preference'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), unique=True, nullable=False)
    preferences = db.Column(db.Text)  # JSON: list of preference strings
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def get_preferences_list(self):
        import json
        if not self.preferences:
            return []
        try:
            return json.loads(self.preferences)
        except (json.JSONDecodeError, TypeError):
            return []

    def set_preferences_list(self, prefs_list):
        import json
        self.preferences = json.dumps(prefs_list, ensure_ascii=False)

    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'preferences': self.get_preferences_list(),
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }


class UserQuota(db.Model):
    """Daily analysis quota tracking."""
    __tablename__ = 'user_quota'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    date = db.Column(db.Date, nullable=False, default=date.today)
    analysis_count = db.Column(db.Integer, default=0)
    compare_count = db.Column(db.Integer, default=0)
    followup_count = db.Column(db.Integer, default=0)
    bonus_credits = db.Column(db.Integer, default=0)  # extra quota granted today
    bonus_granted_date = db.Column(db.Date)

    __table_args__ = (db.UniqueConstraint('user_id', 'date', name='uq_user_date'),)

    @classmethod
    def get_base_limit(cls, user, action='analysis'):
        if action == 'followup':
            return 5
        if user and getattr(user, 'role', None) == 'admin':
            return 100
        if action == 'compare':
            return 2
        return 3

    @classmethod
    def get_effective_limit(cls, user, action='analysis'):
        if not user:
            return cls.get_base_limit(None, action)
        if not hasattr(user, 'id'):
            user = db.session.get(User, user)
        if not user:
            return cls.get_base_limit(None, action)
        base_limit = cls.get_base_limit(user, action)
        quota = cls.get_today_quota(user.id)
        bonus = (quota.bonus_credits or 0) if action in ('analysis', 'compare') else 0
        return base_limit + bonus

    @classmethod
    def get_today_quota(cls, user_id):
        """Get or create today's quota record for a user."""
        today = date.today()
        quota = cls.query.filter_by(user_id=user_id, date=today).first()
        if not quota:
            quota = cls(user_id=user_id, date=today)
            db.session.add(quota)
            db.session.commit()
        return quota

    @classmethod
    def check_and_increment(cls, user_id, action='analysis'):
        """Check quota limit and increment if allowed. Returns (allowed, remaining, daily_limit)."""
        user = db.session.get(User, user_id)
        quota = cls.get_today_quota(user_id)
        daily_limit = cls.get_effective_limit(user, action)

        if action == 'analysis':
            current = quota.analysis_count
        elif action == 'compare':
            current = quota.compare_count
        elif action == 'followup':
            current = quota.followup_count
        else:
            return False, 0, 0

        if current >= daily_limit:
            return False, 0, daily_limit

        # Increment
        if action == 'analysis':
            quota.analysis_count += 1
        elif action == 'compare':
            quota.compare_count += 1
        elif action == 'followup':
            quota.followup_count += 1

        db.session.commit()
        remaining = daily_limit - current - 1
        return True, remaining, daily_limit

    @classmethod
    def refund(cls, user_id, action='analysis'):
        """Return one quota unit after a failed operation."""
        quota = cls.get_today_quota(user_id)
        field = {'analysis': 'analysis_count', 'compare': 'compare_count', 'followup': 'followup_count'}.get(action)
        if not field:
            return False
        current = getattr(quota, field) or 0
        if current <= 0:
            return False
        setattr(quota, field, current - 1)
        db.session.commit()
        return True

    @classmethod
    def grant_login_bonus(cls, user_id, bonus_credits=5):
        """Grant a one-time daily login bonus quota."""
        if bonus_credits <= 0:
            return cls.get_today_quota(user_id)

        today = date.today()
        quota = cls.get_today_quota(user_id)
        if quota.bonus_granted_date == today:
            return quota

        quota.bonus_credits = bonus_credits
        quota.bonus_granted_date = today
        db.session.commit()
        return quota

    @classmethod
    def add_bonus_credits(cls, user_id, bonus_credits=0):
        """Add extra quota credits to today's record."""
        if bonus_credits <= 0:
            return cls.get_today_quota(user_id)
        quota = cls.get_today_quota(user_id)
        quota.bonus_credits = (quota.bonus_credits or 0) + bonus_credits
        quota.bonus_granted_date = date.today()
        db.session.commit()
        return quota

    def to_dict(self):
        return {
            'date': self.date.isoformat(),
            'analysis_count': self.analysis_count,
            'compare_count': self.compare_count,
            'followup_count': self.followup_count,
            'bonus_credits': self.bonus_credits,
            'bonus_granted_date': self.bonus_granted_date.isoformat() if self.bonus_granted_date else None,
        }


class ContractCompare(db.Model):
    __tablename__ = 'contract_compare'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    original_text = db.Column(db.Text)
    modified_text = db.Column(db.Text)
    diff_result = db.Column(db.Text)  # JSON
    ai_interpretation = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'original_text': self.original_text,
            'modified_text': self.modified_text,
            'diff_result': self.diff_result,
            'ai_interpretation': self.ai_interpretation,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class Feedback(db.Model):
    __tablename__ = 'feedback'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    username = db.Column(db.String(80))
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=False)
    feedback_type = db.Column(db.String(20), default='bug')  # bug/feature/improvement/praise
    category = db.Column(db.String(50))  # related module
    rating = db.Column(db.Integer)  # 1-5
    status = db.Column(db.String(20), default='pending')  # pending/reviewing/resolved/dismissed
    admin_reply = db.Column(db.Text)
    contact_email = db.Column(db.String(120))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = db.relationship('User', backref='feedbacks', lazy=True)

    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'username': self.username or (self.user.username if self.user else None),
            'title': self.title,
            'content': self.content,
            'feedback_type': self.feedback_type,
            'category': self.category,
            'rating': self.rating,
            'status': self.status,
            'admin_reply': self.admin_reply,
            'contact_email': self.contact_email,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }


class Conversation(db.Model):
    """AI followup conversation history."""
    __tablename__ = 'conversation'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    analysis_id = db.Column(db.Integer, db.ForeignKey('analysis.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Store as JSON array of messages: [{"role": "user"|"assistant", "content": "...", "timestamp": "..."}]
    messages = db.Column(db.Text, default='[]')

    analysis = db.relationship('Analysis', backref='conversation', uselist=False)

    def get_messages(self):
        if not self.messages:
            return []
        try:
            return json.loads(self.messages)
        except (json.JSONDecodeError, TypeError):
            return []

    def add_message(self, role, content):
        msgs = self.get_messages()
        msgs.append({
            'role': role,
            'content': content,
            'timestamp': datetime.utcnow().isoformat(),
        })
        self.messages = json.dumps(msgs, ensure_ascii=False)

    def to_dict(self):
        return {
            'id': self.id,
            'analysis_id': self.analysis_id,
            'messages': self.get_messages(),
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class Notification(db.Model):
    """通知模板表：每条通知的原始内容，向所有用户广播。"""
    __tablename__ = 'notification'

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    summary = db.Column(db.Text)
    notif_type = db.Column(db.String(20), default='system')  # system / business / alert / team
    icon = db.Column(db.String(50))  # lucide icon name
    link = db.Column(db.String(256))  # 点击跳转链接（可选）
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # 关联每个用户的已读状态
    user_states = db.relationship('UserNotification', backref='notification', lazy=True, cascade='all, delete-orphan')

    def to_dict(self, user_id=None):
        read = False
        if user_id:
            state = UserNotification.query.filter_by(
                notification_id=self.id, user_id=user_id
            ).first()
            read = state.is_read if state else False
        return {
            'id': self.id,
            'title': self.title,
            'summary': self.summary,
            'notif_type': self.notif_type,
            'icon': self.icon or self._default_icon(),
            'link': self.link,
            'read': read,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }

    def _default_icon(self):
        return {
            'alert': 'alert-triangle',
            'business': 'file-check',
            'team': 'users',
            'release': 'rocket',
            'system': 'megaphone',
        }.get(self.notif_type, 'bell')


class UserNotification(db.Model):
    """用户-通知关联表：记录每个用户对每条通知的已读状态。"""
    __tablename__ = 'user_notification'

    id = db.Column(db.Integer, primary_key=True)
    notification_id = db.Column(db.Integer, db.ForeignKey('notification.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    is_read = db.Column(db.Boolean, default=False)
    read_at = db.Column(db.DateTime)
    deleted = db.Column(db.Boolean, default=False)  # 用户软删除（隐藏）
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (db.UniqueConstraint('notification_id', 'user_id', name='uq_notif_user'),)

    user = db.relationship('User', backref='notification_states', lazy=True)
