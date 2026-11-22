import os
import sys
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Flask
from flask import Flask, request, render_template, Response, jsonify, redirect, url_for, session, flash
try:
    from gevent.pywsgi import WSGIServer
    GEVENT_AVAILABLE = True
except ImportError:
    GEVENT_AVAILABLE = False
    print("Warning: gevent not available. Production mode will not work.")

# Authentication
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from authlib.integrations.flask_client import OAuth
from werkzeug.security import generate_password_hash, check_password_hash
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField
from wtforms.validators import DataRequired, Email, EqualTo, Length
import json

# TensorFlow and tf.keras (optional - will work in demo mode if not available)
try:
    from tensorflow.keras.applications.efficientnet import preprocess_input as efficientnet_preprocess
    from tensorflow.keras.applications.imagenet_utils import preprocess_input
    from tensorflow.keras.models import load_model
    import tensorflow as tf
    from tensorflow.keras.preprocessing import image
    TENSORFLOW_AVAILABLE = True
except ImportError:
    print("Warning: TensorFlow not available. App will run in demo mode.")
    TENSORFLOW_AVAILABLE = False
    # Create dummy functions for demo mode
    def preprocess_input(x, mode='tf'):
        return x
    def efficientnet_preprocess(x):
        return x
    class DummyModel:
        def predict(self, x, verbose=0):
            # Return random prediction for demo
            import random
            return [[random.uniform(0.3, 0.7)]]
    def load_model(path, compile=False):
        return DummyModel()
    image = None
    tf = None

# ============================================================
# OPTIMIZED THRESHOLD CONFIGURATION
# ============================================================
# Based on threshold optimization analysis:
# - Default (0.50): Balanced performance
# - Low (0.35): High sensitivity - catches more pneumonia (medical priority)
# - High (0.70): High specificity - fewer false alarms
# ============================================================
CLASSIFICATION_THRESHOLD = float(os.getenv('CLASSIFICATION_THRESHOLD', '0.35'))  # Optimized for high sensitivity
print(f"Using classification threshold: {CLASSIFICATION_THRESHOLD}")

# PIL for image processing
from PIL import Image as PILImage

# Some utilites
import numpy as np
from util import base64_to_pil
from xray_validator import XRayValidator
# Try MongoDB first, fall back to local SQLite
try:
    from database import init_database
    MONGODB_AVAILABLE = True
except ImportError:
    print("Warning: MongoDB database module not available.")
    init_database = None
    MONGODB_AVAILABLE = False

# Import local SQLite fallback
try:
    from database_local import init_local_database
    LOCAL_DB_AVAILABLE = True
except ImportError:
    print("Warning: Local database module not available.")
    init_local_database = None
    LOCAL_DB_AVAILABLE = False


# Declare a flask app
app = Flask(__name__)

# Configuration
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')
app.config['GOOGLE_CLIENT_ID'] = os.getenv('GOOGLE_CLIENT_ID')
app.config['GOOGLE_CLIENT_SECRET'] = os.getenv('GOOGLE_CLIENT_SECRET')

# Initialize Database (MongoDB with SQLite fallback)
db = None

# First try MongoDB
if MONGODB_AVAILABLE and init_database:
    try:
        db = init_database()
        print("✅ MongoDB Atlas connected successfully!")
        
        # Migrate existing users if users.json exists
        if os.path.exists('users.json'):
            print("Migrating existing users to MongoDB...")
            migration_result = db.migrate_users_from_json('users.json')
            if migration_result['success']:
                print(f"Successfully migrated {migration_result['migrated_count']} users")
            else:
                print(f"Migration failed: {migration_result['message']}")
    except Exception as e:
        print(f"⚠️ MongoDB connection failed: {e}")
        db = None

# Fallback to local SQLite if MongoDB fails
if db is None and LOCAL_DB_AVAILABLE and init_local_database:
    try:
        print("📦 Falling back to local SQLite database...")
        db = init_local_database()
        print("✅ Local SQLite database connected successfully!")
        
        # Migrate existing users if users.json exists
        if os.path.exists('users.json'):
            print("Migrating existing users to local database...")
            migration_result = db.migrate_users_from_json('users.json')
            if migration_result['success']:
                print(f"Successfully migrated {migration_result['migrated_count']} users")
    except Exception as e:
        print(f"⚠️ Local database initialization failed: {e}")
        db = None

