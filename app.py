import os
import sys
import sqlite3

from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from flask_socketio import SocketIO, send, emit, join_room, leave_room
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import error, login_required, handle_creature_features, sql_insert, sql_update

# Configure application
app = Flask(__name__)
socketio = SocketIO(app)

# Configure database name
database = "battle.db"

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

@app.route("/")
@login_required
def index():
    """Show user's characters, campaigns, mosters, invitations"""

    # Query database for characters
    with sqlite3.connect(database) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM creatures JOIN characters ON creatures.id = characters.creature_id WHERE user_id = ?",
            (session["user_id"],)
        )
        characters = [dict(row) for row in cur.fetchall()]

    # Query database for campaigns where user is DM or has a character
    with sqlite3.connect(database) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute(
            "SELECT DISTINCT campaigns.id, campaigns.dm_id, campaigns.name FROM campaigns LEFT JOIN players ON campaigns.id = players.campaign_id LEFT JOIN creatures ON players.creature_id = creatures.id WHERE campaigns.dm_id = ? OR creatures.user_id = ?",
            (session["user_id"], session["user_id"])
        )
        campaigns = [dict(row) for row in cur.fetchall()]

     # Query database for monsters
    with sqlite3.connect(database) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM creatures JOIN monsters ON creatures.id = monsters.creature_id WHERE user_id = ?",
            (session["user_id"],)
        )
        monsters = [dict(row) for row in cur.fetchall()]

    # Query database for received invitations
    with sqlite3.connect(database) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM invitations JOIN campaigns ON invitations.campaign_id = campaigns.id JOIN users ON campaigns.dm_id = users.id WHERE user_id = ?",
            (session["user_id"],)
        )
        received_invitations = [dict(row) for row in cur.fetchall()]

    # Query database for sent invitations
    with sqlite3.connect(database) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM invitations JOIN campaigns ON invitations.campaign_id = campaigns.id JOIN users ON invitations.user_id = users.id WHERE campaigns.dm_id = ?",
            (session["user_id"],)
        )
        sent_invitations = [dict(row) for row in cur.fetchall()]

    return render_template("index.html", user=session["user_id"], characters=characters, campaigns=campaigns, monsters=monsters, received_invitations=received_invitations, sent_invitations=sent_invitations)


@app.route("/character_list")
@login_required
def character_list():
    """Show all characters"""

    # Query database for characters
    with sqlite3.connect(database) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM characters LEFT JOIN creatures ON characters.creature_id = creatures.id"
        )
        characters = [dict(row) for row in cur.fetchall()]

    return render_template("character_list.html", characters=characters)


@app.route("/character/<creature_id>")
@login_required
def view_character(creature_id):
    """Show character details"""

    # Query database for character
    with sqlite3.connect(database) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM characters LEFT JOIN creatures ON characters.creature_id = creatures.id WHERE id = ?",
            (creature_id,)
        )
        rows = [dict(row) for row in cur.fetchall()]

    # Ensure character exists
    if len(rows) != 1:
        return error("not found", 404)
    character = rows[0]

    return render_template("character.html", user=session["user_id"], character=character)
    

