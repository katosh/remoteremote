"""
Tests for API endpoints
"""
import pytest


class TestHealthCheck:
    """Test health check endpoint"""

    def test_health_check(self, client, app, db):
        """Health check should return OK"""
        response = client.get('/api/health')
        assert response.status_code == 200
        data = response.get_json()
        assert data.get('status') == 'ok'


class TestProtectedEndpoints:
    """Test that endpoints require authentication"""

    def test_dashboard_requires_auth(self, client, app, db):
        """Dashboard should redirect to login"""
        response = client.get('/dashboard')
        assert response.status_code == 302
        assert 'login' in response.location

    def test_remote_requires_auth(self, client, app, db):
        """Remote control should redirect to login"""
        response = client.get('/remote/')
        assert response.status_code == 302
        assert 'login' in response.location

    def test_settings_requires_auth(self, client, app, db):
        """Settings should redirect to login"""
        response = client.get('/settings/')
        assert response.status_code == 302
        assert 'login' in response.location


class TestTVStatus:
    """Test TV status endpoints"""

    def test_tv_status_requires_auth(self, client, app, db):
        """TV status should require auth"""
        response = client.get('/api/tv/status')
        assert response.status_code == 302

    def test_tv_status_authenticated(self, auth_client, app):
        """TV status should work when authenticated"""
        response = auth_client.get('/api/tv/status')
        assert response.status_code == 200
        data = response.get_json()
        assert 'reachable' in data or 'power_state' in data

    def test_tv_status_json_requires_auth(self, client, app, db):
        """TV status JSON endpoint should require auth"""
        response = client.get('/api/tv/status/json')
        assert response.status_code == 302

    def test_tv_status_json_authenticated(self, auth_client, app):
        """TV status JSON endpoint should return JSON for Alpine.js"""
        response = auth_client.get('/api/tv/status/json')
        assert response.status_code == 200
        data = response.get_json()
        # New JSON endpoint returns simplified data for Alpine.js
        assert 'power_state' in data
        assert 'reachable' in data
        assert 'tv_name' in data

    def test_tv_status_json_returns_correct_format(self, auth_client, app):
        """TV status JSON should return correct data types"""
        from app.services.tv_service import _status_cache
        import time

        with app.app_context():
            # Set known state
            _status_cache['connected'] = True
            _status_cache['power_state'] = 'on'
            _status_cache['last_check'] = time.time()

            response = auth_client.get('/api/tv/status/json')
            data = response.get_json()

            assert isinstance(data['power_state'], str)
            assert isinstance(data['reachable'], bool)
            assert isinstance(data['tv_name'], str)


class TestScheduleAPI:
    """Test schedule endpoints"""

    def test_upcoming_schedules(self, auth_client, app):
        """Should return upcoming schedules"""
        response = auth_client.get('/api/schedules/upcoming')
        assert response.status_code == 200


class TestRemoteControl:
    """Test remote control endpoints"""

    def test_send_key_requires_auth(self, client, app, db):
        """Send key should require auth"""
        response = client.post('/remote/send-key', data={'key': 'KEY_MUTE'})
        assert response.status_code == 302

    def test_power_toggle_requires_auth(self, client, app, db):
        """Power toggle should require auth"""
        response = client.post('/remote/power')
        assert response.status_code == 302
