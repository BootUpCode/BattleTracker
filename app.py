import os
import sys
import sqlite3

from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from flask_socketio import SocketIO, send, emit, join_room, leave_room
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import error, login_required

# Configure application
app = Flask(__name__)
socketio = SocketIO(app)

# Configure database name
database = "battle.db"

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# TODO:

# PARTY
# - expand character to save more data:
    # characters: Class, Level, Species, AC, Speed, Str/Dex/Con/Int/Wis/Cha scores, Str/Dex/Con/Int/Wis/Cha save proficiency, Initiative/skill proficiency
    # players: temp HP, AC bonus, Speed bonus
    # resources: id, character_id, name, number, refresh time (for hit dice, spell slots, class abilities, item charges)
    # attacks: id, character_id, name, bonus, damage, type, range
    # features: character id, name, description
# - button to sort based on initiative for DM

# CREATURES
# - view/add creature pages
# - creature CRUD
# - creature infoview in party screen

@app.route("/")
@login_required
def index():
    """Show user's characters, parties, creatures"""

    # Query database for characters
    with sqlite3.connect(database) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM characters WHERE user_id = ?",
            (session["user_id"],)
        )
        characters = [dict(row) for row in cur.fetchall()]

    # Query database for parties where user is DM or has a character
    with sqlite3.connect(database) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute(
            "SELECT DISTINCT parties.id, parties.dm_id, parties.name FROM parties LEFT JOIN players ON parties.id = players.party_id LEFT JOIN characters ON players.character_id = characters.id WHERE parties.dm_id = ? OR characters.user_id = ?",
            (session["user_id"], session["user_id"])
        )
        parties = [dict(row) for row in cur.fetchall()]

    # Query database for received invitations
    with sqlite3.connect(database) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM invitations JOIN parties ON invitations.party_id = parties.id JOIN users ON parties.dm_id = users.id WHERE user_id = ?",
            (session["user_id"],)
        )
        received_invitations = [dict(row) for row in cur.fetchall()]

    # Query database for sent invitations
    with sqlite3.connect(database) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM invitations JOIN parties ON invitations.party_id = parties.id JOIN users ON invitations.user_id = users.id WHERE parties.dm_id = ?",
            (session["user_id"],)
        )
        sent_invitations = [dict(row) for row in cur.fetchall()]

    return render_template("index.html", characters=characters, parties=parties, received_invitations=received_invitations, sent_invitations=sent_invitations)


@app.route("/character/<character_id>")
@login_required
def view_character(character_id):
    """Show character details"""

    # Query database for character
    with sqlite3.connect(database) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM characters WHERE id = ?",
            (character_id,)
        )
        rows = [dict(row) for row in cur.fetchall()]

    # Ensure character exists
    if len(rows) != 1:
        return error("not found", 404)

    return render_template("character.html", character=rows[0], user=session["user_id"])


@app.route("/character/new/edit", methods=["GET", "POST"])
@login_required
def new_character():
    """New character"""

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure fields were submitted
        if not request.form.get("name"):
            return error("must provide character name", 400)
        if not request.form.get("prof_bonus", type=int) or not request.form.get("max_hitpoints", type=int):
            return error("invalid input", 400)

        # Submit character to database
        with sqlite3.connect(database) as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO characters (name, user_id, prof_bonus, max_hitpoints) VALUES (?, ?, ?, ?) RETURNING id",
                (request.form.get("name"), session["user_id"], int(request.form.get("prof_bonus")), int(request.form.get("max_hitpoints")))
            )
            character_id = cur.fetchone()[0]
            conn.commit()

        # Redirect user to character page
        return redirect("/character/" + str(character_id))

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        new_character = {"id":"new"}

        return render_template("character_edit.html", character=new_character)
    