@app.route("/character/<creature_id>/edit", methods=["GET", "POST"])
@login_required
def edit_character(creature_id):
    """Edit character"""

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        character = {}
        character_traits = ["name", "background", "species", "class",
                            "prof_bonus", "initiative_bonus", "speed", "size", "max_hitpoints"]
        for character_trait in character_traits:
            character[character_trait] = request.form.get(character_trait)

        # Ensure fields were submitted
        if None in character.values():
            return error("missing input", 400)
        
        if creature_id == "new":
            # Insert new creature
            with sqlite3.connect(database) as conn:
                cur = conn.cursor()
                cur.execute(
                    "INSERT INTO creatures (user_id, is_player) VALUES (?, ?) RETURNING id",
                    (session["user_id"], 1)
                )
                creature_id = cur.fetchone()[0]
                conn.commit()

            # Insert new character
            character["creature_id"] = creature_id
            sql_insert(database, "characters", character)

        else:
            # Query database for creature
            with sqlite3.connect(database) as conn:
                conn.row_factory = sqlite3.Row
                cur = conn.cursor()
                cur.execute(
                    "SELECT * FROM creatures WHERE id = ?",
                    (creature_id,)
                )
                creatures = [dict(row) for row in cur.fetchall()]

            if creatures[0]["user_id"] != session["user_id"]:
                return error("forbidden", 403)

            # Update existing character
            sql_update(database, "characters", character, {"creature_id" : creature_id})

        handle_creature_features(database, creature_id)

        # Redirect user to character page
        return redirect("/character/" + str(creature_id))

    # User reached route via GET (as by clicking a link or via redirect)
    else:

        # Check if character is new or pre-existing
        if creature_id == "new":
            # Character is new
            character = {"creature_id":"new"}
            attacks = []
            abilities = []
            resources = []

        else:
            # Query database for existing character
            with sqlite3.connect(database) as conn:
                conn.row_factory = sqlite3.Row
                cur = conn.cursor()
                cur.execute(
                    "SELECT * FROM characters LEFT JOIN creatures ON characters.creature_id = creatures.id WHERE id = ?",
                    (creature_id,)
                )
                characters = [dict(row) for row in cur.fetchall()]

            # Ensure character exists
            if len(characters) != 1:
                return error("not found", 404)
            # Ensure character is owned by current user
            character = characters[0]
            if character["user_id"] != session["user_id"]:
                return error("forbidden", 403)
        
            # Query database for attacks
            with sqlite3.connect(database) as conn:
                conn.row_factory = sqlite3.Row
                cur = conn.cursor()
                cur.execute(
                    "SELECT * FROM attacks WHERE attacks.creature_id = ?",
                    (creature_id,)
                )
                attacks = [dict(row) for row in cur.fetchall()]

            # Query database for damage related to attacks
            for attack in attacks:
                with sqlite3.connect(database) as conn:
                    conn.row_factory = sqlite3.Row
                    cur = conn.cursor()
                    cur.execute(
                        "SELECT * FROM damages WHERE trigger_id = ?",
                        ("a:" + str(attack["id"]),)
                    )
                    attack["damages"] = [dict(row) for row in cur.fetchall()]

            # Query database for abilities
            with sqlite3.connect(database) as conn:
                conn.row_factory = sqlite3.Row
                cur = conn.cursor()
                cur.execute(
                    "SELECT * FROM abilities WHERE creature_id = ?",
                    (creature_id,)
                )
                abilities = [dict(row) for row in cur.fetchall()]

            # Query database for damage related to abilities
            for ability in abilities:
                with sqlite3.connect(database) as conn:
                    conn.row_factory = sqlite3.Row
                    cur = conn.cursor()
                    cur.execute(
                        "SELECT * FROM damages WHERE trigger_id = ?",
                        ("s:" + str(ability["id"]),)
                    )
                    ability["damages"] = [dict(row) for row in cur.fetchall()]

            # Query database for resources
            with sqlite3.connect(database) as conn:
                conn.row_factory = sqlite3.Row
                cur = conn.cursor()
                cur.execute(
                    "SELECT * FROM resources WHERE creature_id = ?",
                    (creature_id,)
                )
                resources = [dict(row) for row in cur.fetchall()]

        return render_template("character_edit.html", character=character, attacks=attacks, abilities=abilities, resources=resources)


@app.route("/monster_list")
@login_required
def monster_list():
    """Show all monsters"""

    # Query database for campaigns
    with sqlite3.connect(database) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM monsters LEFT JOIN creatures ON monsters.creature_id = creatures.id"
        )
        monsters = [dict(row) for row in cur.fetchall()]

    return render_template("monster_list.html", monsters=monsters)


@app.route("/monster/<creature_id>")
@login_required
def view_monsters(creature_id):
    """Show monster details"""

    # Query database for monster
    with sqlite3.connect(database) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM monsters LEFT JOIN creatures ON monsters.creature_id = creatures.id WHERE id = ?",
            (creature_id,)
        )
        rows = [dict(row) for row in cur.fetchall()]

    # Ensure monster exists
    if len(rows) != 1:
        return error("not found", 404)
    monster = rows[0]

    return render_template("monster.html", monster=monster, user=session["user_id"])


