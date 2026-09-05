import os
import sys

import pytest
from flask import Flask

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from models import db, User, UserQuota


@pytest.fixture
def quota_app():
    app = Flask(__name__)
    app.config.update(
        SQLALCHEMY_DATABASE_URI='sqlite:///:memory:',
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        LOGIN_BONUS_CREDITS=2,
    )
    db.init_app(app)
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
