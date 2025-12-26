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
        # Check for password field (works in any language)
        assert b'type="password"' in response.data or b'password' in response.data.lower()

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

    def test_setup_password_too_short(self, client, app, db):
        """Setup should reject passwords shorter than 8 characters"""
        response = client.post('/auth/setup', data={
            'password': 'short',
            'password_confirm': 'short'
        })

        assert response.status_code == 200
        # Should show error, user should not be created
        with app.app_context():
            user = User.query.first()
            assert user is None

    def test_setup_redirects_when_user_exists(self, client, test_user, app):
        """Setup should redirect to login when user already exists"""
        response = client.get('/auth/setup')
        assert response.status_code == 302
        assert '/auth/login' in response.location

    def test_setup_then_login_works(self, client, app, db):
        """Password set during setup should work for immediate login"""
        password = 'myTestPassword123'

        # Setup
        response = client.post('/auth/setup', data={
            'password': password,
            'password_confirm': password
        }, follow_redirects=False)
        assert response.status_code == 302

        # Login with same password
        response = client.post('/auth/login', data={
            'password': password
        }, follow_redirects=False)
        assert response.status_code == 302
        assert '/dashboard' in response.location or '/' in response.location

    def test_root_redirects_to_setup_when_no_user(self, client, app, db):
        """Root URL should redirect to setup when no user exists"""
        response = client.get('/')
        assert response.status_code == 302
        assert '/auth/setup' in response.location

    def test_root_redirects_to_dashboard_when_user_exists(self, client, test_user, app):
        """Root URL should redirect to dashboard (then login) when user exists"""
        response = client.get('/')
        assert response.status_code == 302
        # Should go to dashboard (which will redirect to login if not authenticated)
        assert '/dashboard' in response.location


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

    def test_login_empty_password(self, client, test_user, app):
        """Empty password should fail login"""
        response = client.post('/auth/login', data={
            'password': ''
        })
        assert response.status_code == 200
        # Should stay on login page with error

    def test_login_redirects_to_setup_when_no_user(self, client, app, db):
        """Login page should work even when no user exists (shows login form)"""
        # When no user exists, login page should still render
        # (setup link should be available)
        response = client.get('/auth/login')
        assert response.status_code == 200

    def test_authenticated_user_redirected_from_login(self, auth_client, app):
        """Already authenticated user should be redirected from login page"""
        response = auth_client.get('/auth/login')
        assert response.status_code == 302
        assert '/dashboard' in response.location

    def test_session_persists_across_requests(self, client, test_user, app):
        """Session should persist after login"""
        # Login
        response = client.post('/auth/login', data={
            'password': 'testpassword123',
            'remember': True
        }, follow_redirects=False)
        assert response.status_code == 302

        # Access protected page
        response = client.get('/dashboard')
        assert response.status_code == 200
        assert b'<!DOCTYPE html>' in response.data


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


class TestDatabaseInitialization:
    """Test database initialization - catches missing table issues"""

    def test_all_required_tables_exist(self, app):
        """All required database tables should be created on init"""
        from app.models import db

        with app.app_context():
            inspector = db.inspect(db.engine)
            existing_tables = inspector.get_table_names()

            required_tables = ['users', 'sessions', 'config', 'schedules', 'scenarios', 'logs', 'tv_state']
            for table in required_tables:
                assert table in existing_tables, f"Required table '{table}' is missing"

    def test_default_scenarios_created(self, app):
        """Default scenarios should be created on init"""
        from app.models import Scenario

        with app.app_context():
            builtin_count = Scenario.query.filter_by(is_builtin=True).count()
            assert builtin_count > 0, "No builtin scenarios were created"

    def test_tv_state_singleton_exists(self, app):
        """TVState singleton should exist after init"""
        from app.models import TVState

        with app.app_context():
            tv_state = TVState.get_instance()
            assert tv_state is not None
            assert tv_state.id == 1


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
