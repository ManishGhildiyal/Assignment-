import os
import random
import string
from datetime import datetime
from flask import Flask, render_template, jsonify, request, session, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.sql import text
import logging
from flask_migrate import Migrate

app = Flask(_name_)
app.secret_key = os.environ.get('SECRET_KEY', 'fallback-secret-key')
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///' + os.path.join(os.path.dirname(_file_), 'events.db'))
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
        if self.image_url:
            return self.image_url
        app.logger.info(f"Using placeholder image for event ID={self.id}, name={self.name}")
        return f"https://picsum.photos/200/200?random={self.id}"

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
        return render_template('index.html', events=[], error="Unable to load events due to a database issue. Please try again later.")

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
        otp = request.form.get('otp')
        event_url = request.form.get('url')
        app.logger.debug(f"Received form data: url={event_url}, otp={otp}")

        # If OTP is not provided, process initial ticket request
        if not otp:
            email = request.form.get('email')
            dob = request.form.get('dob')
            app.logger.debug(f"Initial request: email={email}, dob={dob}")

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
            session['event_url'] = event_url
            flash('Please enter the OTP to verify.', 'info')
            return redirect(url_for('index', ticket_id=ticket_request.id))

        # If OTP is provided, verify it
        ticket_id = session.get('ticket_id')
        if not ticket_id:
            flash('No ticket request found. Please submit ticket details again.', 'error')
            return redirect(url_for('index'))

        ticket_request = TicketRequest.query.get(ticket_id)
        if not ticket_request or ticket_request.event_url != event_url:
            flash('Invalid ticket request.', 'error')
            session.pop('ticket_id', None)
            session.pop('event_url', None)
            return redirect(url_for('index'))

        if otp == ticket_request.otp:
            ticket_request.verified = True
            db.session.commit()
            app.logger.info(f"OTP verified for ticket ID={ticket_id}, email={ticket_request.email}")
            flash(f'OTP verified for {ticket_request.email}! Redirecting to event page.', 'success')
            # Clear session data
            session.pop('ticket_id', None)
            session.pop('event_url', None)
            return redirect(ticket_request.event_url)
        else:
            app.logger.warning(f"Wrong OTP entered: {otp}")
            flash('Incorrect OTP. Please try again.', 'error')
            return redirect(url_for('index', ticket_id=ticket_id))

    except Exception as e:
        db.session.rollback()
        app.logger.error(f"Ticket request error: {str(e)}")
        flash(f'Failed to process ticket request: {str(e)}', 'error')
        return redirect(url_for('index'))

def check_migration_status():
    try:
        with app.app_context():
            db.session.execute(text('SELECT * FROM alembic_version'))
            app.logger.info("Alembic version table exists, migrations are set up.")
    except (OperationalError, ProgrammingError) as e:
        app.logger.warning(f"Migration check failed: {str(e)}. Ensure migrations are applied with 'flask db upgrade'.")

# Run migration check after app initialization
check_migration_status()

if _name_ == '_main_':
    app.run(debug=True)
