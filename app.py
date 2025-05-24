import os
from flask import Flask, render_template, jsonify, request
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.exc import OperationalError

app = Flask(__name__)
# Use PostgreSQL on Render, fallback to SQLite locally
database_url = os.environ.get('DATABASE_URL')
if database_url:
    # Replace 'postgres://' with 'postgresql://' for SQLAlchemy and add sslmode
    if database_url.startswith('postgres://'):
        database_url = database_url.replace('postgres://', 'postgresql://', 1)
    app.config['SQLALCHEMY_DATABASE_URI'] = database_url + '?sslmode=require'
else:
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(os.path.dirname(__file__), 'events.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

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
        if not email or not event_url:
            return jsonify({'error': 'Email and URL are required'}), 400
        ticket_request = TicketRequest(email=email, event_url=event_url)
        db.session.add(ticket_request)
        db.session.commit()
        return jsonify({'message': 'Thank you! You will be redirected.', 'url': event_url})
    except Exception as e:
        db.session.rollback()
        app.logger.error(f"Error saving ticket request: {e}")
        return jsonify({'error': 'Failed to process ticket request'}), 500

if __name__ == '__main__':
    app.run(debug=True)