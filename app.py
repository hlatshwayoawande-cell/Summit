from flask import Flask, render_template_string, request, redirect, url_for, flash, jsonify, session, Response
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
import bcrypt
import re
import os
import requests
import json
import csv
import io
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-key')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///summit.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# ---------- BCON CONFIG ----------
BCON_API_KEY = os.environ.get('BCON_API_KEY', '')
BCON_API_URL = 'https://external-api.bcon.global/api/v2'
WALLET_ADDRESS = os.environ.get('WALLET_ADDRESS', '')

# ---------- DATABASE MODELS ----------
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_premium = db.Column(db.Boolean, default=False)
    premium_until = db.Column(db.DateTime, nullable=True)
    referral_code = db.Column(db.String(20), unique=True, nullable=True)
    referred_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)

class Project(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    name = db.Column(db.String(100), nullable=False)
    status = db.Column(db.String(20), default='active')
    last_updated = db.Column(db.DateTime, default=datetime.utcnow)
    notes = db.Column(db.Text, nullable=True)
    due_date = db.Column(db.Date, nullable=True)
    progress = db.Column(db.Integer, default=0)

class Income(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    source = db.Column(db.String(100), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    date = db.Column(db.Date, default=datetime.utcnow)
    notes = db.Column(db.Text, nullable=True)

class Crypto(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    coin_name = db.Column(db.String(50), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    value_zar = db.Column(db.Float, nullable=False)

class Payment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    invoice_id = db.Column(db.String(100))
    amount = db.Column(db.Float)
    currency = db.Column(db.String(10), default='USDC')
    status = db.Column(db.String(20), default='pending')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    confirmed_at = db.Column(db.DateTime, nullable=True)

# Create tables
with app.app_context():
    db.create_all()

# ---------- BASE HTML ----------
BASE_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Summit – {% block title %}Dashboard{% endblock %}</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: 'Inter', sans-serif; background: #0a0a0f; color: #e5e7eb; min-height: 100vh; background-image: radial-gradient(ellipse at 10% 20%, rgba(59,130,246,0.05) 0%, transparent 50%), radial-gradient(ellipse at 90% 80%, rgba(139,92,246,0.05) 0%, transparent 50%); }
        .container { max-width: 1200px; margin: 0 auto; padding: 20px; }
        .navbar { display: flex; justify-content: space-between; align-items: center; padding: 15px 0; border-bottom: 1px solid rgba(255,255,255,0.05); margin-bottom: 30px; flex-wrap: wrap; gap: 10px; }
        .logo { font-size: 28px; font-weight: 800; background: linear-gradient(135deg, #3b82f6, #8b5cf6, #ec4899); -webkit-background-clip: text; -webkit-text-fill-color: transparent; display: flex; align-items: center; gap: 10px; }
        .logo-icon { background: linear-gradient(135deg, #3b82f6, #8b5cf6); width: 36px; height: 36px; border-radius: 10px; display: flex; align-items: center; justify-content: center; color: white; font-size: 18px; -webkit-text-fill-color: white; font-weight: 700; }
        .nav-links { display: flex; gap: 5px; flex-wrap: wrap; }
        .nav-links a { color: #9ca3af; text-decoration: none; padding: 8px 16px; border-radius: 10px; transition: all 0.2s; font-size: 14px; font-weight: 500; }
        .nav-links a:hover { background: rgba(255,255,255,0.05); color: white; }
        .nav-links a.active { background: rgba(59,130,246,0.15); color: #60a5fa; }
        .btn { background: linear-gradient(135deg, #3b82f6, #8b5cf6); color: white; padding: 10px 24px; border: none; border-radius: 10px; cursor: pointer; font-size: 14px; font-weight: 600; transition: all 0.2s; text-decoration: none; display: inline-block; }
        .btn:hover { transform: translateY(-2px); box-shadow: 0 8px 30px rgba(59,130,246,0.3); }
        .btn-ghost { background: rgba(255,255,255,0.05); color: #d1d5db; border: 1px solid rgba(255,255,255,0.08); }
        .btn-ghost:hover { background: rgba(255,255,255,0.1); transform: translateY(-2px); }
        .btn-success { background: linear-gradient(135deg, #22c55e, #16a34a); }
        .btn-success:hover { box-shadow: 0 8px 30px rgba(34,197,94,0.3); }
        .btn-danger { background: linear-gradient(135deg, #ef4444, #dc2626); }
        .card { background: rgba(255,255,255,0.03); backdrop-filter: blur(20px); border: 1px solid rgba(255,255,255,0.06); border-radius: 20px; padding: 24px; margin-bottom: 20px; transition: all 0.2s; }
        .card:hover { border-color: rgba(255,255,255,0.1); }
        .card h3 { color: white; margin-bottom: 12px; font-size: 18px; font-weight: 600; }
        .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 16px; margin-bottom: 20px; }
        .stat { text-align: center; padding: 20px; background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.06); border-radius: 16px; transition: all 0.2s; }
        .stat:hover { border-color: rgba(255,255,255,0.1); transform: translateY(-2px); }
        .stat h2 { color: white; font-size: 32px; font-weight: 700; }
        .stat p { color: #6b7280; font-size: 13px; font-weight: 500; margin-top: 4px; }
        .stat .small { font-size: 18px; }
        input, select, textarea { width: 100%; padding: 12px 16px; background: rgba(255,255,255,0.05); border: 1px solid rgba(255,255,255,0.08); border-radius: 12px; color: white; font-size: 14px; transition: all 0.2s; margin-bottom: 12px; }
        input:focus, select:focus, textarea:focus { outline: none; border-color: #3b82f6; box-shadow: 0 0 0 3px rgba(59,130,246,0.15); background: rgba(255,255,255,0.08); }
        input::placeholder, textarea::placeholder { color: #4b5563; }
        table { width: 100%; border-collapse: collapse; }
        th { text-align: left; padding: 12px 10px; color: #6b7280; font-weight: 600; font-size: 12px; text-transform: uppercase; letter-spacing: 0.5px; }
        td { padding: 12px 10px; border-bottom: 1px solid rgba(255,255,255,0.04); color: #d1d5db; font-size: 14px; }
        .badge { padding: 4px 12px; border-radius: 20px; font-size: 12px; font-weight: 500; }
        .badge-active { background: rgba(34,197,94,0.15); color: #22c55e; }
        .badge-paused { background: rgba(234,179,8,0.15); color: #facc15; }
        .badge-completed { background: rgba(59,130,246,0.15); color: #60a5fa; }
        .badge-premium { background: linear-gradient(135deg, rgba(245,158,11,0.2), rgba(239,68,68,0.2)); color: #f59e0b; }
        .badge-free { background: rgba(255,255,255,0.05); color: #6b7280; }
        .flash { padding: 14px 20px; border-radius: 12px; margin-bottom: 16px; font-size: 14px; font-weight: 500; animation: slideDown 0.3s ease; }
        @keyframes slideDown { from { opacity: 0; transform: translateY(-10px); } to { opacity: 1; transform: translateY(0); } }
        .flash-success { background: rgba(34,197,94,0.1); border: 1px solid rgba(34,197,94,0.15); color: #22c55e; }
        .flash-danger { background: rgba(239,68,68,0.1); border: 1px solid rgba(239,68,68,0.15); color: #ef4444; }
        .flash-warning { background: rgba(234,179,8,0.1); border: 1px solid rgba(234,179,8,0.15); color: #facc15; }
        .flash-info { background: rgba(59,130,246,0.1); border: 1px solid rgba(59,130,246,0.15); color: #60a5fa; }
        .address-box { background: rgba(0,0,0,0.3); padding: 14px; border-radius: 12px; word-break: break-all; font-family: 'Courier New', monospace; font-size: 13px; margin: 10px 0; border: 1px solid rgba(255,255,255,0.05); }
        .flex { display: flex; justify-content: space-between; align-items: center; gap: 10px; flex-wrap: wrap; }
        .gap-2 { gap: 8px; }
        .mt-10 { margin-top: 10px; }
        .mt-20 { margin-top: 20px; }
        .text-center { text-align: center; }
        .text-muted { color: #6b7280; font-size: 14px; }
        .text-sm { font-size: 13px; }
        .text-xs { font-size: 12px; }
        .progress-bar { width: 100%; height: 6px; background: rgba(255,255,255,0.05); border-radius: 10px; overflow: hidden; margin: 6px 0; }
        .progress-bar .fill { height: 100%; border-radius: 10px; transition: width 0.3s; }
        .search-input { margin-bottom: 16px; }
        @media (max-width: 600px) { .navbar { flex-direction: column; align-items: stretch; } .nav-links { justify-content: center; } .grid { grid-template-columns: 1fr 1fr; } }
        @media (max-width: 400px) { .grid { grid-template-columns: 1fr; } }
        .chart-container { margin: 20px 0; display: flex; gap: 20px; flex-wrap: wrap; justify-content: center; }
        .chart-box { background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.06); border-radius: 16px; padding: 20px; flex: 1; min-width: 200px; text-align: center; }
        .chart-box .number { font-size: 36px; font-weight: 700; }
        .chart-box .label { color: #6b7280; font-size: 14px; margin-top: 4px; }
        .chart-box.active .number { color: #22c55e; }
        .chart-box.paused .number { color: #facc15; }
        .chart-box.completed .number { color: #60a5fa; }
    </style>
</head>
<body>
    <div class="container">
        <nav class="navbar">
            <div class="logo">
                <span class="logo-icon">S</span>
                Summit
            </div>
            <div class="nav-links">
                {% if session.user_id %}
                    <a href="{{ url_for('dashboard') }}" {% if request.endpoint == 'dashboard' %}class="active"{% endif %}>Dashboard</a>
                    <a href="{{ url_for('projects') }}" {% if request.endpoint == 'projects' %}class="active"{% endif %}>Projects</a>
                    <a href="{{ url_for('income') }}" {% if request.endpoint == 'income' %}class="active"{% endif %}>Income</a>
                    <a href="{{ url_for('crypto') }}" {% if request.endpoint == 'crypto' %}class="active"{% endif %}>Crypto</a>
                    <a href="{{ url_for('analytics') }}" {% if request.endpoint == 'analytics' %}class="active"{% endif %}>Analytics</a>
                    <a href="{{ url_for('upgrade') }}" {% if request.endpoint == 'upgrade' %}class="active"{% endif %}>Upgrade</a>
                    <a href="{{ url_for('logout') }}">Logout</a>
                {% else %}
                    <a href="{{ url_for('login') }}" {% if request.endpoint == 'login' %}class="active"{% endif %}>Login</a>
                    <a href="{{ url_for('signup') }}" {% if request.endpoint == 'signup' %}class="active"{% endif %}>Sign Up</a>
                {% endif %}
            </div>
        </nav>

        {% with messages = get_flashed_messages(with_categories=true) %}
            {% if messages %}
                {% for category, message in messages %}
                    <div class="flash flash-{{ category }}">{{ message }}</div>
                {% endfor %}
            {% endif %}
        {% endwith %}

        {{ content|safe }}
    </div>
</body>
</html>
"""

# ---------- ROUTES ----------
@app.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

# ---------- AUTH ROUTES ----------
@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        full_name = request.form.get('full_name')
        email = request.form.get('email')
        password = request.form.get('password')
        confirm = request.form.get('confirm_password')

        errors = []
        if len(full_name) < 2:
            errors.append('Full name must be at least 2 characters')
        if not re.match(r'^[\w\.-]+@[\w\.-]+\.\w+$', email):
            errors.append('Invalid email address')
        if len(password) < 6:
            errors.append('Password must be at least 6 characters')
        if password != confirm:
            errors.append('Passwords do not match')

        existing = User.query.filter_by(email=email).first()
        if existing:
            errors.append('Email already registered')

        if errors:
            for e in errors:
                flash(e, 'danger')
            login_url = url_for('login')
            page = f"""
            <div class="card" style="max-width: 420px; margin: auto;">
                <h2 style="font-size: 24px; font-weight: 700; margin-bottom: 4px;">Create Account</h2>
                <p class="text-muted text-sm" style="margin-bottom: 20px;">Start tracking your tech empire</p>
                <form method="POST">
                    <input type="text" name="full_name" placeholder="Full Name" value="{full_name}">
                    <input type="email" name="email" placeholder="Email" value="{email}">
                    <input type="password" name="password" placeholder="Password">
                    <input type="password" name="confirm_password" placeholder="Confirm Password">
                    <button type="submit" class="btn" style="width: 100%;">Create Account</button>
                </form>
                <p class="text-muted text-center mt-10" style="font-size: 14px;">Already have an account? <a href="{login_url}" style="color: #60a5fa; text-decoration: none;">Sign in</a></p>
            </div>
            """
            return render_template_string(BASE_HTML, content=page)

        hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
        new_user = User(full_name=full_name, email=email, password=hashed)
        db.session.add(new_user)
        db.session.commit()

        flash('Account created! Please login.', 'success')
        return redirect(url_for('login'))

    login_url = url_for('login')
    page = f"""
    <div class="card" style="max-width: 420px; margin: auto;">
        <h2 style="font-size: 24px; font-weight: 700; margin-bottom: 4px;">Create Account</h2>
        <p class="text-muted text-sm" style="margin-bottom: 20px;">Start tracking your tech empire</p>
        <form method="POST">
            <input type="text" name="full_name" placeholder="Full Name" required>
            <input type="email" name="email" placeholder="Email" required>
            <input type="password" name="password" placeholder="Password" required>
            <input type="password" name="confirm_password" placeholder="Confirm Password" required>
            <button type="submit" class="btn" style="width: 100%;">Create Account</button>
        </form>
        <p class="text-muted text-center mt-10" style="font-size: 14px;">Already have an account? <a href="{login_url}" style="color: #60a5fa; text-decoration: none;">Sign in</a></p>
    </div>
    """
    return render_template_string(BASE_HTML, content=page)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')

        user = User.query.filter_by(email=email).first()
        if user and bcrypt.checkpw(password.encode(), user.password.encode()):
            session['user_id'] = user.id
            session['user_name'] = user.full_name
            flash('Welcome back!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid email or password', 'danger')

    signup_url = url_for('signup')
    page = f"""
    <div class="card" style="max-width: 420px; margin: auto;">
        <h2 style="font-size: 24px; font-weight: 700; margin-bottom: 4px;">Welcome Back</h2>
        <p class="text-muted text-sm" style="margin-bottom: 20px;">Sign in to your Summit account</p>
        <form method="POST">
            <input type="email" name="email" placeholder="Email" required>
            <input type="password" name="password" placeholder="Password" required>
            <button type="submit" class="btn" style="width: 100%;">Sign In</button>
        </form>
        <p class="text-muted text-center mt-10" style="font-size: 14px;">Don't have an account? <a href="{signup_url}" style="color: #60a5fa; text-decoration: none;">Create one</a></p>
    </div>
    """
    return render_template_string(BASE_HTML, content=page)

@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out', 'info')
    return redirect(url_for('login'))

# ---------- PAYMENT FUNCTIONS ----------
def create_bcon_invoice(user_id, amount=1.60, currency='USD'):
    if not BCON_API_KEY:
        return {'error': 'BCON_API_KEY not configured'}

    headers = {
        'Authorization': f'Bearer {BCON_API_KEY}',
        'Content-Type': 'application/json',
        'Accept': 'application/json'
    }

    data = {
        'amount': amount,
        'currency': currency,
        'user_id': str(user_id),
        'callback_url': url_for('payment_webhook', _external=True)
    }

    try:
        response = requests.post(
            f'{BCON_API_URL}/invoice',
            headers=headers,
            json=data,
            timeout=10
        )
        if response.status_code == 200:
            return response.json()
        else:
            return {'error': f'Bcon error: {response.text}'}
    except Exception as e:
        return {'error': str(e)}

# ---------- PAYMENT ROUTES ----------
@app.route('/payment/beta')
def payment_beta():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user = User.query.get(session['user_id'])
    is_premium = user.is_premium and (user.premium_until is None or user.premium_until > datetime.utcnow())

    if is_premium:
        flash('You are already a Premium user!', 'success')
        return redirect(url_for('dashboard'))

    if not WALLET_ADDRESS:
        flash('Wallet address is not configured. Please add WALLET_ADDRESS to .env', 'danger')
        return redirect(url_for('upgrade'))

    invoice = None
    if BCON_API_KEY:
        invoice = create_bcon_invoice(user.id)
        if 'error' in invoice:
            flash(f'Payment system note: {invoice["error"]}. You can still pay manually.', 'warning')
            invoice = None

    page = f"""
    <div style="max-width: 600px; margin: 0 auto;">
        <div class="card" style="text-align: center; border-color: rgba(59,130,246,0.2);">
            <div style="font-size: 48px; margin-bottom: 12px;">Beta Payment</div>
            <h2 style="font-size: 24px; font-weight: 700;">Beta Payment</h2>
            <p class="text-muted text-sm">Send USDC to the address below to upgrade to Premium</p>
        </div>

        <div class="card" style="border-color: rgba(34,197,94,0.15);">
            <h3>Payment Instructions</h3>
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-top: 12px;">
                <div>
                    <p class="text-muted text-xs">Amount</p>
                    <p style="font-size: 20px; font-weight: 700; color: white;">$1.60 USDC</p>
                </div>
                <div>
                    <p class="text-muted text-xs">ZAR Equivalent</p>
                    <p style="font-size: 20px; font-weight: 700; color: white;">~R30</p>
                </div>
                <div>
                    <p class="text-muted text-xs">Network</p>
                    <p style="font-size: 14px; color: white;">Ethereum (ERC20)</p>
                </div>
                <div>
                    <p class="text-muted text-xs">Token</p>
                    <p style="font-size: 14px; color: white;">USDC</p>
                </div>
            </div>
        </div>

        <div class="card" style="border-color: rgba(245,158,11,0.15); background: rgba(245,158,11,0.03);">
            <h3>Send Payment</h3>
            <p class="text-muted text-sm">Send exactly <strong>$1.60 USDC</strong> to this address:</p>
            <div class="address-box" style="background: #0a0a0f; padding: 14px; border-radius: 12px; font-family: monospace; font-size: 13px; border: 1px solid rgba(255,255,255,0.05);">{WALLET_ADDRESS}</div>
            <div class="flex gap-2" style="margin-top: 10px;">
                <button class="btn btn-ghost" onclick="navigator.clipboard.writeText('{WALLET_ADDRESS}')" style="flex: 1;">Copy Address</button>
                <button class="btn btn-ghost" onclick="window.open('https://trustwallet.com')" style="flex: 1;">Open Trust Wallet</button>
            </div>
            <p class="text-muted text-xs mt-10" style="color: #4b5563;">
                After sending, your account will be upgraded automatically.
                If you don't see the upgrade within 10 minutes, contact support.
            </p>
        </div>

        <div class="card" style="text-align: center; border-color: rgba(255,255,255,0.05);">
            <p class="text-muted text-sm">Status: <span class="badge badge-paused">Waiting for payment</span></p>
            <a href="{url_for('dashboard')}" class="btn btn-ghost" style="margin-top: 12px;">Back to Dashboard</a>
        </div>
    </div>
    """
    return render_template_string(BASE_HTML, content=page)

@app.route('/payment/webhook', methods=['POST'])
def payment_webhook():
    """Bcon webhook endpoint - Auto-upgrades users when they pay"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'status': 'error', 'message': 'No data'}), 400

        invoice_id = data.get('invoice_id')
        status = data.get('status')
        user_id = data.get('user_id')

        if status == 'paid' and user_id:
            existing = Payment.query.filter_by(invoice_id=invoice_id).first()
            if existing and existing.status == 'completed':
                return jsonify({'status': 'already_processed'}), 200

            user = User.query.get(int(user_id))
            if user:
                user.is_premium = True
                user.premium_until = datetime.utcnow() + timedelta(days=30)
                db.session.commit()

                payment = Payment(
                    user_id=user.id,
                    invoice_id=invoice_id,
                    amount=data.get('amount', 1.60),
                    status='completed',
                    confirmed_at=datetime.utcnow()
                )
                db.session.add(payment)
                db.session.commit()

                return jsonify({'status': 'success', 'message': 'User upgraded'}), 200

        return jsonify({'status': 'ignored'}), 200
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

# ---------- DASHBOARD ----------
@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user = User.query.get(session['user_id'])
    projects = Project.query.filter_by(user_id=user.id).all()
    incomes = Income.query.filter_by(user_id=user.id).all()
    cryptos = Crypto.query.filter_by(user_id=user.id).all()

    total_projects = len(projects)
    total_income = sum(i.amount for i in incomes)
    total_crypto_value = sum(c.value_zar for c in cryptos)
    is_premium = user.is_premium and (user.premium_until is None or user.premium_until > datetime.utcnow())
    days_left = (user.premium_until - datetime.utcnow()).days if user.premium_until else 0

    recent_projects = ""
    if projects:
        for p in projects[:5]:
            color = "#22c55e" if p.progress >= 100 else "#facc15" if p.progress > 0 else "#6b7280"
            due_text = f"Due: {p.due_date}" if p.due_date else ""
            recent_projects += f"""
            <li style="padding: 10px 0; border-bottom: 1px solid rgba(255,255,255,0.04);">
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <span>{p.name} <span class="badge badge-{p.status}">{p.status}</span></span>
                    <span style="font-size: 12px; color: #6b7280;">{p.progress}%</span>
                </div>
                <div class="progress-bar"><div class="fill" style="width: {p.progress}%; background: {color};"></div></div>
                <div style="font-size: 11px; color: #4b5563;">{due_text}</div>
            </li>
            """
    else:
        recent_projects = '<p class="text-muted text-sm">No projects yet. <a href="/projects" style="color: #60a5fa; text-decoration: none;">Create your first project</a></p>'

    recent_incomes = ""
    if incomes:
        for i in incomes[:5]:
            recent_incomes += f'<li style="padding: 10px 0; border-bottom: 1px solid rgba(255,255,255,0.04); display: flex; justify-content: space-between;"><span>{i.source}</span><span style="color: #22c55e;">+R{i.amount:.2f}</span></li>'
    else:
        recent_incomes = '<p class="text-muted text-sm">No income yet. <a href="/income" style="color: #60a5fa; text-decoration: none;">Add your first income</a></p>'

    plan_badge = '<span class="badge badge-premium">Premium</span>' if is_premium else '<span class="badge badge-free">Free</span>'
    premium_note = f'<p class="text-muted text-xs">{days_left} days remaining</p>' if is_premium and days_left > 0 else ''

    page = f"""
    <div style="display: flex; justify-content: space-between; align-items: flex-start; flex-wrap: wrap; gap: 10px; margin-bottom: 8px;">
        <div>
            <h2 style="font-size: 28px; font-weight: 700;">Welcome back, {user.full_name}</h2>
            <p class="text-muted text-sm">Here is your tech empire at a glance</p>
        </div>
        <div style="display: flex; align-items: center; gap: 12px;">
            {plan_badge}
            {premium_note}
        </div>
    </div>

    <div class="grid">
        <div class="stat">
            <h2>{total_projects}</h2>
            <p>Projects</p>
        </div>
        <div class="stat">
            <h2>R{total_income:.2f}</h2>
            <p>Income</p>
        </div>
        <div class="stat">
            <h2>R{total_crypto_value:.2f}</h2>
            <p>Crypto Value</p>
        </div>
        <div class="stat" style="border-color: {'rgba(245,158,11,0.15)' if is_premium else 'rgba(255,255,255,0.06)'};">
            <h2 style="color: {'#f59e0b' if is_premium else '#6b7280'};">
                {'Premium' if is_premium else 'Free'}
            </h2>
            <p>Plan</p>
        </div>
    </div>

    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 20px;">
        <div class="card">
            <div class="flex">
                <h3>Recent Projects</h3>
                <a href="{url_for('projects')}" class="btn btn-ghost" style="padding: 6px 14px; font-size: 12px;">View All</a>
            </div>
            <ul style="list-style: none; padding: 0;">
                {recent_projects}
            </ul>
        </div>

        <div class="card">
            <div class="flex">
                <h3>Recent Income</h3>
                <a href="{url_for('income')}" class="btn btn-ghost" style="padding: 6px 14px; font-size: 12px;">View All</a>
            </div>
            <ul style="list-style: none; padding: 0;">
                {recent_incomes}
            </ul>
        </div>
    </div>

    {f'''
    <div class="card premium-card" style="text-align: center; margin-top: 20px;">
        <p style="font-size: 14px; color: #9ca3af;">You are on the <strong>Free Plan</strong></p>
        <a href="{url_for('upgrade')}" class="btn" style="margin-top: 8px;">Upgrade to Premium – R30/month</a>
    </div>
    ''' if not is_premium else ''}
    """
    return render_template_string(BASE_HTML, content=page)

# ---------- PROJECTS ----------
@app.route('/projects', methods=['GET', 'POST'])
def projects():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user = User.query.get(session['user_id'])
    all_projects = Project.query.filter_by(user_id=user.id).all()
    is_premium = user.is_premium and (user.premium_until is None or user.premium_until > datetime.utcnow())

    if request.method == 'POST':
        name = request.form.get('name')
        status = request.form.get('status', 'active')
        notes = request.form.get('notes', '')
        due_date = request.form.get('due_date')
        progress = request.form.get('progress', 0)

        if name:
            due_date_obj = None
            if due_date:
                try:
                    due_date_obj = datetime.strptime(due_date, '%Y-%m-%d').date()
                except:
                    pass

            new_project = Project(
                user_id=user.id,
                name=name,
                status=status,
                notes=notes,
                due_date=due_date_obj,
                progress=int(progress) if progress else 0
            )
            db.session.add(new_project)
            db.session.commit()
            flash('Project added!', 'success')
        else:
            flash('Project name is required', 'danger')
        return redirect(url_for('projects'))

    if not is_premium and len(all_projects) >= 2:
        flash('Free limit: 2 projects. Upgrade to Premium for unlimited!', 'warning')

    table_rows = ""
    for p in all_projects:
        due_text = p.due_date.strftime('%Y-%m-%d') if p.due_date else '-'
        color = "#22c55e" if p.progress >= 100 else "#facc15" if p.progress > 0 else "#6b7280"
        table_rows += f"""
        <tr>
            <td><strong>{p.name}</strong></td>
            <td><span class="badge badge-{p.status}">{p.status}</span></td>
            <td>
                <div style="display: flex; align-items: center; gap: 8px;">
                    <span style="font-size: 12px; color: #6b7280;">{p.progress}%</span>
                    <div class="progress-bar" style="flex: 1; max-width: 100px;"><div class="fill" style="width: {p.progress}%; background: {color};"></div></div>
                </div>
            </td>
            <td>{due_text}</td>
            <td>{p.notes or "-"}</td>
        </tr>
        """

    upgrade_url = url_for('upgrade')
    can_add = is_premium or len(all_projects) < 2

    page = f"""
    <div class="flex">
        <h2 style="font-size: 24px; font-weight: 700;">Projects</h2>
        <span class="text-muted text-sm">{len(all_projects)} / {'Unlimited' if is_premium else '2'}</span>
    </div>

    <div class="card">
        <h3>Add New Project</h3>
        {f'''
        <form method="POST">
            <input type="text" name="name" placeholder="Project Name" required>
            <select name="status">
                <option value="active">Active</option>
                <option value="paused">Paused</option>
                <option value="completed">Completed</option>
            </select>
            <input type="date" name="due_date" placeholder="Due Date">
            <input type="number" name="progress" placeholder="Progress (0-100%)" min="0" max="100">
            <textarea name="notes" placeholder="Notes (optional)" rows="3"></textarea>
            <button type="submit" class="btn">Add Project</button>
        </form>
        ''' if can_add else f'<p class="text-muted text-sm">You have reached the free limit. <a href="{upgrade_url}" style="color: #60a5fa; text-decoration: none;">Upgrade to Premium</a> for unlimited projects.</p>'}
    </div>

    <input type="text" id="searchInput" class="search-input" placeholder="Search projects..." onkeyup="filterProjects()">

    {f'''
    <div class="card">
        <table id="projectTable">
            <thead><tr><th>Name</th><th>Status</th><th>Progress</th><th>Due Date</th><th>Notes</th></tr></thead>
            <tbody>{table_rows}</tbody>
        </table>
    </div>
    ''' if all_projects else '<p class="text-muted text-sm">No projects yet. Add your first one above!</p>'}

    <script>
    function filterProjects() {{
        var input = document.getElementById('searchInput');
        var filter = input.value.toLowerCase();
        var rows = document.querySelectorAll('#projectTable tbody tr');
        rows.forEach(function(row) {{
            var text = row.textContent.toLowerCase();
            row.style.display = text.includes(filter) ? '' : 'none';
        }});
    }}
    </script>
    """
    return render_template_string(BASE_HTML, content=page)

# ---------- INCOME ----------
@app.route('/income', methods=['GET', 'POST'])
def income():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user = User.query.get(session['user_id'])

    if request.method == 'POST':
        source = request.form.get('source')
        amount = request.form.get('amount')
        notes = request.form.get('notes', '')

        if source and amount:
            try:
                amount = float(amount)
                new_income = Income(user_id=user.id, source=source, amount=amount, notes=notes)
                db.session.add(new_income)
                db.session.commit()
                flash('Income added!', 'success')
            except ValueError:
                flash('Invalid amount', 'danger')
        else:
            flash('Source and amount are required', 'danger')
        return redirect(url_for('income'))

    all_incomes = Income.query.filter_by(user_id=user.id).order_by(Income.date.desc()).all()
    total = sum(i.amount for i in all_incomes)

    table_rows = ""
    for i in all_incomes:
        table_rows += f'<tr><td>{i.source}</td><td style="color: #22c55e;">+R{i.amount:.2f}</td><td>{i.date.strftime("%Y-%m-%d")}</td><td>{i.notes or "-"}</td></tr>'

    page = f"""
    <div class="flex">
        <h2 style="font-size: 24px; font-weight: 700;">Income</h2>
        <span class="text-muted text-sm">Total: <strong style="color: #22c55e;">R{total:.2f}</strong></span>
    </div>

    <div class="card">
        <h3>Add Income</h3>
        <form method="POST">
            <input type="text" name="source" placeholder="Source (e.g. Freelance, Salary)" required>
            <input type="number" step="0.01" name="amount" placeholder="Amount (R)" required>
            <textarea name="notes" placeholder="Notes (optional)" rows="2"></textarea>
            <button type="submit" class="btn">Add Income</button>
        </form>
    </div>

    {f'''
    <div class="card">
        <table>
            <thead><tr><th>Source</th><th>Amount</th><th>Date</th><th>Notes</th></tr></thead>
            <tbody>{table_rows}</tbody>
        </table>
    </div>
    ''' if all_incomes else '<p class="text-muted text-sm">No income yet. Add your first income above!</p>'}
    """
    return render_template_string(BASE_HTML, content=page)

# ---------- CRYPTO ----------
@app.route('/crypto', methods=['GET', 'POST'])
def crypto():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user = User.query.get(session['user_id'])

    if request.method == 'POST':
        coin_name = request.form.get('coin_name')
        amount = request.form.get('amount')
        value_zar = request.form.get('value_zar')

        if coin_name and amount and value_zar:
            try:
                amount = float(amount)
                value_zar = float(value_zar)
                new_crypto = Crypto(user_id=user.id, coin_name=coin_name, amount=amount, value_zar=value_zar)
                db.session.add(new_crypto)
                db.session.commit()
                flash('Crypto added!', 'success')
            except ValueError:
                flash('Invalid amount or value', 'danger')
        else:
            flash('All fields are required', 'danger')
        return redirect(url_for('crypto'))

    all_cryptos = Crypto.query.filter_by(user_id=user.id).all()
    total = sum(c.value_zar for c in all_cryptos)

    table_rows = ""
    for c in all_cryptos:
        table_rows += f'<tr><td><strong>{c.coin_name}</strong></td><td>{c.amount}</td><td style="color: #60a5fa;">R{c.value_zar:.2f}</td></tr>'

    page = f"""
    <div class="flex">
        <h2 style="font-size: 24px; font-weight: 700;">Crypto Holdings</h2>
        <span class="text-muted text-sm">Total: <strong style="color: #60a5fa;">R{total:.2f}</strong></span>
    </div>

    <div class="card">
        <h3>Add Crypto</h3>
        <form method="POST">
            <input type="text" name="coin_name" placeholder="Coin (e.g. BTC, ETH, USDC)" required>
            <input type="number" step="0.000001" name="amount" placeholder="Amount" required>
            <input type="number" step="0.01" name="value_zar" placeholder="Value in ZAR" required>
            <button type="submit" class="btn">Add Crypto</button>
        </form>
    </div>

    {f'''
    <div class="card">
        <table>
            <thead><tr><th>Coin</th><th>Amount</th><th>Value (ZAR)</th></tr></thead>
            <tbody>{table_rows}</tbody>
        </table>
    </div>
    ''' if all_cryptos else '<p class="text-muted text-sm">No crypto yet. Add your first holding above!</p>'}
    """
    return render_template_string(BASE_HTML, content=page)

# ---------- ANALYTICS ----------
@app.route('/analytics')
def analytics():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user = User.query.get(session['user_id'])
    projects = Project.query.filter_by(user_id=user.id).all()
    incomes = Income.query.filter_by(user_id=user.id).all()
    cryptos = Crypto.query.filter_by(user_id=user.id).all()

    status_counts = {'active': 0, 'paused': 0, 'completed': 0}
    total_progress = 0
    for p in projects:
        status_counts[p.status] += 1
        total_progress += p.progress

    avg_progress = total_progress / len(projects) if projects else 0
    total_income = sum(i.amount for i in incomes)
    total_crypto = sum(c.value_zar for c in cryptos)

    page = f"""
    <h2 style="font-size: 24px; font-weight: 700; margin-bottom: 20px;">Analytics</h2>

    <div class="grid">
        <div class="stat">
            <h2>{len(projects)}</h2>
            <p>Total Projects</p>
        </div>
        <div class="stat">
            <h2>{avg_progress:.0f}%</h2>
            <p>Average Progress</p>
        </div>
        <div class="stat">
            <h2>R{total_income:.2f}</h2>
            <p>Total Income</p>
        </div>
        <div class="stat">
            <h2>R{total_crypto:.2f}</h2>
            <p>Crypto Value</p>
        </div>
    </div>

    <div class="card">
        <h3>Project Status Breakdown</h3>
        <div class="chart-container">
            <div class="chart-box active">
                <div class="number">{status_counts['active']}</div>
                <div class="label">Active</div>
            </div>
            <div class="chart-box paused">
                <div class="number">{status_counts['paused']}</div>
                <div class="label">Paused</div>
            </div>
            <div class="chart-box completed">
                <div class="number">{status_counts['completed']}</div>
                <div class="label">Completed</div>
            </div>
        </div>
    </div>

    <div class="card">
        <h3>Income and Crypto Summary</h3>
        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 20px;">
            <div>
                <p class="text-muted text-sm">Income Breakdown</p>
                <p style="font-size: 24px; font-weight: 700; color: #22c55e;">R{total_income:.2f}</p>
            </div>
            <div>
                <p class="text-muted text-sm">Crypto Holdings</p>
                <p style="font-size: 24px; font-weight: 700; color: #60a5fa;">R{total_crypto:.2f}</p>
            </div>
        </div>
    </div>

    <div class="card">
        <h3>Export Data</h3>
        <div style="display: flex; gap: 10px; flex-wrap: wrap;">
            <a href="{url_for('export_csv', data_type='projects')}" class="btn btn-ghost">Export Projects</a>
            <a href="{url_for('export_csv', data_type='income')}" class="btn btn-ghost">Export Income</a>
            <a href="{url_for('export_csv', data_type='crypto')}" class="btn btn-ghost">Export Crypto</a>
        </div>
    </div>
    """
    return render_template_string(BASE_HTML, content=page)

# ---------- EXPORT CSV ----------
@app.route('/export/<data_type>')
def export_csv(data_type):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user = User.query.get(session['user_id'])

    output = io.StringIO()
    writer = csv.writer(output)

    if data_type == 'projects':
        projects = Project.query.filter_by(user_id=user.id).all()
        writer.writerow(['Name', 'Status', 'Progress', 'Due Date', 'Notes', 'Last Updated'])
        for p in projects:
            writer.writerow([p.name, p.status, p.progress, p.due_date or '', p.notes or '', p.last_updated])
        filename = 'summit_projects.csv'

    elif data_type == 'income':
        incomes = Income.query.filter_by(user_id=user.id).all()
        writer.writerow(['Source', 'Amount (R)', 'Date', 'Notes'])
        for i in incomes:
            writer.writerow([i.source, i.amount, i.date, i.notes or ''])
        filename = 'summit_income.csv'

    elif data_type == 'crypto':
        cryptos = Crypto.query.filter_by(user_id=user.id).all()
        writer.writerow(['Coin', 'Amount', 'Value (R)'])
        for c in cryptos:
            writer.writerow([c.coin_name, c.amount, c.value_zar])
        filename = 'summit_crypto.csv'

    else:
        flash('Invalid export type', 'danger')
        return redirect(url_for('analytics'))

    output.seek(0)
    return Response(
        output,
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename={filename}'}
    )

# ---------- UPGRADE ----------
@app.route('/upgrade')
def upgrade():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user = User.query.get(session['user_id'])
    is_premium = user.is_premium and (user.premium_until is None or user.premium_until > datetime.utcnow())

    if is_premium:
        flash('You are already a Premium user!', 'success')
        return redirect(url_for('dashboard'))

    page = f"""
    <div style="max-width: 800px; margin: 0 auto;">
        <div style="text-align: center; margin-bottom: 30px;">
            <h2 style="font-size: 28px; font-weight: 700;">Upgrade to Premium</h2>
            <p class="text-muted text-sm">Unlock unlimited projects and more features</p>
        </div>

        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 20px;">
            <div class="card" style="border-color: rgba(255,255,255,0.05);">
                <h3 style="font-size: 20px;">Free</h3>
                <p class="text-muted text-sm">R0/month</p>
                <ul style="list-style: none; padding: 0; margin-top: 16px;">
                    <li style="padding: 6px 0;">2 projects</li>
                    <li style="padding: 6px 0;">Income tracking</li>
                    <li style="padding: 6px 0;">Crypto tracking</li>
                    <li style="padding: 6px 0;">Basic analytics</li>
                </ul>
                <div style="margin-top: 16px; padding: 8px 16px; background: rgba(34,197,94,0.05); border-radius: 8px; border: 1px solid rgba(34,197,94,0.1);">
                    <p style="color: #22c55e; font-size: 13px;">Current Plan</p>
                </div>
            </div>

            <div class="card premium-card" style="border-color: rgba(245,158,11,0.2);">
                <h3 style="font-size: 20px;">Premium</h3>
                <p class="text-muted text-sm">R30/month</p>
                <ul style="list-style: none; padding: 0; margin-top: 16px;">
                    <li style="padding: 6px 0;">Unlimited projects</li>
                    <li style="padding: 6px 0;">Deadlines and reminders</li>
                    <li style="padding: 6px 0;">Progress tracking</li>
                    <li style="padding: 6px 0;">Advanced analytics</li>
                    <li style="padding: 6px 0;">Export to CSV</li>
                    <li style="padding: 6px 0;">Priority support</li>
                </ul>
                <a href="{url_for('payment_beta')}" class="btn" style="width: 100%; margin-top: 16px;">Start Beta Payment</a>
                <p class="text-muted text-xs mt-10" style="color: #4b5563;">Beta test: $1.60 USDC (~R30)</p>
            </div>
        </div>

        <div class="card" style="text-align: center; border-color: rgba(255,255,255,0.03);">
            <p class="text-muted text-sm">Beta Testing – Help us test the payment system!</p>
            <p class="text-muted text-xs">Your account will be upgraded after successful payment</p>
        </div>
    </div>
    """
    return render_template_string(BASE_HTML, content=page)
# ---------- MANUAL PAYMENT VERIFICATION ----------
@app.route('/admin/upgrade/<int:user_id>')
def admin_upgrade(user_id):
    """Admin route to manually upgrade a user (password protected)"""
    # Simple password check – you can change this
    password = request.args.get('password', '')
    if password != 'summit2026':
        return "Unauthorized. Use ?password=summit2026", 401
    
    user = User.query.get(user_id)
    if not user:
        flash('User not found', 'danger')
        return redirect(url_for('dashboard'))
    
    if user.is_premium and user.premium_until and user.premium_until > datetime.utcnow():
        flash(f'{user.full_name} is already Premium until {user.premium_until.strftime("%Y-%m-%d")}', 'warning')
        return redirect(url_for('dashboard'))
    
    # Upgrade the user
    user.is_premium = True
    user.premium_until = datetime.utcnow() + timedelta(days=30)
    db.session.commit()
    
    # Log the payment
    payment = Payment(
        user_id=user.id,
        amount=1.60,
        currency='USDC',
        status='completed',
        confirmed_at=datetime.utcnow()
    )
    db.session.add(payment)
    db.session.commit()
    
    flash(f'✅ {user.full_name} has been upgraded to Premium!', 'success')
    return redirect(url_for('dashboard'))
# ---------- RUN ----------
if __name__ == '__main__':
    app.run(debug=True, port=5000)