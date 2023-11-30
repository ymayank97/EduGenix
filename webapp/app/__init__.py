from datetime import datetime
from functools import wraps
from flask import Flask, request, abort
from flask_migrate import Migrate
from sqlalchemy import text
from app.models import User, Assignment, Submission
from uuid import uuid4
from sqlalchemy.exc import SQLAlchemyError
from app.extensions import db, bcrypt, logger, statsd, publish_to_sns
from config import Config
from helper_func import (
    create_response,
    load_users_from_csv,
    validate_datetime_format,
    is_valid_email,
    is_valid_password,
)


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    logger.info('Flask app "MyFlaskApp" starting up.')
    logger.info("Using config: %s", config_class)

    db.init_app(app)
    bcrypt.init_app(app)

    Migrate(app, db)

    with app.app_context():
        db.create_all()
        load_users_from_csv()
        logger.info("Connected to database successfully.")

    logger.info("Flask app ready to serve requests.")

    # API's Implementation starts here
    def basic_auth_required(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            auth = request.authorization

            if not auth or not auth.username or not auth.password:
                abort(401, description="Missing Basic Auth credentials")

            if not is_valid_email(auth.username):
                abort(400, description="Invalid email format")

            if not is_valid_password(auth.password):
                abort(400, description="Invalid password format")
            try:
                user = User.query.filter_by(email=auth.username).first()
            except SQLAlchemyError:
                abort(503, description="Database connection error")

            if not user or not user.verify_password(auth.password):
                abort(401, description="Invalid email or password")

            return fn(*args, **kwargs)

        return wrapper

    def get_user_id_from_basic_auth():
        auth = request.authorization
        if not auth:
            return None

        user = User.query.filter_by(email=auth.username).first()
        if not user or not user.verify_password(auth.password):
            return None
        return user.id

    def get_email_from_basic_auth():
        auth = request.authorization
        if not auth:
            return None
        return auth.username

    # Assignment API's Read
    @app.route("/v1/assignments", methods=["GET"])
    @basic_auth_required
    def get_assignments():
        statsd.incr(".assignments.get")
        assignments = Assignment.query.all()
        logger.info("Assignments retrieved successfully.")
        return create_response(
            200, [assignment.serialize() for assignment in assignments]
        )

    @app.route("/v1/assignments/<string:ass_id>", methods=["GET"])
    @basic_auth_required
    def get_assignment(ass_id):
        statsd.incr(".assignments.get")
        assignment = Assignment.query.get_or_404(ass_id)
        logger.info("Assignment retrieved successfully.")
        return create_response(200, assignment.serialize())

    # Assignment API's Update

    @app.route("/v1/assignments/<string:ass_id>", methods=["PUT"])
    @basic_auth_required
    def update_assignment(ass_id):
        statsd.incr(".assignments.update")
        assignment = Assignment.query.get_or_404(ass_id)
        current_user_id = get_user_id_from_basic_auth()

        if assignment.created_by != current_user_id:
            abort(
                403,
                description="Forbidden: You do not have permissions to update this assignment",
            )

        data = request.get_json()

        # Check if all necessary arguments are present and not empty
        necessary_args = ["name", "points", "num_of_attempts", "deadline"]
        for arg in necessary_args:
            if not data.get(arg) or data[arg] == "":
                abort(400, description="Missing required fields")

        # If all checks passed, update the assignment attributes
        assignment.name = data["name"]
        assignment.points = data["points"]
        assignment.num_of_attempts = data["num_of_attempts"]
        assignment.deadline = data["deadline"]

        try:
            valid_flag, processed_deadline = validate_datetime_format(data["deadline"])

            if not valid_flag:
                abort(400, description="Invalid deadline format")
            assignment.deadline = processed_deadline
        except ValueError:
            abort(400, description="Invalid deadline format")

        assignment.assignment_updated = datetime.utcnow().strftime(
            "%Y-%m-%dT%H:%M:%S.%fZ"
        )
        db.session.commit()
        logger.info("Assignment updated successfully.")

        return create_response(204)

    # Assignment API's Delete

    @app.route("/v1/assignments/<string:ass_id>", methods=["DELETE"])
    @basic_auth_required
    def delete_assignment(ass_id):
        statsd.incr(".assignments.delete")
        if request.data or request.args:
            abort(400, description="Request body must be empty")

        assignment = Assignment.query.get_or_404(ass_id)
        current_user_id = get_user_id_from_basic_auth()

        if assignment.created_by != current_user_id:
            abort(
                403,
                description="Forbidden: You do not have permissions to delete this assignment",
            )

        # Delete all related submissions first
        Submission.query.filter_by(assignment_id=ass_id).delete()

        db.session.delete(assignment)
        db.session.commit()
        logger.info("Assignment deleted successfully.")
        return create_response(204)

    # Assignment API's Create

    @app.route("/v1/assignments", methods=["POST"])
    @basic_auth_required
    def create_assignment():
        statsd.incr(".assignments.create")
        data = request.get_json()
        if not data:
            abort(400, description="Request body must be present")
        name = data.get("name")
        points = data.get("points")
        num_of_attempts = data.get("num_of_attempts")
        deadline = data.get("deadline")

        if not all([name, points, num_of_attempts, deadline]):
            abort(400, description="Missing required fields")

        if not (1 <= points <= 10):
            abort(400, description="Points must be between 1 and 10")

        if not (1 <= num_of_attempts <= 10):
            abort(400, description="Number of attempts must be between 1 and 10")

        try:
            valid_flag, processed_deadline = validate_datetime_format(deadline)

            if not valid_flag:
                abort(400, description="Invalid deadline format")
        except ValueError:
            abort(400, description="Invalid deadline format")

        current_user_id = get_user_id_from_basic_auth()
        assignment = Assignment(
            id=str(uuid4()),
            name=name,
            points=points,
            num_of_attempts=num_of_attempts,
            deadline=processed_deadline,
            created_by=current_user_id,
        )
        assignment.assignment_updated = datetime.utcnow().strftime(
            "%Y-%m-%dT%H:%M:%S.%fZ"
        )
        db.session.add(assignment)
        db.session.commit()
        logger.info("Assignment created successfully.")
        return create_response(201, assignment.serialize())

    # Health Check API
    @app.route("/healthz", methods=["GET"])
    def health_check():
        if request.data or request.args:
            abort(400, description="Request body must be empty")
        statsd.incr(".healthz")
        try:
            db.session.execute(text("SELECT * FROM user;"))
            return create_response(200)
        except SQLAlchemyError:
            abort(503, description="Database connection error")

    @app.route("/v1/assignments/<string:ass_id>/submission", methods=["POST"])
    @basic_auth_required
    def create_submission(ass_id):
        statsd.incr(".submissions.create")
        data = request.get_json()
        if not data:
            abort(400, description="Request body must be present")

        assignment = Assignment.query.get_or_404(ass_id)
        submission_url = data.get("submission_url")

        if not submission_url:
            abort(400, description="Missing required fields")

        if assignment.deadline <= datetime.utcnow():
            abort(400, description="Deadline has passed for this assignment")

        previous_submissions = Submission.query.filter_by(assignment_id=ass_id).all()

        attempts_left = assignment.num_of_attempts - len(previous_submissions)

        if attempts_left <= 0:
            abort(400, description="No attempts left for this assignment")

        submission_date = (
            previous_submissions[-1].submission_date
            if previous_submissions
            else datetime.utcnow()
        )
        submission = Submission(
            assignment_id=ass_id,
            submission_url=submission_url,
            submission_date=submission_date,
            assignment_updated=datetime.utcnow(),
        )
        db.session.add(submission)
        db.session.commit()
        logger.info("Submission created successfully.")
        # get email based on user id
        username = get_email_from_basic_auth()
        publish_to_sns(submission_url, username, ass_id, assignment.name, len(previous_submissions))
        logger.info("SNS message published successfully.")

        return create_response(201, submission.serialize())

    # Error Handling
    @app.errorhandler(400)
    def bad_request_error(error):
        statsd.incr(".error.400")
        logger.error("Error processing request: %s", error)
        return create_response(400, {"error": "Bad Request", "message": str(error)})

    @app.errorhandler(401)
    def unauthorized_error(error):
        statsd.incr(".error.401")
        logger.error("Error processing request: %s", error)
        return create_response(
            401, {"error": "Unauthorized", "message": "Invalid credentials"}
        )

    @app.errorhandler(403)
    def forbidden_error(error):
        statsd.incr(".error.403")
        logger.error("Error processing request: %s", error)
        return create_response(403, {"error": "Forbidden", "message": str(error)})

    @app.errorhandler(404)
    def not_found_error(error):
        statsd.incr(".error.404")
        logger.error("Error processing request: %s", error)
        return create_response(404, {"error": "Not Found", "message": str(error)})

    @app.errorhandler(405)
    def method_not_allowed_error(error):
        statsd.incr(".error.405")
        logger.error("Error processing request: %s", error)
        return create_response(
            405,
            {
                "error": "Method Not Allowed",
                "message": "The method is not allowed for the requested URL",
            },
        )

    @app.errorhandler(500)
    def internal_server_error(error):
        statsd.incr(".error.500")
        logger.error("Error processing request: %s", error)
        return create_response(
            500,
            {
                "error": "Internal Server Error",
                "message": "An error occurred on the server",
            },
        )

    @app.errorhandler(503)
    def internal_server_error_503(error):
        statsd.incr(".error.503")
        logger.error("Error processing request: %s", error)
        return create_response(
            503,
            {
                "error": "Service Unavailable",
                "message": "The server is currently unavailable",
            },
        )

    return app
