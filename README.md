# remoteRemote

A web-based remote control for Samsung and Philips Smart TVs. Control your TV from any device on your local network through a responsive web interface.

## Features

### Remote Control
- Full virtual remote with all standard buttons (power, volume, channels, navigation, playback)
- Samsung remote layout with color buttons, number pad, and media controls
- Philips remote with Ambilight control support
- Wake-on-LAN (WoL) for powering on TVs remotely

### Scheduling & Automation
- CRON-based task scheduling for automated TV control
- Built-in scenarios (morning wake-up, evening shutdown, natural channel surfing)
- Custom action sequences with configurable delays
- One-time or recurring schedules

### User Management
- Single admin user with secure authentication
- Session management with device tracking
- Session revocation capability
- "Remember me" with persistent tokens

### Monitoring
- Activity logging with filtering and search
- TV status caching for performance
- Connection state tracking

### Internationalization
- English and German language support
- Timezone selection

## Supported TVs

| Brand | Models | Protocol | Notes |
|-------|--------|----------|-------|
| Samsung | 2016+ (Tizen OS) | WebSocket (wss) | Full support, token authentication |
| Philips | Android TV | REST API | Experimental, includes Ambilight |

## Tech Stack

- **Backend**: Flask, SQLAlchemy (SQLite), APScheduler
- **Frontend**: TailwindCSS, HTMX
- **Server**: Gunicorn (production), Caddy (reverse proxy)
- **Security**: Flask-Login, bcrypt, CSRF protection, rate limiting

## Installation

### Prerequisites
- Python 3.7+
- Network access to your Smart TV (same LAN)
- TV with network standby enabled (for WoL)

### Setup

```bash
# Clone the repository
git clone https://github.com/yourusername/remoteremote.git
cd remoteremote

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Linux/macOS
# or: venv\Scripts\activate  # Windows

# Install dependencies
pip install -r requirements.txt

# Initialize the database (happens automatically on first run)
python run.py
```

On first launch, you'll be prompted to create an admin account and configure your TV connection.

## Configuration

Most settings are configured through the **web interface** after initial setup:
- TV connection (IP, MAC, type) - with auto-discovery
- Language preference
- Timezone for scheduled actions

### Environment Variables (Optional)

For headless or automated deployments, you can pre-configure settings via environment variables or a `.env` file:

```bash
# TV connection (optional - can be configured via UI)
TV_IP=192.168.1.100          # Your TV's IP address
TV_MAC=AA:BB:CC:DD:EE:FF     # TV MAC address (for Wake-on-LAN)

# Advanced (rarely needed)
SECRET_KEY=your-secret-key   # Auto-generated if not set
DATABASE_URL=sqlite:///instance/tvremote.db
```

### Application Constants

Security and performance settings are defined in `app/config.py`. These require code changes and application restart:

| Setting | Default | Description |
|---------|---------|-------------|
| `LOG_RETENTION_DAYS` | 365 | Activity log retention period |
| `REMEMBER_ME_DURATION_DAYS` | 90 | "Remember me" token validity |
| `PERMANENT_SESSION_LIFETIME` | 7 days | Session timeout |
| `RATELIMIT_AUTH` | 5/min | Login attempt rate limit |
| `RATELIMIT_REMOTE_KEY` | 120/min | Key press rate limit |
| `RATELIMIT_REMOTE_ACTION` | 60/min | Action (power, volume) rate limit |

## Startup Options

### Development Server

```bash
python run.py [OPTIONS]

Options:
  --host TEXT     Bind address (default: 127.0.0.1)
  --port INTEGER  Port number (default: 5000)
  --production    Disable debug mode
```

Examples:
```bash
# Local development
python run.py

# Accessible from LAN
python run.py --host 0.0.0.0

# Custom port
python run.py --host 0.0.0.0 --port 8080
```

### Production Server (Gunicorn)

```bash
# Direct binding
gunicorn -w 4 -b 0.0.0.0:5000 wsgi:app

# Unix socket (for reverse proxy)
gunicorn -w 4 --bind unix:/tmp/tvremote.sock wsgi:app
```

## Deployment

