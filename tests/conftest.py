"""
Pytest fixtures for TV Remote tests
"""
import os
import tempfile
import pytest
from werkzeug.security import generate_password_hash


@pytest.fixture
def app():
    """Create application for testing"""
    from app import create_app
    from app.models import db as _db

    # Create a temporary database file
    db_fd, db_path = tempfile.mkstemp()

    test_app = create_app()
    test_app.config.update({
        'TESTING': True,
        'WTF_CSRF_ENABLED': False,
        'SQLALCHEMY_DATABASE_URI': f'sqlite:///{db_path}',
        'SECRET_KEY': 'test-secret-key',
        'TV_IP': '192.168.1.1',
        'TV_MAC': '00:00:00:00:00:00',
    })

    with test_app.app_context():
        _db.create_all()

    yield test_app

    # Cleanup
    with test_app.app_context():
        _db.session.remove()
        _db.drop_all()
    os.close(db_fd)
    try:
        os.unlink(db_path)
    except:
        pass


@pytest.fixture
def db(app):
    """Provide database access within app context"""
    from app.models import db as _db
    with app.app_context():
        yield _db


@pytest.fixture
def client(app):
    """Test client"""
    return app.test_client()


@pytest.fixture
def test_user(app):
    """Create a test user"""
    from app.models import db, User

    with app.app_context():
        user = User(
            username='admin',
            password_hash=generate_password_hash('testpassword123')
        )
        db.session.add(user)
        db.session.commit()
        return user.id


@pytest.fixture
def auth_client(client, test_user):
    """Authenticated test client"""
    response = client.post('/auth/login', data={
        'password': 'testpassword123',
        'remember': 'on'
    }, follow_redirects=False)
    # Login should redirect (302) on success
    assert response.status_code == 302
    return client
