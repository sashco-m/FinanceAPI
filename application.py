import os

from cs50 import SQL
from flask import Flask, flash, jsonify, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash

#the date of purchase/sale
from datetime import datetime

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Ensure responses aren't cached
@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")

#taken from https://stackoverflow.com/questions/30926840/how-to-check-change-between-two-values-in-percent
#easily find percent change between stonks
def get_change(current, previous):
    if current == previous:
        return 0
    try:
        if current>previous:
            return (abs(current - previous) / previous) * 100.0
        else:
            return -(abs(current - previous) / previous) * 100.0
    except ZeroDivisionError:
        return float('inf')


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""
    portfolio=db.execute("SELECT * FROM purchase WHERE owner_id=:owner_id",owner_id=session["user_id"])
    #add to the portfolio array
    i=0
    for stocks in portfolio:
        portfolio[i].update({"current_price": lookup(stocks["symbol"])["price"],"change":round(get_change(lookup(stocks["symbol"])["price"],stocks["purchase_price"]),2)})
        i+=1

    cash=round(db.execute("SELECT cash FROM users WHERE id=:userId",userId=session["user_id"])[0]["cash"],2)
    assets=cash

    for stocks in portfolio:
        assets+=stocks["current_price"]*stocks["amount"]

    assets=round(assets,2)
    return render_template("index.html",portfolio=portfolio,cash=cash,assets=assets)


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    price=""
    name=""
    symbol=""
    userCash=""
    shares=""
    success=False

    if request.method == "POST":

        #check if it exists
        if not lookup(request.form.get("symbol")):
            return apology("Invalid Symbol")

        if not float(request.form.get("shares")).is_integer() or int(request.form.get("shares"))<1:
            return apology("Enter a positive integer")


        userCash= db.execute("SELECT cash FROM users WHERE id=:userId",userId=session["user_id"])
        #print(userCash[0]["cash"])
        price = lookup(request.form.get("symbol"))["price"]
        shares= int(request.form.get("shares"))

        if price*shares > userCash[0]["cash"]:
            return apology("Insufficient Funds")

        name = lookup(request.form.get("symbol"))["name"]
        symbol = lookup(request.form.get("symbol"))["symbol"]
        newCash = float(userCash[0]["cash"]) - float(price) * shares



        currentHoldings=db.execute("SELECT amount FROM purchase WHERE owner_id=:user_id AND symbol=:symbol",user_id=session["user_id"],symbol=symbol)
        #checks if the listing exists
        if currentHoldings:
            db.execute("UPDATE purchase SET amount = :newAmount WHERE symbol=:symbol AND owner_id=:user_id",symbol=symbol,user_id=session["user_id"],newAmount=currentHoldings[0]['amount']+shares)
        else:
            db.execute("INSERT INTO purchase(owner_id,symbol,amount,purchase_price,purchase_date) VALUES (?,?,?,?,?)",session["user_id"],symbol,shares,price,datetime.now())

        db.execute("UPDATE users SET cash = :newCash WHERE id=:user_id",newCash=newCash,user_id=session["user_id"])

        db.execute("INSERT INTO history(owner_id,symbol,amount,price,date,type) VALUES (?,?,?,?,?,?)",session["user_id"],symbol,shares,price,datetime.now(),"purchase")

        success=True


        return render_template("buy.html",price=price,symbol=symbol,amount=shares,success=success,name=name)

    else:
        return render_template("buy.html",price=price,symbol=symbol,amount=shares,success=success,name=name)


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    if request.method=="GET":
        portfolio=db.execute("SELECT * FROM history WHERE owner_id=:owner_id ORDER BY date DESC",owner_id=session["user_id"])
        return render_template("history.html",portfolio=portfolio)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = :username",
                          username=request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""
    price=""
    name=""
    symbol=""
    success=False

    if request.method == "POST":

        #check if it exists
        if not lookup(request.form.get("symbol")):
            return apology("Invalid Symbol")

        price = lookup(request.form.get("symbol"))["price"]
        name = lookup(request.form.get("symbol"))["name"]
        symbol = lookup(request.form.get("symbol"))["symbol"]
        success=True

    return render_template("quote.html",price=price,name=name,symbol=symbol,success=success)


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    #if they submit the form
    if request.method == "POST":

        password=request.form.get("password")
        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403) #change out all of these apologies

        # Ensure password was submitted
        elif not password:
            return apology("must provide password", 403)

        # Ensure passwords are the same
        elif request.form.get("password-confirm") != password:
            return apology("confirm password was not identical", 403)

        #checks if the username already exists
        elif db.execute("SELECT * FROM users WHERE username = :username", username=request.form.get("username")):
            return apology("username must be unique",403)

        #special addition of password requirements
        if len(password) < 8:
            return apology("Password must be at least 8 characters",403)

        #borrowed pythonic method of string search from https://stackoverflow.com/questions/5188792/how-to-check-a-string-for-specific-characters
        chars = set('!@#$%^&*)(`~\|][}{?/><')
        if not any((c in chars) for c in password):
            return apology("Password does not contain special character",403)

        #pythonic expression from https://stackoverflow.com/questions/19859282/check-if-a-string-contains-a-number
        hasNumber=any(i.isdigit() for i in password)

        if not hasNumber:
            return apology("Password does not contain a number",403)


        db.execute("INSERT INTO users (username,hash) VALUES (:username,:hash)",username=request.form.get("username"),hash=generate_password_hash(request.form.get("password")))

        rows = db.execute("SELECT * FROM users WHERE username = :username",
                          username=request.form.get("username"))

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    else:
        return render_template("register.html")

