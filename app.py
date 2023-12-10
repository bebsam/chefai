from flask import Flask, jsonify, render_template, request, redirect, url_for, session
from flask import Flask, request, redirect, url_for, send_from_directory
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename  # Import secure_filename from werkzeug.utils
import pymongo
import os
import requests
from bson.objectid import ObjectId 
import re
import datetime
import ssl



############################################################

from pymongo import MongoClient
import logging

# Set up basic logging
logging.basicConfig(level=logging.INFO)

# MongoDB Atlas connection string with your credentials
mongo_conn_string = "mongodb+srv://recipemongo:recipegenerator@recipecluster.bwicxlj.mongodb.net/"

try:
    # Connect to the MongoDB client
    client = MongoClient(mongo_conn_string)
    
    # Select your database
    db = client["recipe_db"]  # Replace with your actual database name if different
    
    # Select your collection
    collection = db["recipes"]  # Replace with your actual collection name if different
    
    # Example operation: Insert a diagnostic document
    insert_result = collection.insert_one({"diagnostic_test": "success"})
    logging.info(f"Inserted diagnostic document with id: {insert_result.inserted_id}")
except Exception as e:
    logging.error(f"An error occurred: {e}")


############################################################


UPLOAD_FOLDER = 'uploaded_images'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

def calculate_average_rating(ratings):
    if not ratings:
        return 0
    total = sum(float(rating['rating']) for rating in ratings)
    return round(total / len(ratings), 1)


# Register the filter
app.jinja_env.filters['calculate_average_rating'] = calculate_average_rating


# Secret key for sessions
app.secret_key = os.urandom(24)

# Hugging Face API details

# MongoDB connection setup
client = pymongo.MongoClient("mongodb://localhost:27017")
db = client["recipe_db"]
recipes_collection = db["recipes"]
users_collection = db["users"]
recipe_board_collection = db["recipe_board"]

@app.route("/", methods=["GET", "POST"])
def land(): #landing
    if 'user' in session:
        return redirect(url_for('index'))
    return render_template("land.html") #Landing.html

@app.route("/home", methods=["GET", "POST"])
def index():
    if 'user' not in session:
        return redirect(url_for('land')) #landing

    ingredients = None
    recipe = None

    if request.method == "POST":
        ingredients = request.form.get("ingredients")
        if ingredients:
            recipe = query_model(ingredients)

    return render_template("index.html", ingredients=ingredients, recipe=recipe)

def query_model(ingredients):
    # Hugging Face API details
    API_URL = "https://api-inference.huggingface.co/models/Ayesha18/chef-ai"
    headers = {"Authorization": "Bearer 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"}

    payload = {
        "inputs": ingredients,
        "parameters": {
            "max_length": 300,  # Increased max_length for longer outputs
            "num_return_sequences": 1,
            "do_sample": True,
            "temperature": 0.8,
            "top_k": 50,  # Number of highest probability tokens to consider at each step
            "top_p": 0.89,
            "num_beams": 3,
            "no_repeat_ngram_size": 3,
            "early_stopping": True
        }
    }

    try:
        response = requests.post(API_URL, headers=headers, json=payload)
        response.raise_for_status()  # Raises an error for bad HTTP responses
        response_json = response.json()
        generated_text = response_json[0].get("generated_text", "")
    except requests.RequestException as e:
        print(f"API Request Failed: {e}")
        return f"An error occurred: {e}"

    # Insert the recipe into the database and return it
    recipe_data = {
        "ingredients": ingredients,
        "recipe": generated_text,
        "username": session["user"],
        "user_notes": ""
    }
    recipes_collection.insert_one(recipe_data)

    return generated_text



@app.route("/recipe_list")
def recipe_list():
    if 'user' not in session:
        return redirect(url_for('login'))

    recipes = recipes_collection.find({"username": session["user"]})
    return render_template("recipe_list.html", recipes=recipes)

@app.route("/delete_recipe/<recipe_id>", methods=["POST"])
def delete_recipe(recipe_id):
    if 'user' not in session:
        return redirect(url_for('login'))
    try:
        # Remove the recipe from the database based on the recipe_id
        recipes_collection.delete_one({'_id': ObjectId(recipe_id), 'username': session['user']})
    except Exception as e:
        app.logger.error(f"Error deleting recipe: {e}")
        return redirect(url_for('recipe_list'))
    return redirect(url_for('recipe_list'))

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")

        hashed_password = generate_password_hash(password)
        users_collection.insert_one({"username": username, "password": hashed_password})

        return redirect(url_for('login'))
    
    return render_template("register.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")

        user = users_collection.find_one({"username": username})
        
        if user and check_password_hash(user["password"], password):
            session["user"] = user["username"]
            return redirect(url_for('index'))
        else:
            return "Invalid username or password"
    
    return render_template("login.html")

@app.route('/login_as_guest', methods=['GET', 'POST'])
def login_as_guest():
    session['user'] = 'guest' 
    return redirect(url_for('index')) 
