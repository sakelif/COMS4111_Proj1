import os
import random
from math import radians, sin, cos, sqrt, atan2
from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool
from flask import Flask, request, render_template, g, redirect, url_for, flash, session
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

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

        # Fetch user details
        query = "SELECT user_id, employee_id AS is_admin, password FROM People WHERE name = :username"
        result = g.conn.execute(text(query), {'username': username}).fetchone()

        # Validate username existence
        if not result:
            flash('Username does not exist')
            return redirect(url_for('login'))

        stored_password = result['password']

        # Check password (plain text or hashed)
        is_valid_password = (
            check_password_hash(stored_password, password)  # For hashed passwords
            or stored_password == password  # For plain-text passwords
        )

        if not is_valid_password:
            flash('Invalid password')
            return redirect(url_for('login'))

        # Set session variables on successful login
        session['logged_in'] = True
        session['user_id'] = result['user_id']
        session['is_admin'] = result['is_admin']
        return redirect(url_for('home'))

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
        is_admin = request.form['is_admin'] == 'admin'  # Check if admin
        hashed_password = generate_password_hash(password)  # Always hash new passwords
        user_id = generate_random_user_id()

        try:
            # Registration logic for admins
            if is_admin:
                query = """
                    INSERT INTO People (user_id, name, password, employee_id) 
                    VALUES (:user_id, :username, :password, TRUE)
                """
                g.conn.execute(text(query), {
                    'user_id': user_id,
                    'username': username,
                    'password': hashed_password
                })
                flash('Admin profile created successfully')
            else:  # Registration logic for customers
                latitude = request.form['latitude']
                longitude = request.form['longitude']
                photo = request.form['photo']
                allergens = request.form['allergens'].split(',')

                query = """
                    INSERT INTO People (user_id, name, password, employee_id, photo, latitude, longitude)
                    VALUES (:user_id, :username, :password, FALSE, :photo, :latitude, :longitude)
                """
                g.conn.execute(text(query), {
                    'user_id': user_id,
                    'username': username,
                    'password': hashed_password,
                    'photo': photo,
                    'latitude': latitude,
                    'longitude': longitude
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

@app.route('/delete_account', methods=['POST'])
def delete_account():
    user_id = session.get('user_id')

    if not user_id:
        flash('No user logged in')
        return redirect(url_for('home'))

    try:
        # Step 1: Set user_id in Review_Writes to NULL for the deleted user's reviews
        update_reviews_query = """
            UPDATE Review_Writes 
            SET user_id = NULL 
            WHERE user_id = :user_id
        """
        g.conn.execute(text(update_reviews_query), {'user_id': user_id})

        # Step 2: Delete associated data from related tables (Customer_Allergens and Customer_Saves)
        delete_allergens_query = """
            DELETE FROM Customer_Allergens 
            WHERE user_id = :user_id
        """
        g.conn.execute(text(delete_allergens_query), {'user_id': user_id})

        delete_saved_restaurants_query = """
            DELETE FROM Customer_Saves 
            WHERE user_id = :user_id
        """
        g.conn.execute(text(delete_saved_restaurants_query), {'user_id': user_id})

        # Step 3: Delete the user from the People table
        delete_user_query = """
            DELETE FROM People 
            WHERE user_id = :user_id
        """
        g.conn.execute(text(delete_user_query), {'user_id': user_id})

        # Step 4: Clear session and log the user out
        session.clear()
        flash('Account deleted successfully')

    except Exception as e:
        print("Error deleting account:", e)
        flash('Error deleting account. Please try again later.')

    return redirect(url_for('home'))

# Helper function to get unique cuisine types
def get_unique_cuisines():
    query = "SELECT DISTINCT cuisineType FROM Restaurant_Creates WHERE cuisineType IS NOT NULL"
    result = g.conn.execute(text(query)).fetchall()
    print(result)  # To verify the result structure
    return [row[0] for row in result]  # Access the single column by index

@app.route('/admin_dashboard', methods=['GET', 'POST'])
def admin_dashboard():
    if not session.get('is_admin'):
        return redirect(url_for('home'))

    # Handle restaurant creation
    if request.method == 'POST' and 'create_restaurant' in request.form:
        rest_name = request.form['rest_name'].strip()
        loc = request.form['loc'].strip()
        latitude = request.form['latitude'].strip()
        longitude = request.form['longitude'].strip()
        cuisine_type = ', '.join([c.strip() for c in request.form['cuisineType'].split(',')])
        diet_name = ', '.join([d.strip() for d in request.form['diet_name'].split(',')])
        user_id = session.get('user_id')

        try:
            query = """
                INSERT INTO Restaurant_Creates (rest_name, loc, latitude, longitude, cuisineType, diet_name, user_id)
                VALUES (:rest_name, :loc, :latitude, :longitude, :cuisineType, :diet_name, :user_id)
            """
            g.conn.execute(text(query), {
                'rest_name': rest_name,
                'loc': loc,
                'latitude': float(latitude),
                'longitude': float(longitude),
                'cuisineType': cuisine_type,
                'diet_name': diet_name,
                'user_id': user_id
            })
            flash('Restaurant created successfully')
        except Exception as e:
            print("Error creating restaurant:", e)
            flash('Error creating restaurant')

    # Handle menu item and ingredient addition
    if request.method == 'POST' and 'add_menu_item' in request.form:
        menu_restaurant = request.form['menu_restaurant'].strip()
        item_name = request.form['item_name'].strip()
        price = request.form['price'].strip()
        ingredients = [ingredient.strip() for ingredient in request.form['ingredients'].split(',')]

        try:
            # Insert menu item into Menu_Item_Contains
            menu_item_query = """
                INSERT INTO Menu_Item_Contains (item_name, price, rest_name)
                VALUES (:item_name, :price, :rest_name)
            """
            g.conn.execute(text(menu_item_query), {
                'item_name': item_name,
                'price': float(price),
                'rest_name': menu_restaurant
            })

            # Insert ingredients into Menu_Item_Includes
            for ingredient in ingredients:
                ingredient_query = """
                    INSERT INTO Menu_Item_Includes (item_name, ing_name)
                    VALUES (:item_name, :ing_name)
                """
                g.conn.execute(text(ingredient_query), {
                    'item_name': item_name,
                    'ing_name': ingredient
                })
            flash('Menu item and ingredients added successfully')
        except Exception as e:
            print("Error adding menu item or ingredients:", e)
            flash('Error adding menu item or ingredients')

    # Fetch restaurants created by the admin
    restaurant_query = "SELECT rest_name FROM Restaurant_Creates WHERE user_id = :user_id"
    restaurants = g.conn.execute(text(restaurant_query), {'user_id': session['user_id']}).fetchall()
    restaurant_names = [row['rest_name'] for row in restaurants]

    # Debugging Logs
    print(f"Restaurants created by admin: {restaurant_names}")

    return render_template('admin_dashboard.html', restaurant_names=restaurant_names)

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

@app.route('/restaurant/<rest_name>', methods=['GET', 'POST'])
def restaurant_details(rest_name):
    user_id = session.get('user_id')

    # Handle form submissions
    if request.method == 'POST':
        action = request.form.get('action')

        # Save restaurant
        if action == 'save_restaurant':
            try:
                query = """
                    INSERT INTO Customer_Saves (user_id, rest_name)
                    VALUES (:user_id, :rest_name)
                    ON CONFLICT DO NOTHING
                """
                g.conn.execute(text(query), {'user_id': user_id, 'rest_name': rest_name})
                flash(f'Restaurant "{rest_name}" saved successfully.')
            except Exception as e:
                print(f"Error saving restaurant: {e}")
                flash('Error saving restaurant.')
            return redirect(url_for('restaurant_details', rest_name=rest_name))

        # Unsave restaurant
        elif action == 'unsave_restaurant':
            try:
                query = """
                    DELETE FROM Customer_Saves
                    WHERE user_id = :user_id AND rest_name = :rest_name
                """
                g.conn.execute(text(query), {'user_id': user_id, 'rest_name': rest_name})
                flash(f'Restaurant "{rest_name}" unsaved successfully.')
            except Exception as e:
                print(f"Error unsaving restaurant: {e}")
                flash('Error unsaving restaurant.')
            return redirect(url_for('restaurant_details', rest_name=rest_name))

        # Submit a review
        elif request.form.get('review_content') and request.form.get('rating'):
            contents = request.form['review_content']
            rating = int(request.form['rating'])
            try:
                # Generate a unique review_id for the new review
                review_id_query = "SELECT COALESCE(MAX(review_id), 0) + 1 AS new_review_id FROM Review_Writes"
                new_review_id = g.conn.execute(text(review_id_query)).fetchone()['new_review_id']

                # Insert the new review into Review_Writes table
                review_query = """
                    INSERT INTO Review_Writes (review_id, contents, rating, dt, user_id) 
                    VALUES (:review_id, :contents, :rating, CURRENT_DATE, :user_id)
                """
                g.conn.execute(text(review_query), {
                    'review_id': new_review_id,
                    'contents': contents,
                    'rating': rating,
                    'user_id': user_id
                })

                # Link the review to the restaurant in the Review_has table
                link_query = "INSERT INTO Review_has (review_id, rest_name) VALUES (:review_id, :rest_name)"
                g.conn.execute(text(link_query), {'review_id': new_review_id, 'rest_name': rest_name})

                flash('Review submitted successfully')
            except Exception as e:
                print(f"Error submitting review: {e}")
                flash('Error submitting review.')
            return redirect(url_for('restaurant_details', rest_name=rest_name))

        # Invalid action
        else:
            flash('Invalid action submitted.')
            return redirect(url_for('restaurant_details', rest_name=rest_name))

    # Fetch restaurant details
    query = """
        SELECT rest_name AS name, loc AS location, cuisineType AS cuisine,
               diet_name AS diet, latitude, longitude
        FROM Restaurant_Creates
        WHERE rest_name = :rest_name
    """
    restaurant = g.conn.execute(text(query), {'rest_name': rest_name}).fetchone()

    cuisine_types = restaurant['cuisine'].split(', ') if restaurant['cuisine'] else []

    # Check if restaurant is saved
    saved_query = """
        SELECT COUNT(*) AS count
        FROM Customer_Saves
        WHERE user_id = :user_id AND rest_name = :rest_name
    """
    is_saved = g.conn.execute(text(saved_query), {'user_id': user_id, 'rest_name': rest_name}).fetchone()['count'] > 0

    # Calculate distance
    user_location_query = "SELECT latitude, longitude FROM People WHERE user_id = :user_id"
    user_location = g.conn.execute(text(user_location_query), {'user_id': user_id}).fetchone()

    distance = None
    if user_location:
        distance = calculate_distance(user_location.latitude, user_location.longitude, restaurant.latitude, restaurant.longitude)

    # Fetch reviews
    reviews_query = """
        SELECT COALESCE(p.name, 'Anonymous') AS name, rw.rating, rw.contents, rw.dt
        FROM Review_Writes rw
        LEFT JOIN People p ON rw.user_id = p.user_id
        JOIN Review_has rh ON rw.review_id = rh.review_id
        WHERE rh.rest_name = :rest_name
        ORDER BY rw.dt DESC
    """
    reviews = g.conn.execute(text(reviews_query), {'rest_name': rest_name}).fetchall()
    print(f"Fetched reviews for {rest_name}: {reviews}")

    # Fetch menu items
    menu_query = """
        SELECT mic.item_name, mic.price, 
               ARRAY_AGG(DISTINCT mii.ing_name) AS ingredients,
               bool_or(mii.ing_name IN (SELECT allergen FROM Customer_Allergens WHERE user_id = :user_id)) AS contains_allergen
        FROM Menu_Item_Contains mic
        JOIN Menu_Item_Includes mii ON mic.item_name = mii.item_name
        WHERE mic.rest_name = :rest_name
        GROUP BY mic.item_name, mic.price
    """
    menu_items = g.conn.execute(text(menu_query), {'rest_name': rest_name, 'user_id': user_id}).fetchall()

    # Normalize allergens to strings for comparison
    allergen_query = "SELECT allergen FROM Customer_Allergens WHERE user_id = :user_id"
    allergens = [row['allergen'].strip().lower() for row in g.conn.execute(text(allergen_query), {'user_id': user_id}).fetchall()]

    return render_template(
        'restaurant_details.html',
        restaurant=restaurant,
        cuisine_types=cuisine_types,
        distance=distance,
        reviews=reviews,
        menu_items=menu_items,
        is_saved=is_saved,
        allergens=allergens
    )

@app.route('/filter_restaurants', methods=['POST'])
def filter_restaurants():
    user_id = session.get('user_id')
    max_distance = request.form.get('max_distance')
    diet_type = request.form.get('diet_type')
    min_reviews = request.form.get('min_reviews', 0) or 0
    selected_cuisines = request.form.getlist('cuisine_types')

    # Base query
    query = """
        SELECT r.rest_name, r.loc, r.latitude, r.longitude, r.cuisineType, r.diet_name,
               COUNT(rw.review_id) AS review_count, COALESCE(ROUND(AVG(rw.rating), 2), 0) AS avg_rating
        FROM Restaurant_Creates r
        LEFT JOIN Review_has rh ON rh.rest_name = r.rest_name
        LEFT JOIN Review_Writes rw ON rw.review_id = rh.review_id
        WHERE 1=1
    """
    params = {}

    # Add distance filtering
    if max_distance:
        user_location_query = "SELECT latitude, longitude FROM People WHERE user_id = :user_id"
        user_location = g.conn.execute(text(user_location_query), {'user_id': user_id}).fetchone()
        if user_location:
            user_lat, user_lon = user_location.latitude, user_location.longitude
            query += """
                AND (3959 * acos(
                    cos(radians(:user_lat)) * cos(radians(r.latitude)) *
                    cos(radians(r.longitude) - radians(:user_lon)) +
                    sin(radians(:user_lat)) * sin(radians(r.latitude))
                )) <= :max_distance
            """
            params.update({'user_lat': user_lat, 'user_lon': user_lon, 'max_distance': float(max_distance)})

    # Add diet type filtering
    if diet_type:
        query += " AND LOWER(r.diet_name) ILIKE :diet_type"
        params['diet_type'] = f"%{diet_type.lower()}%"

    # Add cuisine filtering
    if selected_cuisines:
        query += " AND (" + " OR ".join(
            [f"LOWER(r.cuisineType) ILIKE :cuisine_{i}" for i in range(len(selected_cuisines))]
        ) + ")"
        params.update({f"cuisine_{i}": f"%{cuisine.lower()}%" for i, cuisine in enumerate(selected_cuisines)})

    # Group and filter
    query += """
        GROUP BY r.rest_name, r.loc, r.latitude, r.longitude, r.cuisineType, r.diet_name
        HAVING COUNT(rw.review_id) >= :min_reviews OR :min_reviews = 0
    """
    params['min_reviews'] = int(min_reviews)

    # Execute and render results
    restaurants = g.conn.execute(text(query), params).fetchall()
    return render_template('search_results.html', results=restaurants)

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
