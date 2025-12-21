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
        """Test dashboard renders TV status"""
        with app.app_context():
            response = auth_client.get('/dashboard')
            assert response.status_code == 200
            html = response.data.decode('utf-8')
            # Should contain TV status section
            assert 'Samsung TV' in html

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

    def test_api_mini_status_during_transition(self, auth_client, app):
        """Test mini status shows transition state"""
        from app.services.tv_service import set_cached_power_state

        with app.app_context():
            set_cached_power_state('on')

            response = auth_client.get('/api/tv/status?mini=1',
                                       headers={'HX-Request': 'true'})
            assert response.status_code == 200
            html = response.data.decode('utf-8')
            # Should show transition text
            assert 'Wird gestartet' in html or 'animate-pulse' in html

    def test_api_mini_status_when_off(self, auth_client, app):
        """Test mini status shows off state"""
        from app.services.tv_service import _status_cache
        import time

        with app.app_context():
            # Set to off state (no transition)
            _status_cache['transition_until'] = 0
            _status_cache['transition_type'] = None
            _status_cache['connected'] = False
            _status_cache['power_state'] = 'off'
            _status_cache['last_check'] = time.time()

            response = auth_client.get('/api/tv/status?mini=1',
                                       headers={'HX-Request': 'true'})
            assert response.status_code == 200
            html = response.data.decode('utf-8')
            assert 'Ausgeschaltet' in html


class TestPowerActions:
    """Test power action endpoints"""

    def test_power_on_sets_transition(self, auth_client, app):
        """Test power on sets transition state"""
        from app.services.tv_service import get_cached_status

        with app.app_context():
            response = auth_client.post('/remote/power',
                                        data={'action': 'on'})
            assert response.status_code == 200

            status = get_cached_status()
            # Should be in turning_on transition
            assert status['in_transition'] is True
            assert status['transition_type'] == 'turning_on'

    def test_power_off_sets_transition(self, auth_client, app):
        """Test power off sets transition state (or completes immediately if TV not responding)"""
        from app.services.tv_service import get_cached_status

        with app.app_context():
            response = auth_client.post('/remote/power',
                                        data={'action': 'off'})
            assert response.status_code == 200

            status = get_cached_status()
            # With mock TV (not connected), transition completes immediately
            # since get_info() returns None which is detected as "TV is now off"
            # This is correct behavior - we detect the target state was reached
            assert status['power_state'] == 'off'
            assert status['in_transition'] is False