### Option 1: Development (Local Use)

Suitable for testing or home use behind a firewall:

```bash
python run.py --host 0.0.0.0
```

Access at `http://your-server-ip:5000`

### Option 2: Production with Caddy (Recommended)

For secure remote access with automatic HTTPS:

1. Install Caddy: https://caddyserver.com/docs/install

2. Configure Caddyfile (replace `tvremote.yourdomain.com` with your domain):
```
tvremote.yourdomain.com {
    reverse_proxy localhost:5000

    header {
        Strict-Transport-Security "max-age=31536000; includeSubDomains"
        X-Frame-Options "DENY"
        X-Content-Type-Options "nosniff"
        X-XSS-Protection "1; mode=block"
        Referrer-Policy "strict-origin-when-cross-origin"
    }

    log {
        output file /var/log/caddy/tvremote.log
    }
}
```

3. Start services:
```bash
# Start application
gunicorn -w 4 --bind unix:/tmp/tvremote.sock wsgi:app &

# Start Caddy
sudo caddy run --config /path/to/Caddyfile
```

### Systemd Service

For automatic startup on boot, create a systemd service.

Create `/etc/systemd/system/tvremote.service`:

```ini
[Unit]
Description=TV Remote Control
After=network.target

[Service]
User=<YOUR_USERNAME>
WorkingDirectory=<PATH_TO_TVREMOTE>
Environment="PATH=<PATH_TO_TVREMOTE>/venv/bin"
ExecStart=<PATH_TO_TVREMOTE>/venv/bin/gunicorn -w 2 --bind unix:/tmp/tvremote.sock wsgi:app
Restart=always

[Install]
WantedBy=multi-user.target
```

**Replace these placeholders:**
- `<YOUR_USERNAME>` - The Linux user running the service (e.g., `pi`, `ubuntu`)
- `<PATH_TO_TVREMOTE>` - Absolute path to the project directory (e.g., `/home/pi/tvremote`)

Example with values filled in:
```ini
User=pi
WorkingDirectory=/home/pi/tvremote
Environment="PATH=/home/pi/tvremote/venv/bin"
ExecStart=/home/pi/tvremote/venv/bin/gunicorn -w 2 --bind unix:/tmp/tvremote.sock wsgi:app
```

Enable and start:
```bash
sudo systemctl enable tvremote
sudo systemctl start tvremote
```

## Security Considerations

### Authentication & Session Management

- Passwords are hashed using bcrypt (PBKDF2-SHA256)
- Minimum password length: 8 characters
- Sessions expire after 7 days of inactivity
- Persistent "Remember me" tokens valid for 90 days
- Session tracking includes IP and User-Agent for audit

### Network Security

| Concern | Mitigation |
|---------|------------|
| TV communication | Token-based authentication over WebSocket |
| Web traffic | HTTPS via Caddy with automatic certificates |
| CSRF attacks | Token validation on all state-changing requests |
| Brute force | Rate limiting on all endpoints |
| Session hijacking | Secure, HTTPOnly, SameSite cookies |

### Recommended Security Practices

1. **Use HTTPS in production** - Deploy behind Caddy or nginx with TLS
2. **Restrict network access** - Limit to trusted networks/VPN if exposed externally
3. **Use strong passwords** - Admin password should be unique and complex
4. **Monitor logs** - Review activity logs periodically for unauthorized access
5. **Keep updated** - Regularly update dependencies for security patches
6. **Firewall** - Only expose necessary ports (443 for HTTPS)

### Data Storage

- Database stored in `instance/` directory (excluded from git)
- TV authentication tokens stored in database
- No credentials logged; IPs and user agents recorded for audit
- Local backup/restore functionality available via settings

### Security Headers (Production)

When deployed with Caddy, the following headers are applied:
- `Strict-Transport-Security` - Enforces HTTPS
- `X-Frame-Options: DENY` - Prevents clickjacking
- `X-Content-Type-Options: nosniff` - Prevents MIME sniffing
- `X-XSS-Protection` - XSS filter (legacy browsers)
- `Referrer-Policy` - Controls referrer information

## TV Pairing

