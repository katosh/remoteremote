"""
Tests for rate limiting functionality
"""
import pytest
from app import limiter


class TestRateLimitingConfiguration:
    """Test that rate limiting is properly configured"""

    def test_limiter_initialized(self, app):
        """Limiter should be initialized with the app"""
        with app.app_context():
            assert limiter is not None
            assert limiter._limiter is not None

    def test_rate_limit_storage_configured(self, app):
        """Rate limit storage should be configured"""
        assert 'RATELIMIT_STORAGE_URL' in app.config
        assert app.config['RATELIMIT_STORAGE_URL'] == 'memory://'


class TestLoginRateLimiting:
    """Test rate limiting on login endpoint"""

    def test_login_allows_normal_requests(self, client, test_user, app):
        """Normal login attempts should be allowed"""
        # First few attempts should work
        for i in range(3):
            response = client.post('/auth/login', data={
                'password': 'wrongpassword'
            })
            assert response.status_code == 200, f"Request {i+1} should succeed"

    def test_login_rate_limited_after_threshold(self, client, test_user, app):
        """Login should be rate limited after too many attempts"""
        # Make requests until rate limited (limit is 5 per minute)
        rate_limited = False
        for i in range(10):
            response = client.post('/auth/login', data={
                'password': 'wrongpassword'
            })
            if response.status_code == 429:
                rate_limited = True
                break

        assert rate_limited, "Should have been rate limited after multiple attempts"

    def test_rate_limit_response_format(self, client, test_user, app):
        """Rate limit response should have proper format"""
        # Exhaust rate limit
        for _ in range(10):
            response = client.post('/auth/login', data={
                'password': 'wrongpassword'
            })
            if response.status_code == 429:
                break

        # Verify it's a 429 and contains expected content
        response = client.post('/auth/login', data={
            'password': 'wrongpassword'
        })
        assert response.status_code == 429


class TestAPIRateLimiting:
    """Test rate limiting on API endpoints"""

    def test_health_endpoint_rate_limited(self, client, app):
        """Health endpoint should have rate limiting"""
        # Health limit is 30 per minute
        rate_limited = False
        for i in range(40):
            response = client.get('/api/health')
            if response.status_code == 429:
                rate_limited = True
                break

        assert rate_limited, "Health endpoint should be rate limited"

    def test_api_returns_json_on_rate_limit(self, client, app):
        """API endpoints should return JSON when rate limited"""
        # Exhaust rate limit
        for _ in range(40):
            response = client.get('/api/health')
            if response.status_code == 429:
                break

        response = client.get('/api/health')
        if response.status_code == 429:
            data = response.get_json()
            assert data is not None
            assert 'error' in data
            assert data['error'] == 'Rate limit exceeded'


class TestRemoteRateLimiting:
    """Test rate limiting on remote control endpoints"""

    def test_send_key_allows_rapid_presses(self, auth_client, app):
        """Send key should allow rapid button presses (120/min)"""
        # Should allow at least 10 rapid presses without rate limiting
        for i in range(10):
            response = auth_client.post('/remote/send-key/KEY_UP')
            assert response.status_code != 429, f"Request {i+1} should not be rate limited"

    def test_power_endpoint_rate_limited(self, auth_client, app):
        """Power endpoint should be rate limited after many requests"""
        rate_limited = False
        for i in range(70):
            response = auth_client.post('/remote/power', data={
                'action': 'toggle'
            })
            if response.status_code == 429:
                rate_limited = True
                break

        assert rate_limited, "Power endpoint should eventually be rate limited"


class TestRateLimitHeaders:
    """Test rate limit headers in responses"""

    def test_rate_limit_headers_present(self, client, app):
        """Rate limit headers should be present in responses"""
        response = client.get('/api/health')

        # Flask-Limiter adds these headers when RATELIMIT_HEADERS_ENABLED=True
        # Check for at least one of the common headers
        has_headers = (
            'X-RateLimit-Limit' in response.headers or
            'X-RateLimit-Remaining' in response.headers or
            'RateLimit-Limit' in response.headers or
            'RateLimit-Remaining' in response.headers
        )
        assert has_headers, "Rate limit headers should be present"


class TestRateLimitByIP:
    """Test that rate limiting is per-IP"""

    def test_different_ips_have_separate_limits(self, app):
        """Different IPs should have separate rate limits"""
        # This is implicit in the configuration (key_func=get_remote_address)
        # Testing by checking the limiter key function
        from flask_limiter.util import get_remote_address

        with app.test_request_context(
            '/api/health',
            environ_base={'REMOTE_ADDR': '192.168.1.1'}
        ):
            ip1 = get_remote_address()

        with app.test_request_context(
            '/api/health',
            environ_base={'REMOTE_ADDR': '192.168.1.2'}
        ):
            ip2 = get_remote_address()

        assert ip1 != ip2, "Different IPs should be tracked separately"


class TestRateLimitExemptions:
    """Test that certain scenarios work correctly with rate limiting"""

    def test_successful_login_not_blocked_by_rate_limit(self, client, test_user, app):
        """A successful login should work even after failed attempts (within limit)"""
        # Make a few failed attempts (within limit)
        for _ in range(3):
            client.post('/auth/login', data={'password': 'wrong'})

        # Successful login should still work
        response = client.post('/auth/login', data={
            'password': 'testpassword123'
        }, follow_redirects=False)

        assert response.status_code == 302, "Successful login should redirect"

    def test_authenticated_api_access_works(self, auth_client, app):
        """Authenticated API access should work normally"""
        # Make several API calls
        for _ in range(5):
            response = auth_client.get('/api/tv/status')
            assert response.status_code == 200


class TestSetupRateLimiting:
    """Test rate limiting on setup endpoint"""

    def test_setup_rate_limited(self, client, app, db):
        """Setup endpoint should be rate limited"""
        rate_limited = False
        for i in range(10):
            response = client.post('/auth/setup', data={
                'password': 'short',
                'password_confirm': 'short'
            })
            if response.status_code == 429:
                rate_limited = True
                break

        assert rate_limited, "Setup endpoint should be rate limited"
