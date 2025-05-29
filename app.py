import os
import random
import string
from datetime import datetime
from flask import Flask, render_template, jsonify, request, session, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.exc import OperationalError, ProgrammingError
import logging
from flask_migrate import Migrate

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'fallback-secret-key')
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///' + os.path.join(os.path.dirname(__file__), 'events.db'))
if app.config['SQLALCHEMY_DATABASE_URI'].startswith('postgres://'):
    app.config['SQLALCHEMY_DATABASE_URI'] = app.config['SQLALCHEMY_DATABASE_URI'].replace('postgres://', 'postgresql://', 1) + '?sslmode=require'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)
migrate = Migrate(app, db)

# Configure logging
logging.basicConfig(level=logging.DEBUG)
app.logger.setLevel(logging.DEBUG)

class Event(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), nullable=False)
    date = db.Column(db.String(120), nullable=False)
    description = db.Column(db.String(200), nullable=False)
    url = db.Column(db.String(200), nullable=False)
    image_url = db.Column(db.String(200), nullable=True)

    @property
    def display_image_url(self):
        return self.image_url or f"https://picsum.photos/200/300?random={self.id}"

class TicketRequest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), nullable=False)
    event_url = db.Column(db.String(200), nullable=False)
    dob = db.Column(db.Date, nullable=False)
    otp = db.Column(db.String(6), nullable=True)
    verified = db.Column(db.Boolean, default=False)

FIXED_OTP = "649358"

@app.route('/')
def index():
    try:
        events = Event.query.all()
        return render_template('index.html', events=events)
    except (OperationalError, ProgrammingError) as e:
        app.logger.error(f"Database error in index: {str(e)}")
        return render_template('index.html', events=[], error="Error loading events. Please try again later.")

@app.route('/api/events')
def get_events():
    try:
        events = Event.query.all()
        return jsonify([{
            'name': event.name,
            'date': event.date,
            'description': event.description,
            'url': event.url,
            'image_url': event.display_image_url
        } for event in events])
    except (OperationalError, ProgrammingError) as e:
        app.logger.error(f"Database error in get_events: {str(e)}")
        return jsonify({'error': 'Database error occurred'}), 500

@app.route('/get_tickets', methods=['POST'])
def get_tickets():
    try:
        email = request.form.get('email')
        event_url = request.form.get('url')
        dob = request.form.get('dob')
        otp = request.form.get('otp')
        app.logger.debug(f"Received form data: email={email}, url={event_url}, dob={dob}, otp={otp}")

        # If OTP is not provided, create a ticket request
        if not otp:
            if not email or not event_url or not dob:
                flash('Email, URL, and DOB are required.', 'error')
                return redirect(url_for('index'))
            try:
                dob_date = datetime.strptime(dob, '%Y-%m-%d').date()
            except ValueError as e:
                app.logger.error(f"DOB parsing error: {str(e)}")
                flash('Invalid DOB format (use YYYY-MM-DD).', 'error')
                return redirect(url_for('index'))
            ticket_request = TicketRequest(email=email, event_url=event_url, dob=dob_date, otp=FIXED_OTP, verified=False)
            db.session.add(ticket_request)
            db.session.commit()
            app.logger.info(f"Ticket request saved: ID={ticket_request.id}, OTP={FIXED_OTP}")
            session['ticket_id'] = ticket_request.id
            session['user_email'] = email
            session['event_url'] = event_url
            session['dob'] = dob
            flash('Please enter the OTP to verify.', 'info')
            return redirect(url_for('index', ticket_id=ticket_request.id))

        # If OTP is provided, verify it using session data
        ticket_id = session.get('ticket_id')
        user_email = session.get('user_email')
        event_url = session.get('event_url')
        dob = session.get('dob')
        if not ticket_id or not user_email or not event_url or not dob:
            flash('No ticket request found. Please submit ticket details again.', 'error')
            return redirect(url_for('index'))

        ticket_request = TicketRequest.query.get(ticket_id)
        if not ticket_request:
            flash('Invalid ticket request.', 'error')
            return redirect(url_for('index'))

        if otp == FIXED_OTP:
            ticket_request.verified = True
            db.session.commit()
            app.logger.info(f"OTP verified for ticket ID={ticket_id}, email={user_email}, DOB={ticket_request.dob}")
            flash(f'OTP verified for {user_email}! Redirecting to event page.', 'success')
            # Clear session data
            session.pop('ticket_id', None)
            session.pop('user_email', None)
            session.pop('event_url', None)
            session.pop('dob', None)
            return redirect(ticket_request.event_url)
        else:
            app.logger.warning(f"Wrong OTP entered: {otp}")
            flash('Incorrect OTP.', 'error')
            return redirect(url_for('index', ticket_id=ticket_id))

    except Exception as e:
        db.session.rollback()
        app.logger.error(f"Ticket request error: {str(e)}")
        flash(f'Failed to process ticket request: {str(e)}', 'error')
        return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True)
