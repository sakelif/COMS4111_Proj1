import os
import random
from math import radians, sin, cos, sqrt, atan2
from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool
from flask import Flask, request, render_template, g, redirect, url_for, flash, session
from werkzeug.security import generate_password_hash, check_password_hash

tmpl_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates')
app = Flask(__name__, template_folder=tmpl_dir)

# Database configuration
DB_USER = "em3772"
DB_PASSWORD = "emes3739"
DB_SERVER = "w4111.cisxo09blonu.us-east-1.rds.amazonaws.com"
DATABASEURI = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_SERVER}/w4111"

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
    if g.conn:
        g.conn.close()

# Function to generate a random user_id
def generate_random_user_id():
    return random.randint(10000, 99999)

# Function to calculate distance between two locations based on latitude and longitude
def calculate_distance(lat1, lon1, lat2, lon2):
    R = 3959  # Radius of Earth in miles
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))
    return R * c

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
        query = f"SELECT user_id, employee_id AS is_admin, password FROM People WHERE name = '{username}'"
        result = g.conn.execute(query).fetchone()
        print(result)
        print(result['password'])
        h_password = generate_password_hash(password)
        print(password)
        if result and check_password_hash(h_password, password):
            session['logged_in'] = True
            session['user_id'] = result['user_id']
            session['is_admin'] = result['is_admin']
            return redirect(url_for('home'))
        else:
            flash('Invalid credentials')
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
        
        hashed_password = generate_password_hash(password)
        user_id = generate_random_user_id()
        
        try:
            if is_admin:
                query = "INSERT INTO People (user_id, name, password, employee_id) VALUES (:user_id, :username, :password, TRUE)"
                g.conn.execute(text(query), {'user_id': user_id, 'username': username, 'password': hashed_password})
                flash('Admin profile created successfully')
            else:
                latitude = request.form['latitude']
                longitude = request.form['longitude']
                photo = request.form['photo']
                query = """
                    INSERT INTO People (user_id, name, password, employee_id, photo, latitude, longitude)
                    VALUES (:user_id, :username, :password, FALSE, :photo, :latitude, :longitude)
                """
                g.conn.execute(text(query), {
                    'user_id': user_id, 'username': username, 'password': hashed_password,
                    'photo': photo, 'latitude': latitude, 'longitude': longitude
                })
                flash('Customer profile created successfully')
        except Exception as e:
            print("Registration Error:", e)
            flash('Error during registration')
        
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
    all_reviews = get_all_reviews()  # Get all reviews for display

    return render_template('customer_dashboard.html', 
                           saved_restaurants=saved_restaurants, 
                           all_restaurants=all_restaurants, 
                           all_reviews=all_reviews)

# Route to display restaurant details
@app.route('/restaurant/<rest_name>', methods=['GET', 'POST'])
def restaurant_details(rest_name):
    user_id = session.get('user_id')
    
    # Save restaurant if requested
    if request.method == 'POST' and 'save_restaurant' in request.form:
        query = "INSERT INTO Customer_Saves (user_id, rest_name) VALUES (:user_id, :rest_name) ON CONFLICT DO NOTHING"
        g.conn.execute(text(query), {'user_id': user_id, 'rest_name': rest_name})
        flash('Restaurant saved successfully')

    # Write review if requested
    if request.method == 'POST' and 'write_review' in request.form:
        contents = request.form['review_content']
        rating = int(request.form['rating'])
        query = """
            INSERT INTO Review_Writes (contents, rating, user_id) 
            VALUES (:contents, :rating, :user_id) RETURNING review_id
        """
        review_id = g.conn.execute(text(query), {'contents': contents, 'rating': rating, 'user_id': user_id}).fetchone()['review_id']
        # Link review to restaurant
        g.conn.execute(text("INSERT INTO Review_has (review_id, rest_name) VALUES (:review_id, :rest_name)"),
                       {'review_id': review_id, 'rest_name': rest_name})
        flash('Review submitted successfully')

    # Fetch restaurant details, including cuisine type and diet
    query = """
        SELECT r.rest_name, r.loc, r.latitude, r.longitude, r.cuisineType, r.diet_name
        FROM Restaurant_Creates r
        WHERE r.rest_name = :rest_name
    """
    restaurant = g.conn.execute(text(query), {'rest_name': rest_name}).fetchone()
    
    # Calculate distance from user to restaurant
    user_query = "SELECT latitude, longitude FROM People WHERE user_id = :user_id"
    user_location = g.conn.execute(text(user_query), {'user_id': user_id}).fetchone()
    distance = calculate_distance(user_location['latitude'], user_location['longitude'], restaurant['latitude'], restaurant['longitude'])
    
    # Fetch menu items and check for allergens, displaying ingredients on a single line
    menu_query = """
        SELECT mic.item_name, STRING_AGG(mii.ing_name, ', ') AS ingredients,
               CASE WHEN bool_or(ca.allergen IS NOT NULL) THEN TRUE ELSE FALSE END AS contains_allergen
        FROM Menu_Item_Includes mii
        JOIN Menu_Item_Contains mic ON mii.item_name = mic.item_name
        LEFT JOIN Customer_Allergens ca ON mii.ing_name = ca.allergen AND ca.user_id = :user_id
        WHERE mic.rest_name = :rest_name
        GROUP BY mic.item_name
    """
    menu_items = g.conn.execute(text(menu_query), {'user_id': user_id, 'rest_name': rest_name}).fetchall()
    
    # Get the number of reviews, average rating, and detailed reviews
    reviews_query = """
        SELECT COUNT(rw.review_id) AS review_count, ROUND(AVG(rw.rating), 2) AS avg_rating,
               rw.contents, rw.rating, p.name AS reviewer
        FROM Review_Writes rw
        JOIN Review_has rh ON rw.review_id = rh.review_id
        JOIN People p ON rw.user_id = p.user_id
        WHERE rh.rest_name = :rest_name
        GROUP BY rw.review_id, p.name
    """
    reviews = g.conn.execute(text(reviews_query), {'rest_name': rest_name}).fetchall()

    # Review statistics
    review_count = len(reviews)
    avg_rating = round(sum([review['rating'] for review in reviews]) / review_count, 2) if review_count > 0 else None

    return render_template('restaurant_details.html', restaurant=restaurant, menu_items=menu_items, 
                           distance=distance, review_count=review_count, avg_rating=avg_rating, reviews=reviews)

