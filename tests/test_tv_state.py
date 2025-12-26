"""
Tests for TV state machine and transition handling
"""
import time
import pytest


class TestTVStateCaching:
    """Test TV status caching behavior"""

    def test_set_cached_power_state_turning_on(self, app):
        """Test that power on sets turning_on transition state"""
        from app.services.tv_service import set_cached_power_state, _status_cache

        with app.app_context():
            set_cached_power_state('on')

            assert _status_cache['power_state'] == 'turning_on'
            assert _status_cache['transition_type'] == 'turning_on'
            assert _status_cache['transition_until'] > time.time()

    def test_set_cached_power_state_turning_off(self, app):
        """Test that power off sets turning_off transition state"""
        from app.services.tv_service import set_cached_power_state, _status_cache

        with app.app_context():
            set_cached_power_state('off')

            assert _status_cache['power_state'] == 'turning_off'
            assert _status_cache['transition_type'] == 'turning_off'
            assert _status_cache['transition_until'] > time.time()

    def test_set_cached_power_state_standby_treated_as_off(self, app):
        """Test that standby is treated same as off"""
        from app.services.tv_service import set_cached_power_state, _status_cache

        with app.app_context():
            set_cached_power_state('standby')

            assert _status_cache['power_state'] == 'turning_off'
            assert _status_cache['transition_type'] == 'turning_off'

    def test_invalidate_cache(self, app):
        """Test cache invalidation resets last_check"""
        from app.services.tv_service import invalidate_status_cache, _status_cache

        with app.app_context():
            _status_cache['last_check'] = time.time()
            invalidate_status_cache()
            assert _status_cache['last_check'] == 0


class TestTVStateTransitions:
    """Test TV state transition behavior"""

    def test_transition_state_returned_during_transition(self, app):
        """Test that transition state is returned while in transition"""
        from app.services.tv_service import set_cached_power_state, get_cached_status

        with app.app_context():
            set_cached_power_state('on')
            status = get_cached_status()

            assert status['in_transition'] is True
            assert status['transition_type'] == 'turning_on'
            assert status['power_state'] == 'turning_on'

    def test_transition_has_remaining_time(self, app):
        """Test that transition includes remaining time"""
        from app.services.tv_service import set_cached_power_state, get_cached_status

        with app.app_context():
            set_cached_power_state('on')
            status = get_cached_status()

            assert 'transition_remaining' in status
            assert status['transition_remaining'] > 0

    def test_no_transition_when_not_transitioning(self, app):
        """Test that no transition state when not transitioning"""
        from app.services.tv_service import get_cached_status, _status_cache

        with app.app_context():
            # Reset cache to non-transition state
            _status_cache['transition_until'] = 0
            _status_cache['transition_type'] = None
            _status_cache['connected'] = False
            _status_cache['power_state'] = 'off'
            _status_cache['last_check'] = time.time()

            status = get_cached_status()

            assert status['in_transition'] is False
            assert status['transition_type'] is None


class TestTVStateDisplay:
    """Test TV state display in templates"""

    def test_dashboard_shows_tv_status(self, auth_client, app):
        """Test dashboard renders TV status with Alpine.js component"""
        with app.app_context():
            response = auth_client.get('/dashboard')
            assert response.status_code == 200
            html = response.data.decode('utf-8')
            # Should contain Alpine.js TV status component
            assert 'tvStateControl()' in html
            assert 'tv-status-card' in html

    def test_remote_shows_tv_status(self, auth_client, app):
        """Test remote page renders TV status with Alpine.js component"""
        with app.app_context():
            response = auth_client.get('/remote/')
            assert response.status_code == 200
            html = response.data.decode('utf-8')
            # Should contain Alpine.js TV status component
            assert 'tvStateControl()' in html
            assert 'tv-status-card' in html

    def test_api_returns_transition_state(self, auth_client, app):
        """Test API returns transition state info"""
        from app.services.tv_service import set_cached_power_state

        with app.app_context():
            set_cached_power_state('on')

            response = auth_client.get('/api/tv/status')
            assert response.status_code == 200

            data = response.get_json()
            assert 'in_transition' in data
            assert 'transition_type' in data

    def test_tv_status_json_returns_power_state(self, auth_client, app):
        """Test JSON status endpoint returns current power state"""
        from app.services.tv_service import _status_cache
        import time

        with app.app_context():
            # Set known state
            _status_cache['transition_until'] = 0
            _status_cache['transition_type'] = None
            _status_cache['connected'] = True
            _status_cache['power_state'] = 'on'
            _status_cache['last_check'] = time.time()

            response = auth_client.get('/api/tv/status/json')
            assert response.status_code == 200

            data = response.get_json()
            assert data['power_state'] == 'on'
            assert data['reachable'] is True

    def test_tv_status_json_when_off(self, auth_client, app):
        """Test JSON status shows off state when TV unreachable"""
        from app.services.tv_service import _status_cache
        import time

        with app.app_context():
            # Set to off state
            _status_cache['transition_until'] = 0
            _status_cache['transition_type'] = None
            _status_cache['connected'] = False
            _status_cache['power_state'] = 'off'
            _status_cache['last_check'] = time.time()

            response = auth_client.get('/api/tv/status/json')
            assert response.status_code == 200

            data = response.get_json()
            assert data['power_state'] == 'off'
            assert data['reachable'] is False


class TestPowerActions:
    """Test power action endpoints"""

    def test_power_on_returns_json(self, auth_client, app):
        """Test power on returns JSON response for Alpine.js"""
        with app.app_context():
            response = auth_client.post('/remote/power',
                                        data={'action': 'on'})
            assert response.status_code == 200

            # Should return JSON with success status
            data = response.get_json()
            assert data is not None
            assert 'success' in data
            assert data['success'] is True

    def test_power_off_returns_json(self, auth_client, app):
        """Test power off returns JSON response for Alpine.js"""
        with app.app_context():
            response = auth_client.post('/remote/power',
                                        data={'action': 'off'})
            assert response.status_code == 200

            # Should return JSON with success status
            data = response.get_json()
            assert data is not None
            assert 'success' in data
            assert data['success'] is True

    def test_power_toggle_returns_json(self, auth_client, app):
        """Test power toggle returns JSON response"""
        with app.app_context():
            response = auth_client.post('/remote/power',
                                        data={'action': 'toggle'})
            assert response.status_code == 200

            data = response.get_json()
            assert data is not None
            assert 'success' in data

    def test_power_on_logs_event(self, auth_client, app):
        """Test power on action is logged"""
        from app.models import Log

        with app.app_context():
            response = auth_client.post('/remote/power',
                                        data={'action': 'on'})
            assert response.status_code == 200

            # Check that the action was logged
            log = Log.query.filter(Log.category == 'action').order_by(Log.id.desc()).first()
            assert log is not None
            assert 'eingeschaltet' in log.message or 'Wake-on-LAN' in log.message