@app.route("/monster/<creature_id>/edit", methods=["GET", "POST"])
@login_required
def edit_monster(creature_id):
    """Edit monster"""

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        monster = {}
        monster_traits = ["name", "size", "type", "alignment",
                          "armor_class", "max_hitpoints", "challenge_rating", "initiative_bonus", "speed",
                          "strength", "dexterity", "constitution", "intelligence", "wisdom", "charisma",
                          "strength_save_bonus", "dexterity_save_bonus", "constitution_save_bonus", "intelligence_save_bonus", "wisdom_save_bonus", "charisma_save_bonus",
                          "skills", "vulnerabilities", "resistances", "immunities", "senses", "languages",
                          "traits", "actions", "bonus_actions", "reactions", "legendary_actions"]
        for monster_trait in monster_traits:
            monster[monster_trait] = request.form.get(monster_trait)

        # Ensure fields were submitted
        if None in monster.values():
            return error("missing input", 400)
        
        if creature_id == "new":
            # Insert new creature
            with sqlite3.connect(database) as conn:
                cur = conn.cursor()
                cur.execute(
                    "INSERT INTO creatures (user_id, is_player) VALUES (?, ?) RETURNING id",
                    (session["user_id"], 0)
                )
                creature_id = cur.fetchone()[0]
                conn.commit()

            # Insert new monster
            monster["creature_id"] = creature_id
            sql_insert(database, "monsters", monster)

        else:
            # Query database for creature
            with sqlite3.connect(database) as conn:
                conn.row_factory = sqlite3.Row
                cur = conn.cursor()
                cur.execute(
                    "SELECT * FROM creatures WHERE id = ?",
                    (creature_id,)
                )
                creatures = [dict(row) for row in cur.fetchall()]

            if creatures[0]["user_id"] != session["user_id"]:
                return error("forbidden", 403)

            # Update existing monster
            sql_update(database, "monsters", monster, {"creature_id" : creature_id})

        handle_creature_features(database, creature_id)

        # Redirect user to character page
        return redirect("/monster/" + str(creature_id))

    # User reached route via GET (as by clicking a link or via redirect)
    else:

        # Check if monster is new or pre-existing
        if creature_id == "new":
            # Monster is new
            monster = {"creature_id":"new"}
            attacks = []
            abilities = []
            resources = []
        
        else:
            # Query database for existing monster
            with sqlite3.connect(database) as conn:
                conn.row_factory = sqlite3.Row
                cur = conn.cursor()
                cur.execute(
                    "SELECT * FROM monsters LEFT JOIN creatures ON monsters.creature_id = creatures.id WHERE id = ?",
                    (creature_id,)
                )
                monsters = [dict(row) for row in cur.fetchall()]

            # Ensure monster exists
            if len(monsters) != 1:
                return error("not found", 404)
            # Ensure monster is owned by current user
            monster = monsters[0]
            if monster["user_id"] != session["user_id"]:
                return error("forbidden", 403)
        
            # Query database for attacks
            with sqlite3.connect(database) as conn:
                conn.row_factory = sqlite3.Row
                cur = conn.cursor()
                cur.execute(
                    "SELECT * FROM attacks WHERE attacks.creature_id = ?",
                    (creature_id,)
                )
                attacks = [dict(row) for row in cur.fetchall()]

            # Query database for damage related to attacks
            for attack in attacks:
                with sqlite3.connect(database) as conn:
                    conn.row_factory = sqlite3.Row
                    cur = conn.cursor()
                    cur.execute(
                        "SELECT * FROM damages WHERE trigger_id = ?",
                        ("a:" + str(attack["id"]),)
                    )
                    attack["damages"] = [dict(row) for row in cur.fetchall()]

            # Query database for abilities
            with sqlite3.connect(database) as conn:
                conn.row_factory = sqlite3.Row
                cur = conn.cursor()
                cur.execute(
                    "SELECT * FROM abilities WHERE creature_id = ?",
                    (creature_id,)
                )
                abilities = [dict(row) for row in cur.fetchall()]

            # Query database for damage related to abilities
            for ability in abilities:
                with sqlite3.connect(database) as conn:
                    conn.row_factory = sqlite3.Row
                    cur = conn.cursor()
                    cur.execute(
                        "SELECT * FROM damages WHERE trigger_id = ?",
                        ("s:" + str(ability["id"]),)
                    )
                    ability["damages"] = [dict(row) for row in cur.fetchall()]

            # Query database for resources
            with sqlite3.connect(database) as conn:
                conn.row_factory = sqlite3.Row
                cur = conn.cursor()
                cur.execute(
                    "SELECT * FROM resources WHERE creature_id = ?",
                    (creature_id,)
                )
                resources = [dict(row) for row in cur.fetchall()]

        return render_template("monster_edit.html", monster=monster, attacks=attacks, abilities=abilities, resources=resources)


