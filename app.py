import os
import pathlib
import requests
from google_auth_oauthlib.flow import Flow
import ssl
from google.oauth2 import id_token
from google_auth_oauthlib.flow import Flow
from pip._vendor import cachecontrol
import google.auth.transport.requests
from flask import (
    Flask, flash, render_template, abort,
    redirect, request, session, url_for)
from flask_pymongo import PyMongo
from bson.objectid import ObjectId
from werkzeug.security import generate_password_hash, check_password_hash
if os.path.exists("env.py"):
    import env


# Create instance of Flask
app = Flask(__name__)

app.config["MONGO_DBNAME"] = os.environ.get("MONGO_DBNAME")
app.config["MONGO_URI"] = os.environ.get("MONGO_URI")
app.secret_key = os.environ.get("SECRET_KEY")


# MongoDB properly communicating with Flask
mongo = PyMongo(app, ssl=True, ssl_cert_reqs=ssl.CERT_NONE)


# Env variable for test purposes delete for production!
os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"


GOOGLE_CLIENT_ID = "796970139365-ljhesj8bq7uur7dg66d5m708q9vpucmn.apps.googleusercontent.com"
client_secrets_file = os.path.join(
    pathlib.Path(__file__).parent, "client_secret.json")

flow = Flow.from_client_secrets_file(
    client_secrets_file=client_secrets_file,
    # Scopes = Which APIS is going to have access
    scopes=["https://www.googleapis.com/auth/userinfo.profile",
            "https://www.googleapis.com/auth/userinfo.email", "openid"],
    redirect_uri="http://127.0.0.1:5000/callback"
)


def login_is_required(function):
    def wrapper(*args, **kwargs):
        if "google_id" not in session:
            return abort(401)
        else:
            return function()
    return wrapper


@app.route("/login")
def login():
    # State is an Oath functionality, returns a random number
    authorization_url, state = flow.authorization_url()
    session["state"] = state
    return redirect(authorization_url)


@app.route("/callback")
def callback():
    # Arguments received
    flow.fetch_token(authorization_response=request.url)

    # Check if what we saved on the session is the same so we can protect it
    if not session["state"] == request.args["state"]:
        abort(500)

    # Credentials will be saved
    credentials = flow.credentials
    request_session = requests.session()
    cached_session = cachecontrol.CacheControl(request_session)
    token_request = google.auth.transport.requests.Request(
        session=cached_session)

    # Transform text into the id token
    id_info = id_token.verify_oauth2_token(
        id_token=credentials._id_token,
        request=token_request,
        audience=GOOGLE_CLIENT_ID
    )

    existing_user = mongo.db.users.find_one({"user_id": id_info.get("sub")})
    if not existing_user:
        print("User does not exist, creating user")
        mongo.db.users.insert_one({
            "user_id": id_info.get("sub"),
            "fname": id_info.get("given_name"),
            "list": [
                {
                    "_id": ObjectId(),
                    "value": "My first thing",
                }
            ],
        })

    session["google_id"] = id_info.get("sub")
    session["name"] = id_info.get("name")
    return redirect("/shopping_list")


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/shopping_list")
@login_is_required
def shopping_list():
    user = mongo.db.users.find_one({"user_id": session["google_id"]})
    return render_template("shopping_list.html", user=user)


@app.route("/add_item", methods=["POST"])
def add_item():
    if request.method == "POST":
        # collect the add-comment form data and write to the DB
        new_item = {
            "_id": ObjectId(),
            "value": request.form.get("new_item"),
        }

        mongo.db.users.update_one(
            {"user_id": session["google_id"]},
            {"$push": {"list": new_item}})

        return redirect("/shopping_list")


@app.route("/delete_item/<item_id>", methods=["POST"])
def delete_item(item_id):
    mongo.db.users.update_one(
        {"user_id": session["google_id"]},
        {"$pull": {"list": {"_id": ObjectId(item_id)}}})

    return redirect("/shopping_list")


@app.route("/delete_all_items", methods=["POST"])
def delete_all_items():
    mongo.db.users.update(
        {"user_id": session["google_id"]},
        {"$set": {"list": []}
    })

    return redirect("/shopping_list")


# Tell the app how to run the application
if __name__ == "__main__":
    app.run()