@app.route("/character/<character_id>/edit", methods=["GET", "POST"])
@login_required
def edit_character(character_id):
    """Edit character"""

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure fields were submitted
        if not request.form.get("name") or not request.form.get("prof_bonus") or not request.form.get("max_hitpoints"):
            return error("missing input", 400)
        
        # Query database for attacks
        with sqlite3.connect(database) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute(
                "SELECT * FROM attacks WHERE character_id = ?",
                (character_id,)
            )
            attacks = [dict(row) for row in cur.fetchall()]

        # Update or delete existing attacks in database
        for attack in attacks:
            if request.form.get("attack_name_" + str(attack["id"])) and request.form.get("attack_bonus_" + str(attack["id"])):
                with sqlite3.connect(database) as conn:
                    cur = conn.cursor()
                    cur.execute(
                        "UPDATE attacks SET name = ?, bonus = ? WHERE id = ? AND character_id = ?",
                        (request.form.get("attack_name_" + str(attack["id"])), request.form.get("attack_bonus_" + str(attack["id"])), attack["id"], character_id)
                    )
                    conn.commit()
            else:
                with sqlite3.connect(database) as conn:
                    cur = conn.cursor()
                    cur.execute(
                        "DELETE FROM attacks WHERE id = ? AND character_id = ?",
                        (attack["id"], character_id)
                    )
                    conn.commit()

        # Insert new attacks in database
        if request.form.get("new_attack_count"):
            for i in range(int(request.form.get("new_attack_count"))):
                if request.form.get("new_attack_name_" + str(i)) and request.form.get("new_attack_bonus_" + str(i)):
                    with sqlite3.connect(database) as conn:
                        cur = conn.cursor()
                        cur.execute(
                            "INSERT INTO attacks (name, bonus, character_id) VALUES (?, ?, ?)",
                            (request.form.get("new_attack_name_" + str(i)), request.form.get("new_attack_bonus_" + str(i)), character_id)
                        )
                        conn.commit()

        # Update character in database
        with sqlite3.connect(database) as conn:
            cur = conn.cursor()
            cur.execute(
                "UPDATE characters SET name = ?, prof_bonus = ?, max_hitpoints = ? WHERE id = ? AND user_id = ?",
                (request.form.get("name"), request.form.get("prof_bonus"), request.form.get("max_hitpoints"), character_id, session["user_id"])
            )
            conn.commit()

        # Redirect user to character page
        return redirect("/character/" + str(character_id))

    # User reached route via GET (as by clicking a link or via redirect)
    else:

        # Query database for character
        with sqlite3.connect(database) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute(
                "SELECT * FROM characters WHERE id = ?",
                (character_id,)
            )
            characters = [dict(row) for row in cur.fetchall()]

        # Ensure character exists
        if len(characters) != 1:
            return error("not found", 404)
        # Ensure character is owned by current user
        elif characters[0]["user_id"] != session["user_id"]:
            return error("forbidden", 403)
        
        # Query database for attacks
        with sqlite3.connect(database) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute(
                "SELECT * FROM attacks WHERE character_id = ?",
                (character_id,)
            )
            attacks = [dict(row) for row in cur.fetchall()]

        return render_template("character_edit.html", character=characters[0], attacks=attacks)
    

@app.route("/character_list")
@login_required
def character_list():
    """Show all characters"""

    # Query database for characters
    with sqlite3.connect(database) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM characters"
        )
        characters = [dict(row) for row in cur.fetchall()]

    return render_template("character_list.html", characters=characters)


@app.route("/party/<party_id>")
@login_required
def view_party(party_id):
    """Show party"""

    # Query database for party
    with sqlite3.connect(database) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM parties WHERE id = ?",
            (party_id,)
        )
        rows = [dict(row) for row in cur.fetchall()]

    # Ensure party exists
    if len(rows) != 1:
        return error("not found", 404)
    
    # Query database for players
    with sqlite3.connect(database) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM players JOIN characters ON character_id = characters.id WHERE party_id = ?",
            (party_id,)
        )
        characters = [dict(row) for row in cur.fetchall()]

    # Sort characters based on initiative, highest first, None at the end
    characters = sorted(characters, key=lambda x: (x["initiative"] is not None, x["initiative"]), reverse=True)

    # Modify initiative for display by replacing None with empty string
    for character in characters:
        if character["initiative"] == None:
            character["initiative"] = ""

    return render_template("party.html", party=rows[0], user=session["user_id"], characters=characters)


@app.route("/party/new/edit", methods=["GET", "POST"])
@login_required
def new_party():
    """New party"""

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure fields were submitted
        if not request.form.get("name"):
            return error("must provide party name", 400)

        # Submit party to database
        with sqlite3.connect(database) as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO parties (name, dm_id) VALUES (?, ?) RETURNING id",
                (request.form.get("name"), session["user_id"])
            )
            party_id = cur.fetchone()[0]
            conn.commit()

        # Redirect user to party page
        return redirect("/party/" + str(party_id))

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        new_party = {"id":"new"}

        return render_template("party_edit.html", party=new_party)
    

@app.route("/party/<party_id>/edit", methods=["GET", "POST"])
@login_required
def edit_party(party_id):
    """Edit party"""

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure fields were submitted
        if not request.form.get("name"):
            return error("must provide party name", 400)

        # Update party in database
        with sqlite3.connect(database) as conn:
            cur = conn.cursor()
            cur.execute(
                "UPDATE parties SET name = ? WHERE id = ? AND dm_id = ?",
                (request.form.get("name"), party_id, session["user_id"])
            )
            conn.commit()

        # Redirect user to party page
        return redirect("/party/" + str(party_id))

    # User reached route via GET (as by clicking a link or via redirect)
    else:

        # Query database for party
        with sqlite3.connect(database) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute(
                "SELECT * FROM parties WHERE id = ?",
                (party_id,)
            )
            rows = [dict(row) for row in cur.fetchall()]

        # Ensure party exists
        if len(rows) != 1:
            return error("not found", 404)
        # Ensure party is owned by current user
        elif rows[0]["dm_id"] != session["user_id"]:
            return error("forbidden", 403)

        return render_template("party_edit.html", party=rows[0])
    

