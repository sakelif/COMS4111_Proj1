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
                allergens = request.form['allergens'].split(',')  # Get allergens from input

                query = """
                    INSERT INTO People (user_id, name, password, employee_id, photo, latitude, longitude)
                    VALUES (:user_id, :username, :password, FALSE, :photo, :latitude, :longitude)
                """
                g.conn.execute(text(query), {
                    'user_id': user_id, 'username': username, 'password': hashed_password,
                    'photo': photo, 'latitude': latitude, 'longitude': longitude
                })

                # Insert allergens into Customer_Allergens table
                for allergen in allergens:
                    if allergen.strip():
                        allergen_query = "INSERT INTO Customer_Allergens (user_id, allergen) VALUES (:user_id, :allergen)"
                        g.conn.execute(text(allergen_query), {'user_id': user_id, 'allergen': allergen.strip()})

                flash('Customer profile created successfully')
        except Exception as e:
            print("Registration Error:", e)
            flash('Error during registration')

        return redirect(url_for('login'))
    return render_template('register.html')


# Helper function to get unique cuisine types
def get_unique_cuisines():
    query = "SELECT DISTINCT cuisineType FROM Restaurant_Creates WHERE cuisineType IS NOT NULL"
    result = g.conn.execute(text(query)).fetchall()
    print(result)  # To verify the result structure
    return [row[0] for row in result]  # Access the single column by index

# Display allergens in the customer dashboard
@app.route('/customer_dashboard')
def customer_dashboard():
    user_id = session.get('user_id')
    
    # Fetch saved restaurants for the customer
    saved_restaurants = get_saved_restaurants(user_id)
    
    # Fetch allergens for the customer
    allergen_query = "SELECT allergen FROM Customer_Allergens WHERE user_id = :user_id"
    allergens = [row['allergen'] for row in g.conn.execute(text(allergen_query), {'user_id': user_id}).fetchall()]

    # Fetch unique cuisines for filtering options
    unique_cuisines = get_unique_cuisines()

    return render_template('customer_dashboard.html', saved_restaurants=saved_restaurants, allergens=allergens, unique_cuisines=unique_cuisines)

# Route to add an allergen
@app.route('/add_allergen', methods=['POST'])
def add_allergen():
    user_id = session.get('user_id')
    new_allergen = request.form.get('new_allergen')
    
    if new_allergen:
        try:
            query = "INSERT INTO Customer_Allergens (user_id, allergen) VALUES (:user_id, :allergen)"
            g.conn.execute(text(query), {'user_id': user_id, 'allergen': new_allergen.strip()})
            flash('Allergen added successfully')
        except Exception as e:
            print("Error adding allergen:", e)
            flash('Error adding allergen')
    
    return redirect(url_for('customer_dashboard'))

# Route to delete an allergen
@app.route('/delete_allergen', methods=['POST'])
def delete_allergen():
    user_id = session.get('user_id')
    allergen = request.form.get('allergen')
    
    try:
        query = "DELETE FROM Customer_Allergens WHERE user_id = :user_id AND allergen = :allergen"
        g.conn.execute(text(query), {'user_id': user_id, 'allergen': allergen})
        flash('Allergen deleted successfully')
    except Exception as e:
        print("Error deleting allergen:", e)
        flash('Error deleting allergen')
    
    return redirect(url_for('customer_dashboard'))

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

    return render_template('restaurant_details.html', restaurant=restaurant, menu_items=menu_items, distance=distance, review_count=review_count, avg_rating=avg_rating, reviews=reviews)

# Filter restaurants based on allergens, distance, diet type, reviews, and multiple cuisine types
@app.route('/filter_restaurants', methods=['POST'])
def filter_restaurants():
    user_id = session.get('user_id')
    max_distance = request.form.get('max_distance')
    diet_type = request.form.get('diet_type')
    min_reviews = request.form.get('min_reviews', 0)
    selected_cuisines = request.form.getlist('cuisine_types')  # List of selected cuisine types

    # Base query for filtering restaurants
    query = """
        SELECT r.rest_name, r.loc, r.latitude, r.longitude, r.cuisineType, r.diet_name,
               COUNT(rw.review_id) AS review_count, ROUND(AVG(rw.rating), 2) AS avg_rating
        FROM Restaurant_Creates r
        LEFT JOIN Review_has rh ON rh.rest_name = r.rest_name
        LEFT JOIN Review_Writes rw ON rw.review_id = rh.review_id
        WHERE 1=1
    """
    params = {}

    # Filter by distance if max_distance is specified
    if max_distance:
        user_location_query = "SELECT latitude, longitude FROM People WHERE user_id = :user_id"
        user_location = g.conn.execute(text(user_location_query), {'user_id': user_id}).fetchone()
        if user_location:
            user_lat, user_lon = user_location.latitude, user_location.longitude
            distance_query = """
                AND (3959 * acos(
                    cos(radians(:user_lat)) * cos(radians(r.latitude)) *
                    cos(radians(r.longitude) - radians(:user_lon)) +
                    sin(radians(:user_lat)) * sin(radians(r.latitude))
                )) <= :max_distance
            """
            query += distance_query
            params.update({'user_lat': user_lat, 'user_lon': user_lon, 'max_distance': float(max_distance)})

    # Filter by diet type if specified
    if diet_type:
        query += " AND r.diet_name ILIKE :diet_type"
        params['diet_type'] = f"%{diet_type}%"

    # Filter by minimum number of reviews
    query += " GROUP BY r.rest_name, r.loc, r.latitude, r.longitude, r.cuisineType, r.diet_name"
    query += " HAVING COUNT(rw.review_id) >= :min_reviews"
    params['min_reviews'] = int(min_reviews)

    # Filter by cuisine types if specified
    if selected_cuisines:
        cuisine_conditions = []
        for cuisine in selected_cuisines:
            cuisine_conditions.append("r.cuisineType ILIKE :cuisine_" + cuisine)
            params["cuisine_" + cuisine] = f"%{cuisine}%"
        query += " AND (" + " OR ".join(cuisine_conditions) + ")"

    restaurants = g.conn.execute(text(query), params).fetchall()

    return render_template('customer_dashboard.html', filtered_restaurants=restaurants)

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

