from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

db = SQLAlchemy()


class User(db.Model):
    __tablename__ = 'user'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(20), default='user')  # 'admin' or 'user'
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    analyses = db.relationship('Analysis', backref='user', lazy=True)
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
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class Analysis(db.Model):
    __tablename__ = 'analysis'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    filename = db.Column(db.String(256))
    contract_text = db.Column(db.Text, nullable=False)
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