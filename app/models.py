"""
Datenbankmodelle für die TV Remote Anwendung
"""
from datetime import datetime, timedelta
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
import json
import secrets
import hashlib

db = SQLAlchemy()


class Config(db.Model):
    """Konfigurationseinstellungen als Key-Value-Paare"""
    __tablename__ = 'config'

    key = db.Column(db.String(100), primary_key=True)
    value = db.Column(db.Text, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    @classmethod
    def get(cls, key: str, default=None):
        """Konfigurationswert abrufen"""
        config = cls.query.get(key)
        return config.value if config else default

    @classmethod
    def set(cls, key: str, value: str):
        """Konfigurationswert setzen"""
        config = cls.query.get(key)
        if config:
            config.value = value
        else:
            config = cls(key=key, value=value)
            db.session.add(config)
        db.session.commit()


class User(UserMixin, db.Model):
    """Benutzer (nur ein Admin-Benutzer)"""
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, default='admin')
    password_hash = db.Column(db.String(128), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime)

    # Relationship to sessions
    sessions = db.relationship('Session', backref='user', lazy='dynamic', cascade='all, delete-orphan')


class Session(db.Model):
    """Persistente Anmeldesitzungen für Remember-Me Funktionalität"""
    __tablename__ = 'sessions'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    token_hash = db.Column(db.String(64), unique=True, nullable=False, index=True)
    device_name = db.Column(db.String(200))  # Parsed from User-Agent
    user_agent = db.Column(db.Text)
    client_ip = db.Column(db.String(50))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_used = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime, nullable=False)
    is_current = db.Column(db.Boolean, default=False)  # Marked during request

    # Default session duration: 90 days
    DEFAULT_DURATION_DAYS = 90

    @classmethod
    def create_session(cls, user_id: int, user_agent: str, client_ip: str, duration_days: int = None):
        """Neue Session erstellen und Token zurückgeben"""
        if duration_days is None:
            duration_days = cls.DEFAULT_DURATION_DAYS

        # Generate secure token
        token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(token.encode()).hexdigest()

        # Parse device name from user agent
        device_name = cls._parse_device_name(user_agent)

        session = cls(
            user_id=user_id,
            token_hash=token_hash,
            device_name=device_name,
            user_agent=user_agent,
            client_ip=client_ip,
            expires_at=datetime.utcnow() + timedelta(days=duration_days)
        )
        db.session.add(session)
        db.session.commit()

        return token, session

    @classmethod
    def validate_token(cls, token: str):
        """Token validieren und Session zurückgeben"""
        if not token:
            return None

        token_hash = hashlib.sha256(token.encode()).hexdigest()
        session = cls.query.filter_by(token_hash=token_hash).first()

        if session and session.expires_at > datetime.utcnow():
            # Update last_used
            session.last_used = datetime.utcnow()
            db.session.commit()
            return session

        # Session expired or not found
        if session:
            db.session.delete(session)
            db.session.commit()

        return None

    @classmethod
    def cleanup_expired(cls):
        """Abgelaufene Sessions löschen"""
        expired = cls.query.filter(cls.expires_at < datetime.utcnow()).all()
        for session in expired:
            db.session.delete(session)
        db.session.commit()
        return len(expired)

    @staticmethod
    def _parse_device_name(user_agent: str) -> str:
        """Gerätenamen aus User-Agent extrahieren"""
        if not user_agent:
            return "Unbekanntes Gerät"

        ua = user_agent.lower()

        # iOS devices
        if 'iphone' in ua:
            return "iPhone"
        if 'ipad' in ua:
            return "iPad"

        # Android
        if 'android' in ua:
            if 'mobile' in ua:
                return "Android Smartphone"
            return "Android Tablet"

        # Desktop browsers
        if 'macintosh' in ua or 'mac os' in ua:
            if 'safari' in ua and 'chrome' not in ua:
                return "Mac (Safari)"
            if 'chrome' in ua:
                return "Mac (Chrome)"
            if 'firefox' in ua:
                return "Mac (Firefox)"
            return "Mac"

        if 'windows' in ua:
            if 'edge' in ua:
                return "Windows (Edge)"
            if 'chrome' in ua:
                return "Windows (Chrome)"
            if 'firefox' in ua:
                return "Windows (Firefox)"
            return "Windows"

        if 'linux' in ua:
            return "Linux"

        return "Browser"

    def revoke(self):
        """Diese Session widerrufen"""
        db.session.delete(self)
        db.session.commit()

    def to_dict(self):
        """Session als Dictionary für API"""
        return {
            'id': self.id,
            'device_name': self.device_name,
            'client_ip': self.client_ip,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'last_used': self.last_used.isoformat() if self.last_used else None,
            'expires_at': self.expires_at.isoformat() if self.expires_at else None,
            'is_current': self.is_current
        }


class Schedule(db.Model):
    """Geplante Aktionen"""
    __tablename__ = 'schedules'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    cron_expression = db.Column(db.String(100))  # NULL für einmalige Aktionen
    next_run = db.Column(db.DateTime)
    action_type = db.Column(db.String(50), nullable=False)  # 'key', 'sequence', 'scenario'
    action_data = db.Column(db.Text, nullable=False)  # JSON
    enabled = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_run = db.Column(db.DateTime)
    last_result = db.Column(db.Text)

    def get_action_data(self) -> dict:
        """Aktionsdaten als Dictionary"""
        return json.loads(self.action_data) if self.action_data else {}

    def set_action_data(self, data: dict):
        """Aktionsdaten setzen"""
        self.action_data = json.dumps(data)


