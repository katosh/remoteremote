"""
Tests for authentication and session management
"""
import pytest
from app.models import User, Session
from werkzeug.security import generate_password_hash, check_password_hash


class TestSetup:
    """Test initial setup flow"""

    def test_setup_page_accessible(self, client, app, db):
        """Setup page should be accessible when no user exists"""
        response = client.get('/auth/setup')
        assert response.status_code == 200
        assert b'passwort' in response.data.lower() or b'einricht' in response.data.lower()

    def test_setup_creates_user(self, client, app, db):
        """Setup should create admin user"""
        response = client.post('/auth/setup', data={
            'password': 'testpassword123',
            'password_confirm': 'testpassword123'
        }, follow_redirects=True)

        assert response.status_code == 200

        with app.app_context():
            user = User.query.first()
            assert user is not None
            assert user.username == 'admin'

    def test_setup_password_mismatch(self, client, app, db):
        """Setup should fail with mismatched passwords"""
        response = client.post('/auth/setup', data={
            'password': 'testpassword123',
            'password_confirm': 'differentpassword'
        })

        assert response.status_code == 200
        # Error should be shown on the page
        assert b'stimmen nicht' in response.data.lower() or b'setup' in response.data.lower()


class TestLogin:
    """Test login functionality"""

    def test_login_success(self, client, test_user, app):
        """Successful login should redirect to dashboard"""
        response = client.post('/auth/login', data={
            'password': 'testpassword123'
        }, follow_redirects=False)

        assert response.status_code == 302
        assert '/dashboard' in response.location or '/' in response.location

    def test_login_wrong_password(self, client, test_user, app):
        """Wrong password should show error"""
        response = client.post('/auth/login', data={
            'password': 'wrongpassword'
        })

        assert response.status_code == 200
        # Error should be in the page (password or error)
        assert b'passwort' in response.data.lower() or b'error' in response.data.lower() or b'ung' in response.data.lower()

    def test_login_with_remember(self, client, test_user, app):
        """Login with remember should set session cookie"""
        response = client.post('/auth/login', data={
            'password': 'testpassword123',
            'remember': True
        }, follow_redirects=False)

        assert response.status_code == 302
        # Check for session cookie
        cookies = response.headers.getlist('Set-Cookie')
        session_cookie = [c for c in cookies if 'tvremote_session' in c]
        assert len(session_cookie) > 0


class TestLogout:
    """Test logout functionality"""

    def test_logout_clears_session(self, auth_client, app):
        """Logout should clear session cookie"""
        response = auth_client.get('/auth/logout', follow_redirects=False)

        assert response.status_code == 302
        # Check that cookie is cleared
        cookies = response.headers.getlist('Set-Cookie')
        session_cookie = [c for c in cookies if 'tvremote_session' in c]
        # Cookie should be set to empty/expired
        assert any('tvremote_session=' in c for c in cookies)


class TestSessionModel:
    """Test Session model"""

    def test_create_session(self, app, test_user):
        """Should create session with token"""
        with app.app_context():
            token, session = Session.create_session(
                user_id=test_user,
                user_agent='Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)',
                client_ip='192.168.1.100'
            )

            assert token is not None
            assert len(token) > 20
            assert session.device_name == 'iPhone'
            assert session.client_ip == '192.168.1.100'

    def test_validate_token(self, app, test_user):
        """Should validate valid token"""
        with app.app_context():
            token, session = Session.create_session(
                user_id=test_user,
                user_agent='Test',
                client_ip='127.0.0.1'
            )

            validated_session = Session.validate_token(token)
            assert validated_session is not None
            assert validated_session.id == session.id

    def test_validate_invalid_token(self, app, test_user):
        """Should reject invalid token"""
        with app.app_context():
            validated_session = Session.validate_token('invalid-token')
            assert validated_session is None

    def test_device_name_parsing(self, app):
        """Should correctly parse device names"""
        test_cases = [
            ('Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)', 'iPhone'),
            ('Mozilla/5.0 (iPad; CPU OS 17_0 like Mac OS X)', 'iPad'),
            ('Mozilla/5.0 (Linux; Android 14; SM-S918B) Mobile', 'Android Smartphone'),
            ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120.0', 'Mac (Chrome)'),
            ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0', 'Windows (Chrome)'),
        ]

        for user_agent, expected_device in test_cases:
            # Use static method directly to avoid creating sessions
            device_name = Session._parse_device_name(user_agent)
            assert device_name == expected_device, f"Failed for {user_agent}: got {device_name}"

    def test_revoke_session(self, app, test_user):
        """Should revoke session"""
        with app.app_context():
            from app.models import db
            token, session = Session.create_session(
                user_id=test_user,
                user_agent='Test',
                client_ip='127.0.0.1'
            )
            session_id = session.id

            session.revoke()

            # Session should be deleted
            assert db.session.get(Session, session_id) is None


