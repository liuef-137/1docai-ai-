import os
import sys

import pytest
from flask import Flask

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import routes as api_routes
from auth import create_token
from models import db, User, UserQuota


@pytest.fixture
def quota_app():
    app = Flask(__name__)
    app.config.update(
        SECRET_KEY='quota-test-secret',
        SQLALCHEMY_DATABASE_URI='sqlite:///:memory:',
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        LOGIN_BONUS_CREDITS=2,
    )
    db.init_app(app)
    app.register_blueprint(api_routes.api_bp)
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()


def make_user():
    user = User(username='quota-test', email='quota-test@example.com', email_verified=True)
    user.set_password('secret')
    user.reward_analysis_credits = 2
    user.reward_compare_credits = 2
    user.reward_followup_credits = 2
    db.session.add(user)
    db.session.commit()
    return user


def test_referral_credits_persist_and_refund(quota_app):
    with quota_app.app_context():
        user = make_user()

        available, remaining, limit = UserQuota.check_available(user.id, 'analysis')
        assert available
        assert remaining == limit == 4
        assert UserQuota.get_usage(user, 'analysis') == 0

        UserQuota.check_and_increment(user.id, 'analysis')
        UserQuota.check_and_increment(user.id, 'analysis')
        UserQuota.check_and_increment(user.id, 'analysis')
        assert user.reward_analysis_credits == 1
        assert UserQuota.get_effective_limit(user, 'analysis') == 3

        assert UserQuota.refund(user.id, 'analysis')
        assert user.reward_analysis_credits == 2
        assert UserQuota.get_usage(user, 'analysis') == 2


@pytest.mark.parametrize('action, reward_field', [
    ('compare', 'reward_compare_credits'),
    ('followup', 'reward_followup_credits'),
])
def test_feature_reward_refunds(quota_app, action, reward_field):
    with quota_app.app_context():
        user = make_user()
        UserQuota.check_and_increment(user.id, action)
        UserQuota.check_and_increment(user.id, action)
        assert getattr(user, reward_field) == 1
        assert UserQuota.refund(user.id, action)
        assert getattr(user, reward_field) == 2


def test_analysis_failure_does_not_consume_quota(quota_app, monkeypatch):
    with quota_app.app_context():
        user = make_user()
        token = create_token(user.id)

        def fail_ai(*args, **kwargs):
            raise RuntimeError('provider unavailable')

        monkeypatch.setattr(api_routes, 'call_deepseek', fail_ai)
        response = quota_app.test_client().post(
            '/api/analysis',
            json={'text': '这是一份合同', 'mode': 'summary'},
            headers={'Authorization': f'Bearer {token}'},
        )

        assert response.status_code == 502
        assert UserQuota.get_usage(user, 'analysis') == 0
        assert user.reward_analysis_credits == 2


def test_contract_type_detection_does_not_call_ai(monkeypatch):
    def fail_ai(*args, **kwargs):
        raise AssertionError('contract type detection must not call the provider')

    monkeypatch.setattr(api_routes, 'call_deepseek', fail_ai)
    contract_type, confidence = api_routes._detect_contract_type(
        '本劳动合同约定试用期、工资和社会保险。', '', language='zh'
    )

    assert contract_type == 'labor'
    assert confidence > 0


def test_free_text_limit_is_1500(quota_app):
    with quota_app.app_context():
        quota_app.config['FREE_MAX_TEXT_LENGTH'] = 1500
        quota_app.config['GUEST_MAX_TEXT_LENGTH'] = 1500
        assert api_routes._text_limit_for_user(None) == 1500

        user = make_user()
        user.plan = 'free'
        assert api_routes._text_limit_for_user(user) == 1500