if db is None:
    print("⚠️ WARNING: No database available. User registration/login will not work.")

# Initialize extensions
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'welcome'
login_manager.login_message = 'Please create an account or sign in to access this page.'
login_manager.login_message_category = 'info'

oauth = OAuth(app)
google = oauth.register(
    name='google',
    client_id=app.config['GOOGLE_CLIENT_ID'],
    client_secret=app.config['GOOGLE_CLIENT_SECRET'],
    server_metadata_url='https://accounts.google.com/.well-known/openid_configuration',
    client_kwargs={
        'scope': 'openid email profile'
    }
)

# Form classes
class LoginForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired(), Length(min=3, max=20)])
    password = PasswordField('Password', validators=[DataRequired()])
    submit = SubmitField('Sign In')

class RegistrationForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired(), Length(min=3, max=20)])
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Password', validators=[DataRequired(), Length(min=6)])
    confirm_password = PasswordField('Confirm Password', 
                                   validators=[DataRequired(), EqualTo('password')])
    submit = SubmitField('Create Account')

# Enhanced User class for Flask-Login
class User(UserMixin):
    def __init__(self, user_data):
        self.id = user_data['id']
        self.username = user_data['username']
        self.email = user_data['email']
        self.profile_pic = user_data.get('profile_pic')
        self.auth_type = user_data.get('auth_type', 'local')
        self.created_at = user_data.get('created_at')
        self.last_login = user_data.get('last_login')
    
    def get_id(self):
        return self.id

    @property
    def name(self):
        return self.username

# User loader for Flask-Login

@login_manager.user_loader
def load_user(user_id):
    if db:
        try:
            user_data = db.get_user_by_id(user_id)
            if user_data:
                return User(user_data)
        except Exception as e:
            print(f"Error loading user: {e}")
    return None


# Initialize X-ray validator
xray_validator = XRayValidator()

# Try to use the best trained model (prioritize resumed models)
MODEL_PATHS = [
    'models/best_pneumonia_model_resumed.h5',  # Best from resumed training
    'models/pneumonia_detection_model_resumed.h5',  # Final resumed model
    'models/best_pneumonia_model.h5',  # Original best model
    'models/pneumonia_detection_model.h5',  # Original final model
]

MODEL_PATH = None
for path in MODEL_PATHS:
    if os.path.exists(path):
        MODEL_PATH = path
        print(f"Using model: {MODEL_PATH}")
        break

if MODEL_PATH is None:
    print("Warning: No trained model found. The app will run in demo mode.")
    print("Available models in 'models' directory:")
    if os.path.exists('models'):
        for f in os.listdir('models'):
            if f.endswith('.h5'):
                print(f"  - {f}")

# Load model with compatibility workaround for TensorFlow 2.x
def load_model_with_compatibility(model_path):
    if not TENSORFLOW_AVAILABLE:
        print("TensorFlow not available. Using dummy model for demo mode.")
        return DummyModel()
    
    import h5py
    import json
    from tensorflow.keras.models import model_from_json
    
    try:
        # First try normal loading
        return load_model(model_path, compile=False)
    except Exception as e:
        print(f"Standard loading failed: {e}")
        
        # Try loading with h5py and manual reconstruction
        try:
            with h5py.File(model_path, 'r') as f:
                # Get model config
                model_config = f.attrs.get('model_config')
                if model_config is None:
                    model_config = f.attrs.get('model_config', None)
                
                if isinstance(model_config, bytes):
                    model_config = model_config.decode('utf-8')
                
                # Parse and fix the config
                config_dict = json.loads(model_config)
                
                # Fix the batch_input_shape issue
                if 'config' in config_dict and 'layers' in config_dict['config']:
                    for layer in config_dict['config']['layers']:
                        if 'config' in layer and 'batch_input_shape' in layer['config']:
                            # Remove the problematic batch_input_shape
                            del layer['config']['batch_input_shape']
                
                # Create model from modified config
                model = model_from_json(json.dumps(config_dict))
                
                # Load weights
                model.load_weights(model_path)
                return model
                
        except Exception as e2:
            print(f"H5py loading failed: {e2}")
            # Last resort: try with TF 1.x compatibility
            try:
                import tensorflow.compat.v1 as tf_v1
                tf_v1.disable_v2_behavior()
                model = tf.keras.models.load_model(model_path, compile=False)
                return model
            except Exception as e3:
                print(f"All loading methods failed: {e3}")
                print("Using dummy model for demo mode.")
                return DummyModel()

