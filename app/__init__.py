from flask import Flask, request
from app.extensions import db, bcrypt
from config import Config
from sqlalchemy import text
from app.models import User, Assignment
from flask_jwt_extended import JWTManager, create_access_token, jwt_required, get_jwt_identity
from uuid import uuid4
from sqlalchemy.exc import SQLAlchemyError
from helper_func import create_response, check_request_validity, load_users_from_csv,validate_datetime_format, is_valid_email, is_valid_password
from datetime import datetime
from flask_migrate import Migrate 

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)
    app.config['JWT_SECRET_KEY'] = Config.JWT_SECRET_KEY

    db.init_app(app)
    bcrypt.init_app(app)
    jwt = JWTManager(app)

    migrate = Migrate(app, db)

    with app.app_context():
        db.create_all()
        load_users_from_csv()

    # API's Implementation starts here
    # Login API

    @app.route('/login', methods=['POST'])
    def login():
        data = request.get_json()

        if not data or not data.get('email') or not data.get('password'):
            return create_response(400, {'error': 'Email and password are required!'})
        
        if not is_valid_email(data['email']):
            return create_response(400, {'error': 'Invalid email format'})
        
        if not is_valid_password(data['password']):
            return create_response(400, {'error': 'Invalid password format'})

        user = User.query.filter_by(email=data['email']).first()

        if user and user.verify_password(data['password']):
            access_token = create_access_token(identity=user.id)
            return create_response(200, {'access_token': access_token})
        else:
            return create_response(401, {'error': 'Invalid email or password'})
        

    # Assignment API's

    @app.route('/v1/assignments', methods=['GET'])
    @jwt_required()
    def get_assignments():
        assignments = Assignment.query.all()
        return create_response(200, [assignment.serialize() for assignment in assignments])

    @app.route('/v1/assignments/<string:id>', methods=['GET'])
    @jwt_required()
    def get_assignment(id):
        assignment = Assignment.query.get_or_404(id)
        return create_response(200, assignment.serialize())
    
    # Assignment API's Update

    @app.route('/v1/assignments/<string:id>', methods=['PUT'])
    @jwt_required()
    def update_assignment(id):
        assignment = Assignment.query.get_or_404(id)
        current_user_id = get_jwt_identity()

        if assignment.created_by != current_user_id:
            return create_response(403, {'error': 'Forbidden: You do not have permissions to update this assignment'})

        data = request.get_json()

        # Check if all necessary arguments are present and not empty
        necessary_args = ['name', 'points', 'num_of_attempts', 'deadline']
        for arg in necessary_args:
            if not data.get(arg) or data[arg] == '':
                return create_response(400, {'error': f"The argument '{arg}' is missing or empty!"})

        # If all checks passed, update the assignment attributes
        assignment.name = data['name']
        assignment.points = data['points']
        assignment.num_of_attempts = data['num_of_attempts']
        assignment.deadline = data['deadline']
            
        try:
            valid_flag, processed_deadline = validate_datetime_format(data['deadline'])

            if not valid_flag:
                return create_response(400, {'error': 'Invalid deadline format'})
            if processed_deadline < datetime.utcnow():
                return create_response(400, {'error': 'Deadline must be in the future'})
            assignment.deadline = processed_deadline
        except ValueError:
            return create_response(400, {'error': 'Invalid deadline format'})
            
        assignment.assignment_updated = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        db.session.commit()

        return create_response(204)
    
    # Assignment API's Delete

    @app.route('/v1/assignments/<string:id>', methods=['DELETE'])
    @jwt_required()
    def delete_assignment(id):
        assignment = Assignment.query.get_or_404(id)
        current_user_id = get_jwt_identity()

        if assignment.created_by != current_user_id:
            return create_response(403, {'error': 'Forbidden: You do not have permissions to delete this assignment'})

        db.session.delete(assignment)
        db.session.commit()
        return create_response(204)
    
    # Assignment API's Create

    @app.route('/v1/assignments', methods=['POST'])
    @jwt_required()
    def create_assignment():
        data = request.get_json()
        if not data:
            return create_response(400, {'error': 'Missing data'})

        name = data.get('name')
        points = data.get('points')
        num_of_attempts = data.get('num_of_attempts')
        deadline = data.get('deadline')

        if not all([name, points, num_of_attempts, deadline]):
            return create_response(400, {'error': 'Missing required fields'})
        
        if Assignment.query.filter_by(name=name).first():
            return create_response(400, {'error': 'Assignment name already exists'})

        if not (1 <= points <= 10):
            return create_response(400, {'error': 'Points must be between 1 and 10'})
        
        if not (1 <= num_of_attempts <= 10):
            return create_response(400, {'error': 'Attempts must be between 1 and 10'})
        
        try:
            valid_flag, processed_deadline = validate_datetime_format(deadline)

            if not valid_flag:
                return create_response(400, {'error': 'Invalid deadline format'})
            if processed_deadline < datetime.utcnow():
                return create_response(400, {'error': 'Deadline must be in the future'})
        except ValueError:
            return create_response(400, {'error': 'Invalid deadline format'})

        current_user_id = get_jwt_identity()
        assignment = Assignment(id=str(uuid4()), name=name, points=points, num_of_attempts=num_of_attempts, deadline=processed_deadline, created_by=current_user_id)
        assignment.assignment_updated = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        db.session.add(assignment)
        db.session.commit()
        return create_response(201, assignment.serialize())
    
    # Health Check API

    @app.route('/api/healthz', methods=['GET'])
    def health_check():
        if check_request_validity({'User-Agent', 'Host', 'Content-Type'}):
            return create_response(400)

        try:
            db.session.execute(text('SELECT * FROM user;'))
            return create_response(200)
        except SQLAlchemyError:
            return create_response(503)
        
    # Error Handling

    @app.errorhandler(400)
    def bad_request_error(error):
        return create_response(400, {'error': 'Bad Request', 'message': str(error)})

    @app.errorhandler(401)
    def unauthorized_error(error):
        return create_response(401, {'error': 'Unauthorized', 'message': 'Invalid credentials'})

    @app.errorhandler(404)
    def not_found_error(error):
        return create_response(404, {'error': 'Not Found', 'message': str(error)})

    @app.errorhandler(405)
    def method_not_allowed_error(error):
        return create_response(405, {'error': 'Method Not Allowed', 'message': 'The method is not allowed for the requested URL'})

    @app.errorhandler(500)
    def internal_server_error(error):
        return create_response(500, {'error': 'Internal Server Error', 'message': 'An error occurred on the server'})

    return app
