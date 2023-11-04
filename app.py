from flask import Flask, render_template, request
import requests
import pymongo
from flask import redirect, url_for
from bson import ObjectId  # This is typically how you import ObjectId from pymongo


app = Flask(__name__)

API_URL = "https://api-inference.huggingface.co/models/flax-community/t5-recipe-generation"
API_KEY = "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"

# MongoDB connection setup
client = pymongo.MongoClient("mongodb://localhost:27017/")  # Replace with your MongoDB connection URI
db = client["recipe_db"]  # Replace "recipe_db" with your preferred database name
recipes_collection = db["recipes"]  # Collection for storing recipes

@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        ingredients = request.form.get("ingredients")
        if ingredients:
            output = query_model(ingredients)
            return render_template("index.html", ingredients=ingredients, recipe=output)
    return render_template("index.html")

# Create a route to display the recipe list
@app.route("/recipe_list")
def recipe_list():
    # Retrieve recipes from MongoDB and pass them to the template
    recipes = recipes_collection.find()
    return render_template("recipe_list.html", recipes=recipes)

from flask import redirect, url_for
from bson.objectid import ObjectId  # Correct import statement for ObjectId

@app.route("/delete_recipe/<recipe_id>", methods=["POST"])
def delete_recipe(recipe_id):
    # Logic to delete the recipe from the database using recipe_id
    recipes_collection.delete_one({'_id': ObjectId(recipe_id)})
    # Redirect to the recipe list page after deletion
    return redirect(url_for('recipe_list'))



def query_model(ingredients):
    headers = {"Authorization": f"Bearer {API_KEY}"}
    payload = {
        "inputs": ingredients,
    }
    response = requests.post(API_URL, headers=headers, json=payload)

    # Extract the generated text from the JSON response
    response_json = response.json()
    generated_text = response_json[0].get("generated_text", "")

    # Store the generated recipe in MongoDB
    recipe_data = {"ingredients": ingredients, "recipe": generated_text}
    recipes_collection.insert_one(recipe_data)

    return generated_text  # Return the generated recipe text without "generated text"

if __name__ == "__main__":
    app.run(debug=True)