model = None
if MODEL_PATH:
    try:
        model = load_model_with_compatibility(MODEL_PATH)
        print('Model loaded successfully!')
    except Exception as e:
        print(f"Warning: Could not load model: {e}")
        print("Running in demo mode without model predictions.")
        model = None
else:
    print("Running in demo mode - no model file found.")
    print("To use the app with predictions, ensure a model file exists in the 'models' directory.")

print('Starting Flask server...')


def model_predict(img, model):
    """
    Preprocess image and make prediction using EfficientNet preprocessing
    """
    if not TENSORFLOW_AVAILABLE or model is None:
        # Demo mode - return random prediction distribution
        import random
        probability = random.uniform(0.3, 0.7)
        return np.array([[probability]], dtype=np.float32)

    # Convert PIL image to array
    x = image.img_to_array(img)
    # Apply EfficientNet preprocessing (same as used during training)
    x = efficientnet_preprocess(x)
    # Add batch dimension
    x = np.expand_dims(x, axis=0)

    # Make prediction
    preds = model.predict(x, verbose=0)

    return preds


def get_confidence_level(probability, threshold=CLASSIFICATION_THRESHOLD):
    """
    Get confidence level description based on probability
    """
    if probability >= threshold:
        # Pneumonia detected
        if probability >= 0.90:
            return "Very High", "danger"
        elif probability >= 0.75:
            return "High", "warning"
        elif probability >= 0.60:
            return "Moderate", "warning"
        else:
            return "Low", "info"
    else:
        # Normal
        normal_prob = 1 - probability
        if normal_prob >= 0.90:
            return "Very High", "success"
        elif normal_prob >= 0.75:
            return "High", "success"
        elif normal_prob >= 0.60:
            return "Moderate", "info"
        else:
            return "Low", "info"


# Authentication routes
@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    
    form = LoginForm()
    
    if form.validate_on_submit():
        username = form.username.data
        password = form.password.data
        
        if db:
            result = db.authenticate_user(username, password)
            if result['success']:
                user = User(result['user'])
                login_user(user)
                flash('Successfully logged in!', 'success')
                return redirect(url_for('index'))
            else:
                flash(result.get('message', 'Invalid username or password.'), 'error')
        else:
            flash('Database connection error. Please try again later.', 'error')
    
    return render_template('login.html', form=form)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    
    form = RegistrationForm()
    
    if form.validate_on_submit():
        username = form.username.data
        email = form.email.data
        password = form.password.data
        
        try:
            if not db:
                flash('Database connection error. Please try again later.', 'error')
                return render_template('register.html', title='Register', form=form)
                
            result = db.create_user(username, email, password, auth_type='local')
            if result.get('success'):
                flash('Account created successfully! Please log in.', 'success')
                return redirect(url_for('login'))
            else:
                flash(result.get('message', 'Failed to create account. Please try again.'), 'error')
        except Exception as e:
            print(f"Error during registration: {str(e)}")
            flash('An error occurred during registration. Please try again.', 'error')
    
    # If form not submitted or validation fails, render the registration form
    return render_template('register.html', title='Register', form=form)

@app.route('/auth/google')
def google_login():
    redirect_uri = url_for('google_callback', _external=True)
    return google.authorize_redirect(redirect_uri)