@app.route("/party/<party_id>/invitation", methods=["GET", "POST"])
@login_required
def party_invitation(party_id):
    """Invite new player to party"""

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure fields were submitted
        if not request.form.get("name"):
            return error("must provide player account name", 400)
        
        # Query database for user
        with sqlite3.connect(database) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute(
                "SELECT * FROM users WHERE username = ?",
                (request.form.get("name"),)
            )
            rows = [dict(row) for row in cur.fetchall()]

        # Ensure user exists
        if len(rows) != 1:
            return error("not found", 404)
        invited_user_id = rows[0]["id"]
        
        # Query database for invitations
        with sqlite3.connect(database) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute(
                "SELECT * FROM invitations WHERE party_id = ? AND user_id = ? AND status = ?",
                (party_id, invited_user_id, "pending")
            )
            rows = [dict(row) for row in cur.fetchall()]

        # Ensure user was not already invited
        if len(rows) > 0:
            return error("duplicate invitation pending", 404)

        # Submit invitation to database
        with sqlite3.connect(database) as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO invitations (party_id, user_id, status) VALUES (?, ?, ?)",
                (party_id, invited_user_id, "pending")
            )
            conn.commit()

        # Redirect user to party page
        return redirect("/party/" + str(party_id))

    # User reached route via GET (as by clicking a link or via redirect)
    else:

        # Query database for party
        with sqlite3.connect(database) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute(
                "SELECT * FROM parties WHERE id = ?",
                (party_id,)
            )
            rows = [dict(row) for row in cur.fetchall()]

        # Ensure party exists
        if len(rows) != 1:
            return error("not found", 404)

        return render_template("party_invitation.html", party=rows[0])
    

@app.route("/invitation/<invitation_id>", methods=["GET"])
@login_required
def party_invitation_response(invitation_id):
    """Show invitation details"""

    # Query database for invitations
    with sqlite3.connect(database) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute(
        "SELECT * FROM invitations JOIN parties ON invitations.party_id = parties.id WHERE user_id = ? AND invitations.id = ? AND status = ?",
            (session["user_id"], invitation_id, "pending")
        )
        invitation = [dict(row) for row in cur.fetchall()]

    # Ensure invitation exists
    if len(invitation) != 1:
        return error("not found", 404)
    
    # Query database for characters in party
    with sqlite3.connect(database) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute(
        "SELECT * FROM players JOIN characters ON character_id = characters.id JOIN users ON characters.user_id = users.id WHERE party_id = ?",
            (invitation[0]["party_id"],)
        )
        party_characters = [dict(row) for row in cur.fetchall()]
    
    # Query database for characters
    with sqlite3.connect(database) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM characters WHERE user_id = ?",
            (session["user_id"],)
        )
        characters = [dict(row) for row in cur.fetchall()]

    return render_template("party_invitation_response.html", invitation=invitation[0], characters=characters, party_characters=party_characters)


@app.route("/invitation/<invitation_id>/accepted", methods=["POST"])
@login_required
def party_invitation_response_accepted(invitation_id):
    """Handle accepted invitation"""

    # Query database for invitation
    with sqlite3.connect(database) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM invitations JOIN parties ON invitations.party_id = parties.id WHERE user_id = ? AND invitations.id = ? AND status = ?",
            (session["user_id"], invitation_id, "pending")
        )
        invitations = [dict(row) for row in cur.fetchall()]

    # Ensure invitation exists
    if len(invitations) != 1:
        return error("invitation not found", 404)

    # Ensure fields were submitted
    if not request.form.get("character_id"):
        return error("must select character", 400)

    # Query database for character
    with sqlite3.connect(database) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM characters WHERE id = ?",
            (request.form.get("character_id"),)
        )
        character = [dict(row) for row in cur.fetchall()]

    # Ensure character exists
    if len(character) != 1:
        return error("not found", 404)
        
    # Add character to party
    with sqlite3.connect(database) as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO players (party_id, character_id, initiative, current_hitpoints) VALUES (?, ?, ?, ?)",
            (invitations[0]["party_id"], character[0]["id"], None, character[0]["max_hitpoints"])
        )
        conn.commit()

    # Set invitation as accepted
    with sqlite3.connect(database) as conn:
        cur = conn.cursor()
        cur.execute(
            "UPDATE invitations SET status = ? WHERE invitations.id = ?",
            ("accepted", invitation_id)
        )
        conn.commit()

    # Redirect user to party page
    return redirect("/party/" + str(invitations[0]["party_id"]))
        