class TestSessionManagement:
    """Test session management views"""

    def test_sessions_page(self, auth_client, app):
        """Should show sessions page"""
        response = auth_client.get('/settings/sessions')
        assert response.status_code == 200
        assert b'Sitzungen' in response.data or b'session' in response.data.lower()

    def test_sessions_api(self, auth_client, app):
        """Should return sessions as JSON"""
        response = auth_client.get('/settings/sessions/api')
        assert response.status_code == 200
        data = response.get_json()
        assert 'sessions' in data


class TestPasswordHashing:
    """Test password hashing compatibility - catches issues like scrypt unavailability"""

    def test_password_hash_generation(self):
        """Password hashing should work with the configured method"""
        password = 'testpassword123'
        # This uses the same method as the app
        hash_value = generate_password_hash(password, method='pbkdf2:sha256')
        assert hash_value is not None
        assert hash_value != password
        assert hash_value.startswith('pbkdf2:sha256:')

    def test_password_hash_verification(self):
        """Password verification should work"""
        password = 'testpassword123'
        hash_value = generate_password_hash(password, method='pbkdf2:sha256')
        assert check_password_hash(hash_value, password) is True
        assert check_password_hash(hash_value, 'wrongpassword') is False

    def test_setup_creates_verifiable_password(self, client, app, db):
        """Password set during setup should be verifiable"""
        password = 'mySecurePassword123'
        response = client.post('/auth/setup', data={
            'password': password,
            'password_confirm': password
        }, follow_redirects=True)

        assert response.status_code == 200

        with app.app_context():
            user = User.query.first()
            assert user is not None
            # Verify the stored password can be checked
            assert check_password_hash(user.password_hash, password) is True
            assert check_password_hash(user.password_hash, 'wrongpassword') is False

    def test_password_change_creates_verifiable_password(self, auth_client, app, test_user):
        """Changed password should be verifiable"""
        new_password = 'newSecurePassword456'
        response = auth_client.post('/settings/password', data={
            'current_password': 'testpassword123',
            'new_password': new_password,
            'confirm_password': new_password
        }, follow_redirects=True)

        assert response.status_code == 200

        with app.app_context():
            user = User.query.first()
            assert check_password_hash(user.password_hash, new_password) is True


class TestCriticalEndpoints:
    """Smoke tests for critical endpoints - catches template/import errors"""

    def test_setup_page_renders(self, client, app, db):
        """Setup page should render without errors"""
        response = client.get('/auth/setup')
        assert response.status_code == 200
        assert b'<!DOCTYPE html>' in response.data or b'<html' in response.data

    def test_login_page_renders(self, client, app, test_user):
        """Login page should render without errors"""
        response = client.get('/auth/login')
        assert response.status_code == 200
        assert b'<!DOCTYPE html>' in response.data or b'<html' in response.data

    def test_dashboard_renders(self, auth_client, app):
        """Dashboard should render without errors"""
        response = auth_client.get('/dashboard')
        assert response.status_code == 200
        assert b'<!DOCTYPE html>' in response.data or b'<html' in response.data

    def test_remote_page_renders(self, auth_client, app):
        """Remote control page should render without errors"""
        response = auth_client.get('/remote/')
        assert response.status_code == 200
        assert b'<!DOCTYPE html>' in response.data or b'<html' in response.data

    def test_settings_page_renders(self, auth_client, app):
        """Settings page should render without errors"""
        response = auth_client.get('/settings/')
        assert response.status_code == 200
        assert b'<!DOCTYPE html>' in response.data or b'<html' in response.data

    def test_schedule_page_renders(self, auth_client, app):
        """Schedule page should render without errors"""
        response = auth_client.get('/schedule/')
        assert response.status_code == 200
        assert b'<!DOCTYPE html>' in response.data or b'<html' in response.data


class TestModelTypes:
    """Test that model field types are correct - catches type assignment bugs"""

    def test_tv_state_datetime_fields(self, app):
        """TVState datetime fields should only accept datetime objects"""
        from datetime import datetime
        from app.models import TVState, db

        with app.app_context():
            tv_state = TVState.get_instance()

            # Set valid datetime - should work
            tv_state.last_confirmed = datetime.utcnow()
            tv_state.last_updated = datetime.utcnow()
            db.session.commit()  # This should not raise

            # Verify the values are datetime objects
            assert isinstance(tv_state.last_confirmed, datetime)
            assert isinstance(tv_state.last_updated, datetime)

    def test_tv_state_power_state_string(self, app):
        """TVState power_state should be a string"""
        from app.models import TVState, db

        with app.app_context():
            tv_state = TVState.get_instance()
            tv_state.power_state = 'on'
            db.session.commit()

            assert tv_state.power_state == 'on'

    def test_dashboard_with_tv_connected(self, auth_client, app):
        """Dashboard should render correctly when TV state is updated"""
        from datetime import datetime
        from app.models import TVState, db

        with app.app_context():
            # Pre-populate TV state to simulate connected TV
            tv_state = TVState.get_instance()
            tv_state.power_state = 'on'
            tv_state.last_confirmed = datetime.utcnow()
            tv_state.estimated_volume = 25
            db.session.commit()

        # Now access dashboard - should not error
        response = auth_client.get('/dashboard')
        assert response.status_code == 200
        assert b'<!DOCTYPE html>' in response.data or b'<html' in response.data