@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    price=""
    name=""
    symbol=""
    userCash=""
    shares=""
    success=False
    portfolio=db.execute("SELECT * FROM purchase WHERE owner_id=:owner_id",owner_id=session["user_id"])


    if request.method=="POST":
        if not request.form.get("symbol"):
            return apology("Please select a stock")
        elif not request.form.get("shares"):
            return apology("Select number of stocks to sell")

        shares= int(request.form.get("shares"))
        ownedStock=db.execute("SELECT symbol FROM purchase WHERE owner_id=:user_id",user_id=session["user_id"])


        owned=False

        for stocks in ownedStock:
            if stocks["symbol"]==request.form.get("symbol"):
                owned=True

        symbol=request.form.get("symbol")


        if not owned:
            return apology("You do not own this stock")

        amount=db.execute("SELECT amount FROM purchase WHERE owner_id=:user_id AND symbol=:symbol",user_id=session["user_id"],symbol=symbol)

        if shares>int(amount[0]["amount"]):
            return apology("You do not own that many shares")

        symbol = lookup(request.form.get("symbol"))["symbol"]
        #subtract the stock from purchase, remove the row if it is zero
        #add row to sell, dont bother congregating rows
        #add to history
        userCash= db.execute("SELECT cash FROM users WHERE id=:userId",userId=session["user_id"])
        price = int(lookup(request.form.get("symbol"))["price"])
        name = lookup(request.form.get("symbol"))["name"]

        if not shares-int(amount[0]["amount"])==0:
            db.execute("UPDATE purchase SET amount = :newAmount WHERE symbol=:symbol AND owner_id=:user_id",symbol=symbol,user_id=session["user_id"],newAmount=int(amount[0]["amount"])-int(request.form.get("shares")))
        else:
            db.execute("DELETE FROM purchase WHERE symbol=:symbol AND owner_id=:user_id",symbol=symbol,user_id=session["user_id"])

        db.execute("INSERT INTO sale(owner_id,symbol,amount,sell_price,sell_date) VALUES (?,?,?,?,?)",session["user_id"],symbol,shares,price,datetime.now())
        db.execute("INSERT INTO history(owner_id,symbol,amount,price,date,type) VALUES (?,?,?,?,?,?)",session["user_id"],symbol,shares,price,datetime.now(),"sale")
        succes=True

        print(userCash)
        print(shares)
        print(price)
        #update money
        db.execute("UPDATE users SET cash = :newCash WHERE id=:user_id",user_id=session["user_id"],newCash=userCash[0]["cash"]+shares*price)
        portfolio=db.execute("SELECT * FROM purchase WHERE owner_id=:owner_id",owner_id=session["user_id"])


        return render_template("sell.html",price=price,symbol=symbol,amount=shares,success=success,name=name,portfolio=portfolio)

    else:
        return render_template("sell.html",price=price,symbol=symbol,amount=shares,success=success,name=name,portfolio=portfolio)

def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)