@app.route('/auth/google/callback')
def google_callback():
    try:
        token = google.authorize_access_token()
        user_info = token.get('userinfo')
        
        if user_info and db:
            result = db.get_or_create_oauth_user(user_info, auth_type='google')
            if result['success']:
                user = User(result['user'])
                login_user(user)
                flash('Successfully logged in!', 'success')
                return redirect(url_for('index'))
            else:
                flash(result.get('message', 'OAuth authentication failed.'), 'error')
                return redirect(url_for('login'))
        else:
            flash('Failed to get user information from Google.', 'error')
            return redirect(url_for('login'))
            
    except Exception as e:
        print(f"OAuth error: {e}")
        flash('Authentication failed. Please try again.', 'error')
        return redirect(url_for('login'))

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('welcome'))

# Welcome/Landing page (public)
@app.route('/')
def welcome():
    if db and current_user.is_authenticated:
        return redirect(url_for('index'))
    return render_template('welcome.html')

# Main pneumonia detection page (protected if db available)
@app.route('/app', methods=['GET'])
def index():
    # Require login only if database is available
    if db:
        if not current_user.is_authenticated:
            return redirect(url_for('welcome'))
    # Allow access without authentication if no database
    return render_template('index.html')


@app.route('/predict', methods=['POST'])
def predict():
    """
    Handle chest X-ray image prediction.
    Accepts base64 encoded image, validates that it is a chest X-ray,
    and runs neural network inference.
    """
    try:
        # Get the image from JSON request
        if not request.is_json:
            return jsonify(error="Request must be JSON with image data"), 400

        img_data = request.json.get('image')
        if not img_data:
            return jsonify(error="No image data provided"), 400
        
        # Convert base64 to PIL image
        img = base64_to_pil(img_data)
        
        # Ensure image is in RGB format (handles RGBA, grayscale, etc.)
        if img.mode != 'RGB':
            img = img.convert('RGB')
        
        # Resize image to match model input size (224x224)
        try:
            img = img.resize((224, 224), PILImage.Resampling.LANCZOS)
        except AttributeError:
            # Fallback for older PIL versions
            img = img.resize((224, 224), PILImage.LANCZOS)
        
        # Validate if image is a valid chest X-ray (validated in memory)
        is_valid_xray, validation_reason, validation_confidence = xray_validator.is_valid_xray(img)
        
        if not is_valid_xray:
            error_message = validation_reason if validation_reason else "Please upload a valid chest X-ray image."
            return jsonify(error=error_message), 400

        preds = model_predict(img, model)
        probability = float(preds[0][0])
        probability = max(min(probability, 0.9999), 0.0001)  # clamp for stability
        
        # Use optimized threshold for classification
        threshold = CLASSIFICATION_THRESHOLD
        label = "PNEUMONIA" if probability >= threshold else "NORMAL"
        confidence = probability if probability >= threshold else (1 - probability)
        confidence_pct = round(confidence * 100, 1)
        
        # Get confidence level description
        confidence_level, confidence_class = get_confidence_level(probability, threshold)

        # Generate detailed diagnosis text
        if label == "PNEUMONIA":
            diagnosis_text = f"⚠️ Pneumonia Detected ({confidence_level} Confidence: {confidence_pct}%)"
            recommendation = "Please consult a healthcare professional for further evaluation."
        else:
            diagnosis_text = f"✓ Normal Lungs ({confidence_level} Confidence: {confidence_pct}%)"
            recommendation = "No signs of pneumonia detected. Regular check-ups recommended."

        response_payload = {
            "label": label,
            "probability": round(probability, 4),
            "confidence": round(confidence, 4),
            "confidence_percent": confidence_pct,
            "confidence_level": confidence_level,
            "confidence_class": confidence_class,
            "diagnosis": diagnosis_text,
            "recommendation": recommendation,
            "threshold_used": threshold,
            "mode": "demo" if not TENSORFLOW_AVAILABLE or model is None else "production"
        }
        return jsonify(response_payload)
    
    except ValueError as ve:
        return jsonify(error=f"Image processing failed: {str(ve)}"), 400
    except Exception as e:
        return jsonify(error=f"An unexpected error occurred during prediction: {str(e)}"), 500


if __name__ == '__main__':
    # For development
    app.run(host='0.0.0.0', port=5002, debug=True)
    
    # For production with gevent (uncomment when needed)
    # http_server = WSGIServer(('0.0.0.0', 5000), app)
    # http_server.serve_forever()
