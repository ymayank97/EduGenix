from app.extensions import db, bcrypt
from datetime import datetime

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    first_name = db.Column(db.String(50), nullable=False)
    last_name = db.Column(db.String(50), nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)

    account_created = db.Column(db.DateTime, default=datetime.utcnow)
    account_updated = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    @property
    def password(self):
        raise AttributeError('password is not a readable attribute')
    
    @password.setter
    def password(self, password):
        self.password_hash = bcrypt.generate_password_hash(password).decode('utf-8')

    def verify_password(self, password):
        return bcrypt.check_password_hash(self.password_hash, password)



class Assignment(db.Model):
    id = db.Column(db.String, primary_key=True)  # UUID as string
    name = db.Column(db.String(50), nullable=False, unique=True)
    points = db.Column(db.Integer, nullable=False)
    num_of_attempts = db.Column(db.Integer, nullable=False)
    deadline = db.Column(db.DateTime, nullable=False)
    assignment_created = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    assignment_updated = db.Column(db.DateTime, nullable=True, onupdate=datetime.utcnow)

    created_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    creator = db.relationship('User', backref='assignments')

    def serialize(self):
        """ Return object data in easily serializable format"""
        return {
            'id': self.id,
            'name': self.name,
            'points': self.points,
            'num_of_attempts': self.num_of_attempts,
            'deadline': self.deadline.isoformat(),
            'assignment_created': self.assignment_created.isoformat(),
            'assignment_updated': self.assignment_updated.isoformat() if self.assignment_updated else None
            }