# Filter restaurants based on allergens, distance, diet type, and reviews
@app.route('/filter_restaurants', methods=['GET', 'POST'])
def filter_restaurants():
    user_id = session.get('user_id')
    user_location_query = "SELECT latitude, longitude FROM People WHERE user_id = :user_id"
    user_location = g.conn.execute(text(user_location_query), {'user_id': user_id}).fetchone()
    
    # Collect filter criteria from the form
    max_distance = float(request.form.get('max_distance', 10))
    diet_type = request.form.get('diet_type', '%')
    min_reviews = int(request.form.get('min_reviews', 0))
    
    # Filter by allergens
    allergen_query = """
        SELECT DISTINCT r.rest_name, r.loc, r.latitude, r.longitude, r.cuisineType, r.diet_name,
            COUNT(rw.review_id) AS review_count, ROUND(AVG(rw.rating), 2) AS avg_rating
        FROM Restaurant_Creates r
        LEFT JOIN Menu_Item_Includes mii ON r.rest_name = mii.rest_name
        LEFT JOIN Menu_Item_Contains mic ON mii.item_name = mic.item_name
        LEFT JOIN Customer_Allergens ca ON mii.ing_name = ca.allergen AND ca.user_id = :user_id
        LEFT JOIN Review_has rh ON rh.rest_name = r.rest_name
        LEFT JOIN Review_Writes rw ON rw.review_id = rh.review_id
        WHERE ca.allergen IS NULL
          AND r.diet_name ILIKE :diet_type
        GROUP BY r.rest_name, r.loc, r.latitude, r.longitude, r.cuisineType, r.diet_name
        HAVING COUNT(rw.review_id) >= :min_reviews
    """
    filtered_restaurants = []
    for row in g.conn.execute(text(allergen_query), {'user_id': user_id, 'diet_type': f"%{diet_type}%", 'min_reviews': min_reviews}):
        distance = calculate_distance(user_location['latitude'], user_location['longitude'], row['latitude'], row['longitude'])
        if distance <= max_distance:
            filtered_restaurants.append({**row, 'distance': distance})

    return render_template('filtered_results.html', filtered_restaurants=filtered_restaurants)

# Helper function to get all restaurants
def get_all_restaurants():
    query = "SELECT rest_name, loc FROM Restaurant_Creates"
    return g.conn.execute(text(query)).fetchall()

# Helper function to get saved restaurants for a user
def get_saved_restaurants(user_id):
    query = "SELECT rest_name FROM Customer_Saves WHERE user_id = :user_id"
    return g.conn.execute(text(query), {'user_id': user_id}).fetchall()

# Helper function to get all reviews
def get_all_reviews():
    query = """
        SELECT rw.contents, rw.rating, rw.dt, rh.rest_name
        FROM Review_Writes rw
        JOIN Review_has rh ON rw.review_id = rh.review_id
        ORDER BY rw.dt DESC
    """
    return g.conn.execute(text(query)).fetchall()

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

