import os
import random
import string
from datetime import datetime
from flask import Flask, render_template, jsonify, request, session
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.exc import OperationalError
import logging

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'fallback-secret-key')
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///' + os.path.join(os.path.dirname(__file__), 'events.db'))
if app.config['SQLALCHEMY_DATABASE_URI'].startswith('postgres://'):
    app.config['SQLALCHEMY_DATABASE_URI'] = app.config['SQLALCHEMY_DATABASE_URI'].replace('postgres://', 'postgresql://', 1) + '?sslmode=require'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# Configure logging
logging.basicConfig(level=logging.DEBUG)
app.logger.setLevel(logging.DEBUG)

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
    dob = db.Column(db.Date, nullable=False)
    otp = db.Column(db.String(6), nullable=True)
    verified = db.Column(db.Boolean, default=False)

def generate_otp(length=6):
    return ''.join(random.choices(string.digits, k=length))

@app.route('/')
def index():
    try:
        events = Event.query.all()
        return render_template('index.html', events=events)
    except OperationalError as e:
        app.logger.error(f"Database error in index: {str(e)}")
        return render_template('index.html', events=[], error="Error loading events. Please try again later.")

@app.route('/create-tables')
def create_tables():
    with app.app_context():
        try:
            db.create_all()
            db.session.commit()
            app.logger.info("Tables created successfully")
            return "Tables created successfully!"
        except Exception as e:
            db.session.rollback()
            app.logger.error(f"Error creating tables: {str(e)}")
            return f"Error creating tables: {str(e)}", 500

@app.route('/api/events')
def get_events():
    try:
        events = Event.query.all()
        return jsonify([{'name': event.name, 'date': event.date, 'description': event.description, 'url': event.url} for event in events])
    except OperationalError as e:
        app.logger.error(f"Database error in get_events: {str(e)}")
        return jsonify({'error': 'Database error occurred'}), 500

@app.route('/get_tickets', methods=['POST'])
def get_tickets():
    try:
        email = request.form.get('email')
        event_url = request.form.get('url')
        dob = request.form.get('dob')
        app.logger.debug(f"Received form data: email={email}, url={event_url}, dob={dob}")
        if not email or not event_url or not dob:
            return jsonify({'error': 'Email, URL, and DOB are required'}), 400
        try:
            dob_date = datetime.strptime(dob, '%Y-%m-%d').date()
        except ValueError as e:
            app.logger.error(f"DOB parsing error: {str(e)}")
            return jsonify({'error': 'Invalid DOB format (use YYYY-MM-DD)'}), 400
        otp = generate_otp()
        ticket_request = TicketRequest(email=email, event_url=event_url, dob=dob_date, otp=otp, verified=False)
        db.session.add(ticket_request)
        db.session.commit()
        app.logger.info(f"Ticket request saved: ID={ticket_request.id}, OTP={otp}")
        session['ticket_id'] = ticket_request.id
        # Return OTP in response for testing (in production, use email)
        return jsonify({'message': 'OTP generated. Enter it to verify.', 'otp': otp})  # Remove 'otp' in production
    except Exception as e:
        db.session.rollback()
        app.logger.error(f"Ticket request error: {str(e)}")
        return jsonify({'error': f'Failed to process ticket request: {str(e)}'}), 500

@app.route('/verify_otp', methods=['POST'])
def verify_otp():
    try:
        otp = request.form.get('otp')
        ticket_id = session.get('ticket_id')
        app.logger.debug(f"Verifying OTP: otp={otp}, ticket_id={ticket_id}")
        if not ticket_id or not otp:
            return jsonify({'error': 'OTP and ticket ID are required'}), 400
        ticket_request = TicketRequest.query.get(ticket_id)
        if not ticket_request:
            return jsonify({'error': 'Invalid ticket request'}), 404
        if ticket_request.otp == otp:
            ticket_request.verified = True
            db.session.commit()
            app.logger.info(f"OTP verified for ticket ID={ticket_id}")
            return jsonify({'message': 'OTP verified! You will be redirected.', 'url': ticket_request.event_url})
        else:
            return jsonify({'error': 'Invalid OTP'}), 400
    except Exception as e:
        db.session.rollback()
        app.logger.error(f"OTP verification error: {str(e)}")
        return jsonify({'error': 'Failed to verify OTP'}), 500

if __name__ == '__main__':
    app.run(debug=True)