class Scenario(db.Model):
    """Vordefinierte und benutzerdefinierte Szenarien"""
    __tablename__ = 'scenarios'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    steps = db.Column(db.Text, nullable=False)  # JSON Array
    is_builtin = db.Column(db.Boolean, default=False)
    randomize_delays = db.Column(db.Boolean, default=True)
    min_delay_ms = db.Column(db.Integer, default=500)
    max_delay_ms = db.Column(db.Integer, default=2000)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def get_steps(self) -> list:
        """Schritte als Liste"""
        return json.loads(self.steps) if self.steps else []

    def set_steps(self, steps: list):
        """Schritte setzen"""
        self.steps = json.dumps(steps)


class Log(db.Model):
    """Aktivitätsprotokolle"""
    __tablename__ = 'logs'

    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    level = db.Column(db.String(20), nullable=False, index=True)  # INFO, WARNING, ERROR
    category = db.Column(db.String(50), nullable=False, index=True)  # auth, action, schedule, config, system
    message = db.Column(db.Text, nullable=False)
    details = db.Column(db.Text)  # JSON
    client_ip = db.Column(db.String(50))
    user_agent = db.Column(db.Text)
    source = db.Column(db.String(50))  # 'manual', 'schedule', 'system'

    def get_details(self) -> dict:
        """Details als Dictionary"""
        return json.loads(self.details) if self.details else {}


class TVState(db.Model):
    """Geschätzter TV-Zustand"""
    __tablename__ = 'tv_state'

    id = db.Column(db.Integer, primary_key=True, default=1)
    power_state = db.Column(db.String(20), default='unknown')  # 'on', 'standby', 'unknown'
    estimated_volume = db.Column(db.Integer)
    estimated_channel = db.Column(db.Integer)
    estimated_muted = db.Column(db.Boolean, default=False)
    last_updated = db.Column(db.DateTime, default=datetime.utcnow)
    last_confirmed = db.Column(db.DateTime)  # Letzter API-Check

    @classmethod
    def get_instance(cls):
        """Singleton-Instanz abrufen oder erstellen"""
        state = cls.query.get(1)
        if not state:
            state = cls(id=1)
            db.session.add(state)
            db.session.commit()
        return state


def init_db(app):
    """Datenbank initialisieren und Standarddaten einfügen"""
    with app.app_context():
        db.create_all()

        # Repair corrupted tv_state if needed (e.g., wrong type in datetime fields)
        try:
            # Use raw SQL to check and fix corrupted datetime fields
            result = db.session.execute(
                db.text("SELECT id, last_confirmed FROM tv_state WHERE id = 1")
            ).fetchone()
            if result and result[1] is not None:
                # If last_confirmed is not a valid datetime string, reset it
                try:
                    if isinstance(result[1], str) and result[1] in ('on', 'off', 'standby', 'unknown'):
                        db.session.execute(
                            db.text("UPDATE tv_state SET last_confirmed = NULL, last_updated = NULL WHERE id = 1")
                        )
                        db.session.commit()
                except Exception:
                    pass
        except Exception:
            pass  # Table might not exist yet

        # Prüfen ob Szenarien existieren, sonst Standardszenarien einfügen
        if Scenario.query.filter_by(is_builtin=True).count() == 0:
            _create_default_scenarios()

        # TV-Zustand initialisieren
        TVState.get_instance()

        db.session.commit()


def _create_default_scenarios():
    """Vordefinierte Szenarien erstellen"""
    scenarios = [
        Scenario(
            name="Morgens einschalten",
            description="TV einschalten, auf Nachrichtenkanal wechseln, moderate Lautstärke",
            steps=json.dumps([
                {"action": "power_on", "delay": 5000},
                {"action": "key", "key": "KEY_EXIT", "delay": 1000},
                {"action": "key", "key": "KEY_EXIT", "delay": 1000},
                {"action": "channel", "channel": 1, "delay": 2000},
                {"action": "volume", "level": 15}
            ]),
            is_builtin=True,
            randomize_delays=True,
            min_delay_ms=800,
            max_delay_ms=2500
        ),
        Scenario(
            name="Abends ausschalten",
            description="Alle Menüs schließen und TV ausschalten",
            steps=json.dumps([
                {"action": "key", "key": "KEY_EXIT", "delay": 500},
                {"action": "key", "key": "KEY_EXIT", "delay": 500},
                {"action": "key", "key": "KEY_RETURN", "delay": 500},
                {"action": "power_off"}
            ]),
            is_builtin=True,
            randomize_delays=True,
            min_delay_ms=300,
            max_delay_ms=1000
        ),
        Scenario(
            name="Natürliches Zappen",
            description="Zwischen Kanälen wechseln wie ein echter Zuschauer",
            steps=json.dumps([
                {"action": "key", "key": "KEY_CHUP", "delay": 8000},
                {"action": "key", "key": "KEY_CHUP", "delay": 5000},
                {"action": "key", "key": "KEY_CHDOWN", "delay": 12000},
                {"action": "key", "key": "KEY_CHUP", "delay": 3000},
                {"action": "key", "key": "KEY_CHUP", "delay": 15000}
            ]),
            is_builtin=True,
            randomize_delays=True,
            min_delay_ms=2000,
            max_delay_ms=20000
        ),
        Scenario(
            name="Menüs schließen",
            description="Alle offenen Menüs und Overlays schließen",
            steps=json.dumps([
                {"action": "key", "key": "KEY_EXIT", "delay": 300},
                {"action": "key", "key": "KEY_EXIT", "delay": 300},
                {"action": "key", "key": "KEY_RETURN", "delay": 300},
                {"action": "key", "key": "KEY_RETURN", "delay": 300}
            ]),
            is_builtin=True,
            randomize_delays=False
        )
    ]

    for scenario in scenarios:
        db.session.add(scenario)