@app.route("/campaign_list")
@login_required
def campaign_list():
    """Show all campaigns"""

    # Query database for campaigns
    with sqlite3.connect(database) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM campaigns"
        )
        campaigns = [dict(row) for row in cur.fetchall()]

    return render_template("campaign_list.html", campaigns=campaigns)


@app.route("/campaign/<campaign_id>")
@login_required
def view_campaign(campaign_id):
    """Show campaign"""

    # Query database for campaign
    with sqlite3.connect(database) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM campaigns WHERE id = ?",
            (campaign_id,)
        )
        rows = [dict(row) for row in cur.fetchall()]

    # Ensure campaign exists
    if len(rows) != 1:
        return error("not found", 404)
    campaign = rows[0]
    
    # Query database for players
    with sqlite3.connect(database) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM players JOIN characters ON players.creature_id = characters.creature_id JOIN creatures ON players.creature_id = creatures.id JOIN users ON creatures.user_id = users.id WHERE campaign_id = ?",
            (campaign_id,)
        )
        characters = [dict(row) for row in cur.fetchall()]

    # Query database for invitations
    with sqlite3.connect(database) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM invitations JOIN users ON user_id = users.id WHERE campaign_id = ?",
            (campaign_id,)
        )
        invitations = [dict(row) for row in cur.fetchall()]

    return render_template("campaign.html", user=session["user_id"], campaign=campaign, characters=characters, invitations=invitations)
    

@app.route("/campaign/<campaign_id>/edit", methods=["GET", "POST"])
@login_required
def edit_campaign(campaign_id):
    """Edit campaign"""

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure fields were submitted
        campaign = {"name" : request.form.get("campaign_name"), 
                    "description" : request.form.get("campaign_description")}

        # Ensure fields were submitted
        if None in campaign.values():
            return error("missing input", 400)
        
        if campaign_id == "new":
            # Insert new campaign
            with sqlite3.connect(database) as conn:
                cur = conn.cursor()
                cur.execute(
                    "INSERT INTO campaigns (name, description, dm_id) VALUES (?, ?, ?) RETURNING id",
                    (campaign["name"], campaign["description"], session["user_id"])
                )
                campaign_id = cur.fetchone()[0]
                conn.commit()

        else:
            # Update existing campaign
            with sqlite3.connect(database) as conn:
                cur = conn.cursor()
                cur.execute(
                    "UPDATE campaigns SET name = ?, description = ? WHERE id = ? AND dm_id = ?",
                    (campaign["name"], campaign["description"], campaign_id, session["user_id"])
                )
                conn.commit()

        # Redirect user to campaign page
        return redirect("/campaign/" + str(campaign_id))

    # User reached route via GET (as by clicking a link or via redirect)
    else:

        # Check if campaign is new or pre-existing
        if campaign_id == "new":
            # Campaign is new
            campaign = {"id":"new"}

        else:
        # Query database for campaign
            with sqlite3.connect(database) as conn:
                conn.row_factory = sqlite3.Row
                cur = conn.cursor()
                cur.execute(
                    "SELECT * FROM campaigns WHERE id = ?",
                    (campaign_id,)
                )
                campaigns = [dict(row) for row in cur.fetchall()]

            # Ensure campaign exists
            if len(campaigns) != 1:
                return error("not found", 404)
            # Ensure campaign is owned by current user
            campaign=campaigns[0]
            if campaign["dm_id"] != session["user_id"]:
                return error("forbidden", 403)

        return render_template("campaign_edit.html", campaign=campaign)
    

@app.route("/campaign/<campaign_id>/invitation", methods=["GET", "POST"])
@login_required
def campaign_invitation(campaign_id):
    """Invite new player to campaign"""

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure fields were submitted
        if not request.form.get("invitation_name"):
            return error("must provide player account name", 400)
        
        # Query database for user
        with sqlite3.connect(database) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute(
                "SELECT * FROM users WHERE username = ?",
                (request.form.get("invitation_name"),)
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
                "SELECT * FROM invitations WHERE campaign_id = ? AND user_id = ? AND status = ?",
                (campaign_id, invited_user_id, "pending")
            )
            rows = [dict(row) for row in cur.fetchall()]

        # Ensure user was not already invited
        if len(rows) > 0:
            return error("duplicate invitation pending", 404)

        # Submit invitation to database
        with sqlite3.connect(database) as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO invitations (campaign_id, user_id, status) VALUES (?, ?, ?)",
                (campaign_id, invited_user_id, "pending")
            )
            conn.commit()

        # Redirect user to campaign page
        return redirect("/campaign/" + str(campaign_id))


