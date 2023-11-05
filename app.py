from flask import Flask, render_template, request, redirect, url_for, session
from werkzeug.security import generate_password_hash, check_password_hash
import pymongo
import os
import requests
from bson.objectid import ObjectId 

app = Flask(__name__)

# Secret key for sessions
app.secret_key = os.urandom(24)

API_URL = "https://api-inference.huggingface.co/models/flax-community/t5-recipe-generation"
API_KEY = "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"

# MongoDB connection setup
client = pymongo.MongoClient("mongodb://localhost:27017/")
db = client["recipe_db"]
recipes_collection = db["recipes"]
users_collection = db["users"]

@app.route("/", methods=["GET", "POST"])

def landing():
    if 'user' in session:
        return redirect(url_for('index'))
    return render_template("landing.html")

@app.route("/home", methods=["GET", "POST"])
def index():
    if 'user' not in session:
        return redirect(url_for('landing'))

    ingredients = None
    recipe = None

    if request.method == "POST":
        ingredients = request.form.get("ingredients")
        if ingredients:
            try:
                recipe = query_model(ingredients)
            except Exception as e:
                recipe = f"An error occurred: {e}"

    return render_template("index.html", ingredients=ingredients, recipe=recipe)

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

@app.route('/logout', methods=['GET', 'POST'])
def logout():
    session.pop('user', None)
    return redirect(url_for('landing'))

def query_model(ingredients):
    headers = {"Authorization": f"Bearer {API_KEY}"}
    payload = {"inputs": ingredients}
    response = requests.post(API_URL, headers=headers, json=payload)
    response_json = response.json()
    generated_text = response_json[0].get("generated_text", "")

    recipe_data = {
        "ingredients": ingredients,
        "recipe": generated_text,
        "username": session["user"]
    }
    recipes_collection.insert_one(recipe_data)

    return generated_text

if __name__ == "__main__":
    app.run(debug=True)
