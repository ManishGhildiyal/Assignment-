import os
import random
import string
from datetime import datetime
from flask import Flask, render_template, jsonify, request, session
from flask_sqlalchemy import SQLAlchemy
from flask_mail import Mail, Message
from sqlalchemy.exc import OperationalError

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'your-secret-key')  # Set in Render
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///' + os.path.join(os.path.dirname(__file__), 'events.db'))
if app.config['SQLALCHEMY_DATABASE_URI'].startswith('postgres://'):
    app.config['SQLALCHEMY_DATABASE_URI'] = app.config['SQLALCHEMY_DATABASE_URI'].replace('postgres://', 'postgresql://', 1) + '?sslmode=require'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME')  # Set in Render
app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD')  # Set in Render
app.config['MAIL_DEFAULT_SENDER'] = os.environ.get('MAIL_USERNAME')
db = SQLAlchemy(app)
mail = Mail(app)

class Event(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), nullable=False)
    date = db.Column(db.String(120), nullable=False)
    description = db.Column(db.String(200), nullable=False)
    url = db.Column(db.String(200), nullable=False)

class TicketRequest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), nullable=False)
    event_url = db.Column(db.String(200), nullable=False)
    dob = db.Column(db.Date, nullable=False)  # New DOB field
    otp = db.Column(db.String(6), nullable=True)  # OTP field
    verified = db.Column(db.Boolean, default=False)  # OTP verification status

def generate_otp(length=6):
    return ''.join(random.choices(string.digits, k=length))

@app.route('/')
def index():
    try:
        events = Event.query.all()
        return render_template('index.html', events=events)
    except OperationalError as e:
        app.logger.error(f"Database error: {e}")
        return render_template('index.html', events=[], error="Error loading events. Please try again later.")

@app.route('/create-tables')
def create_tables():
    with app.app_context():
        try:
            db.create_all()
            db.session.commit()
            return "Tables created successfully!"
        except Exception as e:
            db.session.rollback()
            return f"Error creating tables: {e}", 500

@app.route('/api/events')
def get_events():
    try:
        events = Event.query.all()
        return jsonify([{'name': event.name, 'date': event.date, 'description': event.description, 'url': event.url} for event in events])
    except OperationalError as e:
        app.logger.error(f"Database error: {e}")
        return jsonify({'error': 'Database error occurred'}), 500

@app.route('/get_tickets', methods=['POST'])
def get_tickets():
    try:
        email = request.form.get('email')
        event_url = request.form.get('url')
        dob = request.form.get('dob')  # New DOB field
        if not email or not event_url or not dob:
            return jsonify({'error': 'Email, URL, and DOB are required'}), 400
        try:
            dob_date = datetime.strptime(dob, '%Y-%m-%d').date()
        except ValueError:
            return jsonify({'error': 'Invalid DOB format (use YYYY-MM-DD)'}), 400
        otp = generate_otp()
        ticket_request = TicketRequest(email=email, event_url=event_url, dob=dob_date, otp=otp, verified=False)
        db.session.add(ticket_request)
        db.session.commit()
        # Send OTP email
        msg = Message('Your OTP for Sydney Events', recipients=[email])
        msg.body = f'Your OTP is {otp}. Enter it to confirm your ticket request.'
        try:
            mail.send(msg)
            session['ticket_id'] = ticket_request.id
            return jsonify({'message': 'OTP sent to your email. Please verify.'})
        except Exception as e:
            db.session.rollback()
            app.logger.error(f"Email error: {e}")
            return jsonify({'error': 'Failed to send OTP email'}), 500
    except Exception as e:
        db.session.rollback()
        app.logger.error(f"Error saving ticket request: {e}")
        return jsonify({'error': 'Failed to process ticket request'}), 500

@app.route('/verify_otp', methods=['POST'])
def verify_otp():
    try:
        otp = request.form.get('otp')
        ticket_id = session.get('ticket_id')
        if not ticket_id or not otp:
            return jsonify({'error': 'OTP and ticket ID are required'}), 400
        ticket_request = TicketRequest.query.get(ticket_id)
        if not ticket_request:
            return jsonify({'error': 'Invalid ticket request'}), 404
        if ticket_request.otp == otp:
            ticket_request.verified = True
            db.session.commit()
            return jsonify({'message': 'OTP verified! You will be redirected.', 'url': ticket_request.event_url})
        else:
            return jsonify({'error': 'Invalid OTP'}), 400
    except Exception as e:
        db.session.rollback()
        app.logger.error(f"OTP verification error: {e}")
        return jsonify({'error': 'Failed to verify OTP'}), 500

if __name__ == '__main__':
    app.run(debug=True)
