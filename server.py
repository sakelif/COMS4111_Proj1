import os
from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool
from flask import Flask, request, render_template, g, redirect, url_for, flash, session

tmpl_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates')
app = Flask(__name__, template_folder=tmpl_dir)

# Database configuration
DB_USER = "em3772"
DB_PASSWORD = "emes3739"
DB_SERVER = "w4111.cisxo09blonu.us-east-1.rds.amazonaws.com"
DATABASEURI = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_SERVER}/proj1part2"

# Initialize the database engine
engine = create_engine(DATABASEURI, poolclass=NullPool)
app.secret_key = os.urandom(12)

# Database connection setup
@app.before_request
def before_request():
    try:
        g.conn = engine.connect()
    except Exception as e:
        print("Problem connecting to database:", e)
        g.conn = None

@app.teardown_request
def teardown_request(exception):
    try:
        g.conn.close()
    except Exception as e:
        pass

# Home route
@app.route('/')
def home():
    if not session.get('logged_in'):
        return render_template('login.html')
    elif session.get('is_admin'):
        return redirect(url_for('admin_dashboard'))
    else:
        return redirect(url_for('customer_dashboard'))

# Login route
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        query = """
            SELECT user_id, employee_id AS is_admin
            FROM Users
            WHERE name = :username AND password = :password;
        """
        result = g.conn.execute(text(query), {'username': username, 'password': password}).fetchone()
        
        if result:
            session['logged_in'] = True
            session['user_id'] = result['user_id']
            session['is_admin'] = result['is_admin']
            return redirect(url_for('home'))
        else:
            flash('Invalid credentials')
            return redirect(url_for('login'))
    return render_template('login.html')

# Logout route
@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for('home'))

# Registration route
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        is_admin = request.form['is_admin'] == 'admin'
        
        if is_admin:
            # Admin registration
            query = "INSERT INTO Users ( name, password, employee_id)  VALUES (:username, :password, TRUE)"
            g.conn.execute(text(query), {'username': username, 'password': password})
            flash('Admin profile created successfully')
        else:
            # Customer registration with location data
            latitude = request.form['latitude']
            longitude = request.form['longitude']
            photo = request.form['photo']
            query = """
                INSERT INTO Users (name, password, employee_id, photo, latitude, longitude)
                VALUES (:username, :password, FALSE, :photo, :latitude, :longitude)
            """
            g.conn.execute(text(query), {'username': username, 'password': password, 'photo': photo, 'latitude': latitude, 'longitude': longitude})
            flash('Customer profile created successfully')
        
        return redirect(url_for('login'))
    return render_template('register.html')

# Customer dashboard route
@app.route('/customer_dashboard')
def customer_dashboard():
    if session.get('is_admin'):
        return redirect(url_for('home'))
    user_id = session.get('user_id')
    saved_restaurants = get_saved_restaurants(user_id)
    all_restaurants = get_all_restaurants()
    return render_template('customer_dashboard.html', saved_restaurants=saved_restaurants, all_restaurants=all_restaurants)

# Admin dashboard route
@app.route('/admin_dashboard', methods=['GET', 'POST'])
def admin_dashboard():
    if not session.get('is_admin'):
        return redirect(url_for('home'))
    if request.method == 'POST':
        rest_name = request.form['rest_name']
        loc = request.form['loc']
        latitude = request.form['latitude']
        longitude = request.form['longitude']
        cuisineType = request.form['cuisineType']
        diet_name = request.form['diet_name']
        user_id = session.get('user_id')
        
        query = """
            INSERT INTO Restaurant_Creates (rest_name, loc, latitude, longitude, cuisineType, diet_name, user_id)
            VALUES (:rest_name, :loc, :latitude, :longitude, :cuisineType, :diet_name, :user_id)
        """
        try:
            g.conn.execute(text(query), {
                'rest_name': rest_name, 'loc': loc, 'latitude': latitude,
                'longitude': longitude, 'cuisineType': cuisineType, 'diet_name': diet_name, 'user_id': user_id
            })
            flash('Restaurant created successfully')
        except Exception as e:
            flash('Error creating restaurant')
            print(e)
    
    return render_template('admin_dashboard.html')

# Submit review for a restaurant
@app.route('/write_review', methods=['POST'])
def write_review():
    if session.get('is_admin'):
        return redirect(url_for('home'))
    user_id = session.get('user_id')
    rest_name = request.form['rest_name']
    contents = request.form['contents']
    rating = request.form['rating']
    
    query = """
        INSERT INTO Review_Writes (contents, rating, user_id)
        VALUES (:contents, :rating, :user_id)
        RETURNING review_id
    """
    result = g.conn.execute(text(query), {'contents': contents, 'rating': rating, 'user_id': user_id}).fetchone()
    review_id = result['review_id']

    # Link review to restaurant
    query = "INSERT INTO Review_has (review_id, rest_name) VALUES (:review_id, :rest_name)"
    g.conn.execute(text(query), {'review_id': review_id, 'rest_name': rest_name})
    
    flash('Review submitted successfully')
    return redirect(url_for('customer_dashboard'))

# Helper function to get all restaurants
def get_all_restaurants():
    query = "SELECT rest_name, loc FROM Restaurant_Creates"
    return g.conn.execute(text(query)).fetchall()

# Helper function to get saved restaurants for a user
def get_saved_restaurants(user_id):
    query = "SELECT rest_name FROM Customer_Saves WHERE user_id = :user_id"
    return g.conn.execute(text(query), {'user_id': user_id}).fetchall()

if __name__ == "__main__":
    import click

    @click.command()
    @click.option('--debug', is_flag=True)
    @click.option('--threaded', is_flag=True)
    @click.argument('HOST', default='0.0.0.0')
    @click.argument('PORT', default=8111, type=int)
    def run(debug, threaded, host, port):
        print(f"Running on {host}:{port}")
        app.run(host=host, port=port, debug=debug, threaded=threaded)

    run()