@app.route("/submit_to_board/<recipe_id>", methods=["POST"])
def submit_to_board(recipe_id):
    
    username = session.get('user', 'Guest')

    recipe = recipes_collection.find_one({'_id': ObjectId(recipe_id)})
    if not recipe:
        return "Recipe not found", 404

    # Add the recipe data to the recipe_board_collection
    recipe_board_collection.insert_one({
        "title": recipe.get("title", "Untitled Recipe"),
        "ingredients": recipe["ingredients"],
        "recipe": recipe["recipe"],
        "image_url": recipe.get("image_url"),
        "created_at": datetime.datetime.utcnow(),
        "username": username
    })
    
    # Update the 'on_board' flag to True in the original recipe document
    recipes_collection.update_one(
        {'_id': ObjectId(recipe_id)},
        {'$set': {'on_board': True}}
    )

    return redirect(url_for('recipe_board'))

@app.route("/recipe_board")
def recipe_board():
    recipes = recipe_board_collection.find().sort("created_at", pymongo.DESCENDING)
    return render_template("recipe_board.html", recipes=recipes)


@app.route('/remove_from_board/<recipe_id>', methods=['POST'])
def remove_from_board(recipe_id):
    if 'user' not in session:
        return redirect(url_for('login'))

    try:
        # Convert string ID to ObjectId
        object_id = ObjectId(recipe_id)

        # Find the recipe in the recipe_board_collection
        recipe = recipe_board_collection.find_one({'_id': object_id})

        # Check if recipe exists
        if not recipe:
            app.logger.error(f"Recipe not found: {recipe_id}")
            return "Recipe not found", 404

        # Check if the logged-in user is authorized to remove the recipe
        if recipe.get('username') != session['user']:
            app.logger.error(f"User not authorized to remove recipe: {recipe_id}")
            return "User not authorized to remove this recipe", 403  # Use 403 for Forbidden

        # Remove the image URL from the recipe in the recipes_collection
        recipes_collection.update_one(
            {'_id': ObjectId(recipe_id)},
            {'$unset': {'image_url': 1}}
        )

        # Continue with any other necessary logic

        return redirect(url_for('recipe_list'))

    except Exception as e:
        app.logger.error(f"Error removing recipe from board: {e}")
        return "An error occurred", 500










@app.route('/save_note/<recipe_id>', methods=['POST'])
def save_note(recipe_id):
    if 'user' not in session:
        return redirect(url_for('login'))

    user_notes = request.json.get('content', '')

    try:
        recipes_collection.update_one(
            {'_id': ObjectId(recipe_id), 'username': session['user']},
            {'$set': {'user_notes': user_notes}}
        )
        return jsonify(success=True)
    except Exception as e:
        app.logger.error(f"Error saving note: {e}")
        return jsonify(success=False)

@app.route('/delete_note/<recipe_id>', methods=['POST'])
def delete_note(recipe_id):
    if 'user' not in session:
        return redirect(url_for('login'))

    try:
        recipes_collection.update_one(
            {'_id': ObjectId(recipe_id), 'username': session['user']},
            {'$set': {'user_notes': ''}}  # Clear the user notes
        )
        return jsonify(success=True)
    except Exception as e:
        app.logger.error(f"Error deleting note: {e}")
        return jsonify(success=False)


# Ensure the upload folder exists
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/upload_image/<recipe_id>', methods=['POST'])
def upload_image(recipe_id):
    if 'user' not in session:
        return redirect(url_for('login'))

    if 'recipe_image' not in request.files:
        return "No file part in the request", 400

    file = request.files['recipe_image']
    if file.filename == '':
        return "No file selected", 400

    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(file_path)
        image_url = url_for('uploaded_file', filename=filename, _external=True)

        recipes_collection.update_one(
            {'_id': ObjectId(recipe_id), 'username': session['user']},
            {'$set': {'image_url': image_url}}
        )

        return redirect(url_for('recipe_list'))

    return "File type not allowed", 400

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/rate_recipe/<recipe_id>', methods=['POST'])
def rate_recipe(recipe_id):
    rating = int(request.form.get('rating')) 
    comment = request.form.get('comment', '')  # Default to empty string if no comment

    user = session.get('user', 'anonymous')  # Use 'anonymous' for non-logged-in users

    try:
        # Update the recipe with the new rating
        recipe_board_collection.update_one(
            {'_id': ObjectId(recipe_id)},
            {'$push': {'ratings': {'user': user, 'rating': int(rating), 'comment': comment, 'timestamp': datetime.datetime.utcnow()}}}
        )

        # Fetch the updated recipe to recalculate the average rating
        recipe = recipe_board_collection.find_one({'_id': ObjectId(recipe_id)})

        # Calculate average rating
        ratings = recipe.get('ratings', [])
        if ratings:
            avg_rating = sum(r['rating'] for r in ratings) / len(ratings)
        else:
            avg_rating = 0

        # Update the average rating in the database
        recipe_board_collection.update_one(
            {'_id': ObjectId(recipe_id)},
            {'$set': {'avg_rating': avg_rating}}
        )

    except Exception as e:
        app.logger.error(f"Error submitting rating: {e}")
        return "An error occurred", 500

    return redirect(url_for('recipe_board'))


@app.route('/get_ratings/<recipe_id>', methods=['GET'])
def get_ratings(recipe_id):
    try:
        recipe = recipe_board_collection.find_one({'_id': ObjectId(recipe_id)}, {'ratings': 1})
        return jsonify(recipe.get('ratings', []))
    except Exception as e:
        app.logger.error(f"Error fetching ratings: {e}")
        return jsonify([])




@app.route('/logout', methods=['GET', 'POST'])
def logout():
    session.pop('user', None)
    return redirect(url_for('land'))


if __name__ == "__main__":
    app.run(debug=True)