@app.route("/invitation/<invitation_id>/accepted", methods=["POST"])
@login_required
def campaign_invitation_response_accepted(invitation_id):
    """Handle accepted invitation"""

    # Query database for invitation
    with sqlite3.connect(database) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM invitations JOIN campaigns ON invitations.campaign_id = campaigns.id WHERE user_id = ? AND invitations.id = ? AND status = ?",
            (session["user_id"], invitation_id, "pending")
        )
        invitations = [dict(row) for row in cur.fetchall()]

    # Ensure invitation exists
    if len(invitations) != 1:
        return error("invitation not found", 404)

    # Ensure fields were submitted
    if not request.form.get("creature_id"):
        return error("must select character", 400)

    # Query database for character
    with sqlite3.connect(database) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM characters WHERE creature_id = ?",
            (request.form.get("creature_id"),)
        )
        character = [dict(row) for row in cur.fetchall()]

    # Ensure character exists
    if len(character) != 1:
        return error("not found", 404)
        
    # Add character to campaign
    with sqlite3.connect(database) as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO players (campaign_id, creature_id) VALUES (?, ?)",
            (invitations[0]["campaign_id"], character[0]["creature_id"])
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

    # Redirect user to campaign page
    return redirect("/campaign/" + str(invitations[0]["campaign_id"]))
        

@app.route("/invitation/<invitation_id>/denied", methods=["POST"])
@login_required
def campaign_invitation_response_denied(invitation_id):
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
    invitation = invitations[0]
    
    # Determine invitation status
    if session["user_id"] == invitation["user_id"]:
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
            
    # Redirect user to index page depending on status
    if status == "denied":
        return redirect("/")
    elif status == "cancelled":
        return redirect("/campaign/" + str(invitation["campaign_id"]))


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
    

# Handle user joining campaign room
@socketio.on("join")
def on_join(data):
    # Join room for campaign
    join_room(data["campaign_id"])
    # Join room for user
    join_room(data["user_id"])


# Handle user leaving campaign room
@socketio.on("leave")
def on_leave(data):
    # Leave room for campaign
    leave_room(data["campaign_id"])
    # Join room for user
    join_room(data["user_id"])


# Handle user initiative input
# !! BROKEN due to character/creature change
@socketio.on('init_update')
def handle_init_update(campaign_id, creature_id, initiative):

    # Ensure correct data was submitted
    try:
        campaign_id = int(campaign_id)
        creature_id = int(creature_id)
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
            "UPDATE players SET initiative = ? WHERE campaign_id = ? AND creature_id = ?",
            (initiative, campaign_id, creature_id)
        )
        conn.commit()

    # Send update to campaign room
    emit("init_updated", {"character_id": str(creature_id), "initiative": str(initiative)}, to=str(campaign_id))


# Handle user hp input
# !! BROKEN due to character/creature change
@socketio.on('hp_update')
def handle_hp_update(campaign_id, creature_id, current_hitpoints):

    # Ensure correct data was submitted
    try:
        campaign_id = int(campaign_id)
        creature_id = int(creature_id)
        current_hitpoints = int(current_hitpoints)
    except TypeError:
        return
    except ValueError:
        return

    # Update character in database
    with sqlite3.connect(database) as conn:
        cur = conn.cursor()
        cur.execute(
            "UPDATE players SET current_hitpoints = ? WHERE campaign_id = ? AND creature_id = ?",
            (current_hitpoints, campaign_id, creature_id)
        )
        conn.commit()

    # Send update to campaign room
    emit("hp_updated", {"character_id": str(creature_id), "current_hitpoints": str(current_hitpoints)}, to=str(campaign_id))


# Handle user character details request
# !! BROKEN due to character/creature change
@socketio.on('character_info_request')
def handle_character_info_request(user_id, creature_id):

    # Ensure correct data was submitted
    try:
        user_id = int(user_id)
        creature_id = int(creature_id)
    except TypeError:
        print("TypeError")
        return
    except ValueError:
        print("ValueError")
        return
    
    # Query database for character
    with sqlite3.connect(database) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM creatures WHERE id = ?",
            (creature_id,)
        )
        creatures = [dict(row) for row in cur.fetchall()]

    # Ensure character exists
    if len(creatures) != 1:
        return error("not found", 404)

    # Send update to campaign room
    emit("character_details_updated", {"character": creatures[0]}, to=str(user_id))