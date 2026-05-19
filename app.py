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
        # Add: max_charges, refresh
        # Add separate database table for tracking number of charges based on player id
    # attacks:
        # Add: range
        # Switch: to damage: id, attack_id, damage_dice_number, damage_dice_size, damage_bonus, damage_type
    # new/edit character use same code?
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
    

@app.route("/character/<character_id>/edit", methods=["GET", "POST"])
@login_required
def edit_character(character_id):
    """Edit character"""

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        print(str(request.form.get("new_attack_name_tags")))
        print(str(request.form.get("new_ability_name_tags")))
        print(str(request.form.get("new_damage_name_tags")))

        # --- Character Data ---
        character = {"name" : request.form.get("name"), 
                     "background" : request.form.get("background"), 
                     "species" : request.form.get("species"), 
                     "class" : request.form.get("class"), 
                     "prof_bonus" : request.form.get("prof_bonus"),
                     "initiative_bonus" : request.form.get("initiative_bonus"), 
                     "speed" : request.form.get("speed"), 
                     "size" : request.form.get("size"), 
                     "max_hitpoints" : request.form.get("max_hitpoints")}

        # Ensure fields were submitted
        if None in character.values():
            return error("missing input", 400)
        
        if character_id == "new":
            # Insert new character
            with sqlite3.connect(database) as conn:
                cur = conn.cursor()
                cur.execute(
                    "INSERT INTO characters (name, background, species, class, prof_bonus, initiative_bonus, speed, size, max_hitpoints, user_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?) RETURNING id",
                    (character["name"], character["background"], character["species"], character["class"], character["prof_bonus"], character["initiative_bonus"], character["speed"], character["size"], character["max_hitpoints"], session["user_id"])
                )
                character_id = cur.fetchone()[0]
                conn.commit()

        else:
            # Update existing character
            with sqlite3.connect(database) as conn:
                cur = conn.cursor()
                cur.execute(
                    "UPDATE characters SET name = ?, background = ?, species = ?, class = ?, prof_bonus = ?, initiative_bonus = ?, speed = ?, size = ?, max_hitpoints = ? WHERE id = ? AND user_id = ?",
                    (character["name"], character["background"], character["species"], character["class"], character["prof_bonus"], character["initiative_bonus"], character["speed"], character["size"], character["max_hitpoints"], character_id, session["user_id"])
                )
                conn.commit()

        # --- Attack Data ---
        # Query database for attacks
        with sqlite3.connect(database) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute(
                "SELECT id FROM attacks WHERE character_id = ?",
                (character_id,)
            )
            attacks = [dict(row) for row in cur.fetchall()]

        # Add form nametags for pre-existing attacks
        for attack in attacks:
            attack["new"] = False
            attack["nametag"] = "a:" + str(attack["id"])
        # Add form nametags for new attacks
        if request.form.get("new_attack_name_tags"):
            for i in str(request.form.get("new_attack_name_tags")).split(","):
                attacks.append({"nametag" : str(i), "new" : True})
        
        # Add form data for attacks to dictionaries using form nametags
        for attack in attacks:
            attack["name"] = request.form.get(attack["nametag"] + "_name")
            attack["bonus"] = request.form.get(attack["nametag"] + "_bonus")
            attack["description"] = request.form.get(attack["nametag"] + "_description")
            attack["retrieved"] = False
            # Check if all attack form data was succesfully retrieved
            if not None in attack.values():
                attack["retrieved"] = True

        for attack in attacks:
            # Update if attack was pre-existing and still present on the form
            if not attack["new"] and attack["retrieved"]:
                with sqlite3.connect(database) as conn:
                    cur = conn.cursor()
                    cur.execute(
                        "UPDATE attacks SET name = ?, bonus = ?, description = ? WHERE id = ? AND character_id = ?",
                        (attack["name"], attack["bonus"], attack["description"], attack["id"], character_id)
                    )
                    conn.commit()
            # Delete if attack was pre-existing and no longer present on the form
            elif not attack["new"] and not attack["retrieved"]:
                with sqlite3.connect(database) as conn:
                    cur = conn.cursor()
                    cur.execute(
                        "DELETE FROM attacks WHERE id = ? AND character_id = ?",
                        (attack["id"], character_id)
                    )
                    conn.commit()
            # Insert if attack is new and present on the form
            elif attack["new"] and attack["retrieved"]:
                with sqlite3.connect(database) as conn:
                    cur = conn.cursor()
                    cur.execute(
                        "INSERT INTO attacks (name, bonus, description, character_id) VALUES (?, ?, ?, ?) RETURNING id",
                        (attack["name"], attack["bonus"], attack["description"], character_id)
                    )
                    attack["id"] = cur.fetchone()[0]
                    conn.commit()
            # Delete from attack list if attack is new and no longer present on the form
            elif attack["new"] and not attack["retrieved"]:
                attacks.remove(attack)

        # -- Ability Data --
        # Query database for abilities
        with sqlite3.connect(database) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute(
                "SELECT id FROM abilities WHERE character_id = ?",
                (character_id,)
            )
            abilities = [dict(row) for row in cur.fetchall()]
        
        # Add form nametags for pre-existing abilities
        for ability in abilities:
            ability["new"] = False
            ability["nametag"] = "s:" + str(ability["id"])
        # Add form nametags for new abilities
        if request.form.get("new_ability_name_tags"):
            for i in request.form.get("new_ability_name_tags").split(","):
                abilities.append({"nametag" : str(i), "new" : True})
        
        # Add form data for abilities to dictionaries using form nametags
        for ability in abilities:
            ability["name"] = request.form.get(ability["nametag"] + "_name")
            ability["dc"] = request.form.get(ability["nametag"] + "_dc")
            ability["attribute"] = request.form.get(ability["nametag"] + "_attribute")
            ability["description"] = request.form.get(ability["nametag"] + "_description")
            ability["retrieved"] = False
            # Check if all ability form data was succesfully retrieved
            if not None in ability.values():
                ability["retrieved"] = True

        for ability in abilities:
            # Update if ability was pre-existing and still present on the form
            if not ability["new"] and ability["retrieved"]:
                with sqlite3.connect(database) as conn:
                    cur = conn.cursor()
                    cur.execute(
                        "UPDATE abilities SET name = ?, dc = ?, attribute = ?, description = ? WHERE id = ? AND character_id = ?",
                        (ability["name"], ability["dc"], ability["attribute"], ability["description"], ability["id"], character_id)
                    )
                    conn.commit()
            # Delete if ability was pre-existing and no longer present on the form
            elif not ability["new"] and not ability["retrieved"]:
                with sqlite3.connect(database) as conn:
                    cur = conn.cursor()
                    cur.execute(
                        "DELETE FROM abilities WHERE id = ? AND character_id = ?",
                        (ability["id"], character_id)
                    )
                    conn.commit()
            # Insert if ability is new and present on the form
            elif ability["new"] and ability["retrieved"]:
                with sqlite3.connect(database) as conn:
                    cur = conn.cursor()
                    cur.execute(
                        "INSERT INTO abilities (name, dc, attribute, description, character_id) VALUES (?, ?, ?, ?, ?) RETURNING id",
                        (ability["name"], ability["dc"], ability["attribute"], ability["description"], character_id)
                    )
                    ability["id"] = cur.fetchone()[0]
                    conn.commit()
            # Delete from ability list if ability is new and no longer present on the form
            elif ability["new"] and not ability["retrieved"]:
                abilities.remove(ability)

        # -- Damage Data ---
        # Query database for damages
        damages = []
        trigger_id_lookup = []
        for trigger in attacks + abilities:
            if trigger["id"]:
                trigger_id_lookup.append({"nametag": trigger["nametag"], "id": trigger["id"]})
            with sqlite3.connect(database) as conn:
                conn.row_factory = sqlite3.Row
                cur = conn.cursor()
                cur.execute(
                    "SELECT id, trigger_id FROM damages WHERE trigger_id = ?",
                    (trigger["id"],)
                )
                trigger_damages = [dict(row) for row in cur.fetchall()]

            # Add form nametags for pre-existing damages
            for trigger_damage in trigger_damages:
                trigger_damage["new"] = False
                trigger_damage["nametag"] = trigger["nametag"][0] + ":" + str(trigger["id"]) + ".d:" + str(trigger_damage["id"])
            damages = damages + trigger_damages

        # Check if new attacks are present on the form, add form nametags for new damages
        if request.form.get("new_damage_name_tags"):
            for i in request.form.get("new_damage_name_tags").split(","):
                for trigger in trigger_id_lookup:
                    if str(i).split(".")[0] == trigger["nametag"]:
                        damages.append({"nametag" : str(i), "trigger_id" : trigger["id"], "new" : True})

        # Add form data for damages to dictionaries using form nametags
        for damage in damages:
            damage["count"] = request.form.get(damage["nametag"] + "_count")
            damage["size"] = request.form.get(damage["nametag"] + "_size")
            damage["bonus"] = request.form.get(damage["nametag"] + "_bonus")
            damage["type"] = request.form.get(damage["nametag"] + "_type")
            damage["retrieved"] = False
            # Check if all damage form data was succesfully retrieved
            if not None in damage.values():
                damage["retrieved"] = True

        print(str(damages))
        
        for damage in damages:
            # Update if damage was pre-existing and still present on the form
            if not damage["new"] and damage["retrieved"]:
                with sqlite3.connect(database) as conn:
                    cur = conn.cursor()
                    cur.execute(
                        "UPDATE damages SET count = ?, size = ?, bonus = ?, type = ? WHERE id = ? AND trigger_id = ?",
                        (damage["count"], damage["size"], damage["bonus"], damage["type"], damage["id"], damage["trigger_id"])
                    )
                    conn.commit()
            # Delete if damage was pre-existing and no longer present on the form
            elif not damage["new"] and not damage["retrieved"]:
                with sqlite3.connect(database) as conn:
                    cur = conn.cursor()
                    cur.execute(
                        "DELETE FROM damages WHERE id = ? and trigger_id = ?",
                        (damage["id"], damage["trigger_id"])
                    )
                    conn.commit()
            # Insert if damage is new and present on the form
            elif damage["new"] and damage["retrieved"]:
                with sqlite3.connect(database) as conn:
                    cur = conn.cursor()
                    cur.execute(
                        "INSERT INTO damages (count, size, bonus, type, trigger_id) VALUES (?, ?, ?, ?, ?) RETURNING id",
                        (damage["count"], damage["size"], damage["bonus"], damage["type"], damage["trigger_id"])
                    )
                    damage["id"] = cur.fetchone()[0]
                    conn.commit()

        # -- Resource Data ---
        # Query database for resources
        with sqlite3.connect(database) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute(
                "SELECT * FROM attacks WHERE character_id = ?",
                (character_id,)
            )
            existing_resources = [dict(row) for row in cur.fetchall()]

        # Create list containing dictionaries for newly added and pre-existing resources
        resources = []
        # Add form nametags for new resources
        if request.form.get("new_resource_name_tags"):
            for i in request.form.get("new_resource_name_tags").split(","):
                resources.append({"nametag" : "new_" + str(i), "new" : True})
        # Add form nametags and database id for pre-existing resources
        for existing_resource in existing_resources:
            resources.append({"nametag": str(existing_resource["id"]), "new" : False, "id" : str(existing_resource["id"])})

        # Add form data for resources to dictionaries using form nametags
        for resource in resources:
            resource["name"] = request.form.get("resource_name_" + resource["nametag"])
            resource["max_charges"] = request.form.get("resource_max_charges_" + resource["nametag"])
            resource["recharge"] = request.form.get("resource_recharge_" + resource["nametag"])
            resource["retrieved"] = False
            # Check if all form data was succesfully retrieved
            if not None in resource.values():
                resource["retrieved"] = True

        for resource in resources:
            # Update if resource was pre-existing and still present on the form
            if not resource["new"] and resource["retrieved"]:
                with sqlite3.connect(database) as conn:
                    cur = conn.cursor()
                    cur.execute(
                        "UPDATE resources SET name = ?, max_charges = ?, recharge = ? WHERE id = ? AND character_id = ?",
                        (resource["name"], resource["max_charges"], resource["recharge"], resource["id"], character_id)
                    )
                    conn.commit()
            # Delete if resource was pre-existing and no longer present on the form
            elif not resource["new"] and not resource["retrieved"]:
                with sqlite3.connect(database) as conn:
                    cur = conn.cursor()
                    cur.execute(
                        "DELETE FROM resources WHERE id = ? AND character_id = ?",
                        (resource["id"], character_id)
                    )
                    conn.commit()
            # Insert if resource is new and present on the form
            elif resource["new"] and resource["retrieved"]:
                with sqlite3.connect(database) as conn:
                    cur = conn.cursor()
                    cur.execute(
                        "INSERT INTO resources (name, max_charges, recharge, character_id) VALUES (?, ?, ?, ?)",
                        (resource["name"], resource["max_charges"], resource["recharge"], character_id)
                    )
                    conn.commit()

        # Redirect user to character page
        return redirect("/character/" + str(character_id))

    # User reached route via GET (as by clicking a link or via redirect)
    else:

        # Check if character is new or pre-existing
        if character_id == "new":
            # Character is new
            character = {"id":"new"}
            attacks = []
            resources = []

        else:
            # Query database for existing character
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
            character = characters[0]
            if character["user_id"] != session["user_id"]:
                return error("forbidden", 403)
        
            # Query database for attacks
            with sqlite3.connect(database) as conn:
                conn.row_factory = sqlite3.Row
                cur = conn.cursor()
                cur.execute(
                    "SELECT * FROM attacks WHERE attacks.character_id = ?",
                    (character_id,)
                )
                attacks = [dict(row) for row in cur.fetchall()]

            # Query database for damage related to attacks
            for attack in attacks:
                with sqlite3.connect(database) as conn:
                    conn.row_factory = sqlite3.Row
                    cur = conn.cursor()
                    cur.execute(
                        "SELECT * FROM damages WHERE trigger_id = ?",
                        (attack["id"],)
                    )
                    attack["damages"] = [dict(row) for row in cur.fetchall()]

            # Query database for abilities
            with sqlite3.connect(database) as conn:
                conn.row_factory = sqlite3.Row
                cur = conn.cursor()
                cur.execute(
                    "SELECT * FROM abilities WHERE character_id = ?",
                    (character_id,)
                )
                abilities = [dict(row) for row in cur.fetchall()]

            # Query database for damage related to abilities
            for ability in abilities:
                with sqlite3.connect(database) as conn:
                    conn.row_factory = sqlite3.Row
                    cur = conn.cursor()
                    cur.execute(
                        "SELECT * FROM damages WHERE trigger_id = ?",
                        (ability["id"],)
                    )
                    ability["damages"] = [dict(row) for row in cur.fetchall()]

            # Query database for resources
            with sqlite3.connect(database) as conn:
                conn.row_factory = sqlite3.Row
                cur = conn.cursor()
                cur.execute(
                    "SELECT * FROM resources WHERE character_id = ?",
                    (character_id,)
                )
                resources = [dict(row) for row in cur.fetchall()]

        return render_template("character_edit.html", character=character, attacks=attacks, abilities=abilities, resources=resources)
    

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