@app.route("/invitation/<invitation_id>/denied", methods=["POST"])
@login_required
def party_invitation_response_denied(invitation_id):
    """handle denied or cancelled invitation"""

    # Query database for invitation
    with sqlite3.connect(database) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM invitations WHERE invitations.id = ?",
            (invitation_id,)
        )
        invitations = [dict(row) for row in cur.fetchall()]

    # Ensure invitation exists
    if len(invitations) != 1:
        return error("not found", 404)
    
    # Determine invitation status
    if session["user_id"] == invitations[0]["user_id"]:
        status = "denied"
    else:
        status = "cancelled"

    # Set invitation as denied or cancelled
    with sqlite3.connect(database) as conn:
        cur = conn.cursor()
        cur.execute(
            "UPDATE invitations SET status = ? WHERE invitations.id = ?",
            (status, invitation_id)
        )
        conn.commit()
            
    # Redirect user to index page
    return redirect("/")


@app.route("/party_list")
@login_required
def party_list():
    """Show all parties"""

    # Query database for parties
    with sqlite3.connect(database) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM parties"
        )
        parties = [dict(row) for row in cur.fetchall()]

    return render_template("party_list.html", parties=parties)


@app.route("/creature")
@login_required
def creature():
    """Show creature"""
    # TODO
    # Editable fields describing a creatures's statistics

    # return render_template("creature.html")

    # Return not implemented error
    return error("not implemented", 400)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":
        # Ensure username was submitted
        if not request.form.get("username"):
            return error("must provide username", 400)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return error("must provide password", 400)

        # Query database for username
        with sqlite3.connect(database) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute(
                "SELECT * FROM users WHERE username = ?",
                (request.form.get("username"),)
            )
            rows = [dict(row) for row in cur.fetchall()]
        
        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(
            rows[0]["hash"], request.form.get("password")
        ):
            return error("invalid username and/or password", 400)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
@login_required
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")

@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return error("must provide username", 400)
        
        # Ensure username is unique
        with sqlite3.connect(database) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute(
                "SELECT * FROM users WHERE username = ?",
                (request.form.get("username"),)
            )
            rows = [dict(row) for row in cur.fetchall()]

        if len(rows) != 0:
            return error("username already exists", 400)
        
        # Ensure password was submitted and is equal to confirmation
        elif not request.form.get("password"):
            return error("must provide password", 400)
        elif request.form.get("password") != request.form.get("confirmation"):
            return error("passwords do not match", 400)

        # Submit user to database, return user id
        with sqlite3.connect(database) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO users (username, hash) VALUES (?, ?) RETURNING id",
                (request.form.get("username"), generate_password_hash(request.form.get("password")))
            )
            user_id = cur.fetchone()[0]
            conn.commit()

        # Remember which user has logged in
        session["user_id"] = user_id

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("register.html")
    

# Handle user joining party room
@socketio.on("join")
def on_join(data):
    # Join room for party
    join_room(data["party_id"])


# Handle user leaving party room
@socketio.on("leave")
def on_leave(data):
    # Leave room for party
    leave_room(data["party_id"])


# Handle user initiative input
@socketio.on('init_update')
def handle_init_update(party_id, character_id, initiative):

    # Ensure correct data was submitted
    try:
        party_id = int(party_id)
        character_id = int(character_id)
        if initiative == "":
            initiative = None
        else:
            initiative = int(initiative)
    except TypeError:
        return

    # Update character in database
    with sqlite3.connect(database) as conn:
        cur = conn.cursor()
        cur.execute(
            "UPDATE players SET initiative = ? WHERE party_id = ? AND character_id = ?",
            (initiative, party_id, character_id)
        )
        conn.commit()

    # Send update to party room
    emit("init_updated", {"character_id": str(character_id), "initiative": str(initiative)}, to=str(party_id))


# Handle user hp input
@socketio.on('hp_update')
def handle_hp_update(party_id, character_id, current_hitpoints):

    # Ensure correct data was submitted
    try:
        party_id = int(party_id)
        character_id = int(character_id)
        current_hitpoints = int(current_hitpoints)
    except TypeError:
        return
    except ValueError:
        return

    # Update character in database
    with sqlite3.connect(database) as conn:
        cur = conn.cursor()
        cur.execute(
            "UPDATE players SET current_hitpoints = ? WHERE party_id = ? AND character_id = ?",
            (current_hitpoints, party_id, character_id)
        )
        conn.commit()

    # Send update to party room
    emit("hp_updated", {"character_id": str(character_id), "current_hitpoints": str(current_hitpoints)}, to=str(party_id))