Both TV types require initial pairing to establish a secure connection.

**Prerequisites:**
- TV must be powered on (not in deep standby)
- TV and server must be on the same network subnet

**Pairing Steps:**

1. Open the web interface and go to **Settings > TV Connection**
2. Select your TV type (Samsung or Philips)
3. Use **Search** to auto-discover your TV, or enter the IP/MAC manually
4. Click **Connect** to initiate pairing
5. **On your TV:** Accept the pairing request when prompted
   - Samsung: A popup appears on screen - confirm with your physical remote
   - Philips: Enter the PIN code shown on your TV screen (if required)
6. Once paired, the token is saved automatically for future connections

**Auto-Discovery:**

The search function uses SSDP (Simple Service Discovery Protocol) to find TVs on the local network.

Discovery requires:
- TV is fully booted (wait ~30 seconds after power on)
- Server and TV on the same network subnet
- Router allows UDP multicast traffic (port 1900)

If auto-discovery fails, enter the IP address manually (find it in your TV's network settings or router admin panel).

**Troubleshooting:**
- Ensure "Remote Control" or "Network Remote" is enabled in TV settings
- Samsung: Requires port 8002 accessible (WebSocket API)
- Philips: Requires port 1926 accessible (REST API), may need "API access" enabled

## API Endpoints

The application uses HTMX for dynamic updates. Key endpoints:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/tv/key/<key>` | POST | Send remote key |
| `/api/tv/power` | POST | Toggle power |
| `/api/tv/status` | GET | Get TV status |
| `/api/tv/volume/<direction>` | POST | Adjust volume |
| `/api/tv/channel/<direction>` | POST | Change channel |
| `/api/schedule` | GET/POST | Manage schedules |

## Troubleshooting

### TV Not Responding

1. Verify TV is on the same network
2. Check TV IP address is correct
3. Ensure TV has network standby enabled
4. Try re-pairing (clear token and reconnect)

### Connection Refused

- Samsung TVs require secure WebSocket (port 8002)
- Check firewall allows connections to TV ports
- Some TVs need "Remote control" enabled in settings

### Wake-on-LAN Not Working

- Enable "Network standby" in TV power settings
- Verify MAC address is correct
- WoL requires TV to be in standby, not fully off

## Project Structure

```
tvremote/
├── app/
│   ├── __init__.py      # Flask app factory
│   ├── config.py        # Configuration classes
│   ├── models.py        # Database models
│   ├── views/           # Route handlers
│   ├── services/        # Business logic
│   ├── templates/       # Jinja2 templates
│   └── static/          # CSS, JS, icons
├── instance/            # Database, tokens (gitignored)
├── run.py               # Development entry point
├── wsgi.py              # Production entry point
├── requirements.txt     # Python dependencies
└── Caddyfile            # Web server config
```

## Contributing

Contributions are welcome! Please:
1. Fork the repository
2. Create a feature branch
3. Submit a pull request

## Disclaimer

**USE AT YOUR OWN RISK.** This software is provided "as is" without warranty of any kind.

- **No Affiliation**: This project is not affiliated with, endorsed by, or connected to Samsung, Philips, or any TV manufacturer. All product names, logos, and brands are property of their respective owners.

- **Hardware Risk**: This software sends commands to your TV. While designed to be safe, the authors are not responsible for any damage to your TV, unexpected behavior, or voided warranties that may result from using this software.

- **Network Security**: This application is designed for use on trusted home networks. Exposing it to the internet without proper security measures (HTTPS, strong passwords, firewall rules) may create security risks.

- **Personal Use**: This software is intended for personal, non-commercial home automation use.

- **No Warranty**: THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED. See the LICENSE file for the complete legal terms.

By using this software, you acknowledge that you have read and understood these terms.

## License

MIT License - See LICENSE file for details.

## Acknowledgments

- [ha-samsungtv-smart](https://github.com/ollo69/ha-samsungtv-smart) - Samsung TV integration for Home Assistant, used as reference for the Samsung WebSocket API
- [philipstv](https://pypi.org/project/philipstv/) library for Philips TV support
- Flask and its excellent ecosystem
