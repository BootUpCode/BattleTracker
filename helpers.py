import sqlite3

from flask import redirect, render_template, session, request
from functools import wraps

def error(message, code=400):
    """Render message as an apology to user."""

    def escape(s):
        """
        Escape special characters.

        https://github.com/jacebrowning/memegen#special-characters
        """
        for old, new in [
            ("-", "--"),
            (" ", "-"),
            ("_", "__"),
            ("?", "~q"),
            ("%", "~p"),
            ("#", "~h"),
            ("/", "~s"),
            ('"', "''"),
        ]:
            s = s.replace(old, new)
        return s

    return render_template("error.html", top=code, bottom=escape(message)), code


def login_required(f):
    """
    Decorate routes to require login.

    https://flask.palletsprojects.com/en/latest/patterns/viewdecorators/
    """

    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get("user_id") is None:
            return redirect("/login")
        return f(*args, **kwargs)

    return decorated_function


def handle_creature_features(database, creature_id):
    """Handle data from optional features on creature edit page"""

    # --- Attack Data ---
    # Lookup form data for nametags of new attacks
    attackNametags = ""
    if request.form.get("new_attack_name_tags"):
        attackNametags = request.form.get("new_attack_name_tags")

    # Query database for nametags of existing attacks
    with sqlite3.connect(database) as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT id FROM attacks WHERE creature_id = ?",
            (creature_id,)
        )
        for result in cur.fetchall():
            attackNametags += ",a:" + str(result[0])

    # Add form data for attacks to dictionaries using form nametags
    attacks = []
    for nametag in attackNametags.split(","):
        if nametag != "":
            attack = {"nametag" : nametag,
                        "name" : request.form.get(nametag + "_name"),
                        "description" : request.form.get(nametag + "_description"),
                        "retrieved" : False,}
            try:
                attack["bonus"] = int(request.form.get(nametag + "_bonus"))
            except:
                attack["bonus"] = 0
            # Check if all attack form data was succesfully retrieved
            if not None in attack.values():
                attack["retrieved"] = True
            attacks.append(attack)

    # Dictionary for saving database id of new attacks and abilities for database entries of related damage
    newTriggerLookup = {}

    for attack in attacks:
        # Update if attack was pre-existing and still present on the form
        if not attack["nametag"][2:5] == "new" and attack["retrieved"]:
            with sqlite3.connect(database) as conn:
                cur = conn.cursor()
                cur.execute(
                    "UPDATE attacks SET name = ?, bonus = ?, description = ? WHERE id = ? AND creature_id = ?",
                    (attack["name"], attack["bonus"], attack["description"], attack["nametag"][2:], creature_id)
                )
                conn.commit()
        # Delete if attack was pre-existing and no longer present on the form
        elif not attack["nametag"][2:5] == "new" and not attack["retrieved"]:
            with sqlite3.connect(database) as conn:
                cur = conn.cursor()
                cur.execute(
                    "DELETE FROM attacks WHERE id = ? AND creature_id = ?",
                    (attack["nametag"][2:], creature_id)
                )
                conn.commit()
        # Insert if attack is new and present on the form
        elif attack["nametag"][2:5] == "new" and attack["retrieved"]:
            with sqlite3.connect(database) as conn:
                cur = conn.cursor()
                cur.execute(
                    "INSERT INTO attacks (name, bonus, description, creature_id) VALUES (?, ?, ?, ?) RETURNING id",
                    (attack["name"], attack["bonus"], attack["description"], creature_id)
                )
                newTriggerLookup[attack["nametag"]] = "a:" + str(cur.fetchone()[0])
                conn.commit()

    # -- Ability Data --
    # Lookup form data for nametags of new abilities
    abilityNametags = ""
    if request.form.get("new_ability_name_tags"):
        abilityNametags = request.form.get("new_ability_name_tags")

    # Query database for nametags of existing abilities
    with sqlite3.connect(database) as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT id FROM abilities WHERE creature_id = ?",
            (creature_id,)
        )
        for result in cur.fetchall():
            abilityNametags += ",s:" + str(result[0])

    # Add form data for abilities to dictionaries using form nametags
    abilities = []
    for nametag in abilityNametags.split(","):
        if nametag != "":
            ability = {"nametag" : nametag,
                        "name" : request.form.get(nametag + "_name"),
                        "attribute" : request.form.get(nametag + "_attribute"),
                        "description" : request.form.get(nametag + "_description"),
                        "retrieved" : False}
            try:
                ability["dc"] = int(request.form.get(nametag + "_dc"))
            except:
                ability["dc"] = 0
            # Check if all ability form data was succesfully retrieved
            if not None in ability.values():
                ability["retrieved"] = True
            abilities.append(ability)

    for ability in abilities:
        # Update if ability was pre-existing and still present on the form
        if not ability["nametag"][2:5] == "new" and ability["retrieved"]:
            with sqlite3.connect(database) as conn:
                cur = conn.cursor()
                cur.execute(
                    "UPDATE abilities SET name = ?, dc = ?, attribute = ?, description = ? WHERE id = ? AND creature_id = ?",
                    (ability["name"], ability["dc"], ability["attribute"], ability["description"], ability["nametag"][2:], creature_id)
                )
                conn.commit()
        # Delete if ability was pre-existing and no longer present on the form
        elif not ability["nametag"][2:5] == "new" and not ability["retrieved"]:
            with sqlite3.connect(database) as conn:
                cur = conn.cursor()
                cur.execute(
                    "DELETE FROM abilities WHERE id = ? AND creature_id = ?",
                    (ability["nametag"][2:], creature_id)
                )
                conn.commit()
        # Insert if ability is new and present on the form
        elif ability["nametag"][2:5] == "new" and ability["retrieved"]:
            with sqlite3.connect(database) as conn:
                cur = conn.cursor()
                cur.execute(
                    "INSERT INTO abilities (name, dc, attribute, description, creature_id) VALUES (?, ?, ?, ?, ?) RETURNING id",
                    (ability["name"], ability["dc"], ability["attribute"], ability["description"], creature_id)
                )
                newTriggerLookup[ability["nametag"]] = "s:" + str(cur.fetchone()[0])
                conn.commit()

    # -- Damage Data ---
    # Lookup form data for nametags of new damages
    damageNametags = ""
    if request.form.get("new_damage_name_tags"):
        damageNametags = request.form.get("new_damage_name_tags")

    # Query database for nametags of existing damages
    for trigger in attacks + abilities:
        if trigger["nametag"][2:5] != "new":
            with sqlite3.connect(database) as conn:
                cur = conn.cursor()
                cur.execute(
                    "SELECT id FROM damages WHERE trigger_id = ?",
                    (trigger["nametag"],)
                )
                for result in cur.fetchall():
                    damageNametags += "," + trigger["nametag"] + ".d:" + str(result[0])

    # Add form data for damages to dictionaries using form nametags
    damages = []
    for nametag in damageNametags.split(","):
        if nametag != "":
            damage = {"nametag" : nametag[nametag.find("d"):],
                        "trigger_nametag" : nametag[:nametag.find(".")],
                        "type" : request.form.get(nametag + "_type"),
                        "retrieved" : False}
            for damageAttribute in ["count", "size", "bonus"]:
                try:
                    damage[damageAttribute] = int(request.form.get(nametag + "_" + damageAttribute))
                except:
                    damage[damageAttribute] = 0
            # Find database id of triggering attack or ability if it is newly added to database
            if damage["trigger_nametag"][2:5] == "new":
                damage["trigger_nametag"] = newTriggerLookup[damage["trigger_nametag"]]
            # Check if all damage form data was succesfully retrieved
            if not None in damage.values():
                damage["retrieved"] = True
            damages.append(damage)
    
    for damage in damages:
        # Update if damage was pre-existing and still present on the form
        if not damage["nametag"][2:5] == "new" and damage["retrieved"]:
            with sqlite3.connect(database) as conn:
                cur = conn.cursor()
                cur.execute(
                    "UPDATE damages SET count = ?, size = ?, bonus = ?, type = ? WHERE id = ? AND trigger_id = ?",
                    (damage["count"], damage["size"], damage["bonus"], damage["type"], damage["nametag"][2:], damage["trigger_nametag"])
                )
                conn.commit()
        # Delete if damage was pre-existing and no longer present on the form
        elif not damage["nametag"][2:5] == "new" and not damage["retrieved"]:
            with sqlite3.connect(database) as conn:
                cur = conn.cursor()
                cur.execute(
                    "DELETE FROM damages WHERE id = ? and trigger_id = ?",
                    (damage["nametag"][2:], damage["trigger_nametag"])
                )
                conn.commit()
        # Insert if damage is new and present on the form
        elif damage["nametag"][2:5] == "new" and damage["retrieved"]:
            with sqlite3.connect(database) as conn:
                cur = conn.cursor()
                cur.execute(
                    "INSERT INTO damages (count, size, bonus, type, trigger_id) VALUES (?, ?, ?, ?, ?)",
                    (damage["count"], damage["size"], damage["bonus"], damage["type"], damage["trigger_nametag"])
                )
                conn.commit()

    # -- Resource Data ---
    # Lookup form data for nametags of new resources
    resourceNametags = ""
    if request.form.get("new_resource_name_tags"):
        resourceNametags = request.form.get("new_resource_name_tags")

    # Query database for nametags of existing resources
    with sqlite3.connect(database) as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT id FROM resources WHERE creature_id = ?",
            (creature_id,)
        )
        for result in cur.fetchall():
            resourceNametags += ",r:" + str(result[0])

    # Add form data for resources to dictionaries using form nametags
    resources = []
    for nametag in resourceNametags.split(","):
        if nametag != "":
            resource = {"nametag" : nametag,
                        "name" : request.form.get(nametag + "_name"),
                        "description" : request.form.get(nametag + "_description"),
                        "recharge" : request.form.get(nametag + "_recharge"),
                        "retrieved" : False}
            try:
                resource["max_charges"] = int(request.form.get(nametag + "_max_charges"))
            except:
                resource["max_charges"] = 0
            # Check if all resource form data was succesfully retrieved
            if not None in resource.values():
                resource["retrieved"] = True
            resources.append(resource)

    for resource in resources:
        # Update if resource was pre-existing and still present on the form
        if not resource["nametag"][2:5] == "new" and resource["retrieved"]:
            with sqlite3.connect(database) as conn:
                cur = conn.cursor()
                cur.execute(
                    "UPDATE resources SET name = ?, max_charges = ?, description = ?, recharge = ? WHERE id = ? AND creature_id = ?",
                    (resource["name"], resource["max_charges"], resource["description"], resource["recharge"], resource["nametag"][2:], creature_id)
                )
                conn.commit()
        # Delete if resource was pre-existing and no longer present on the form
        elif not resource["nametag"][2:5] == "new" and not resource["retrieved"]:
            with sqlite3.connect(database) as conn:
                cur = conn.cursor()
                cur.execute(
                    "DELETE FROM resources WHERE id = ? AND creature_id = ?",
                    (resource["nametag"][2:], creature_id)
                )
                conn.commit()
        # Insert if resource is new and present on the form
        elif resource["nametag"][2:5] == "new" and resource["retrieved"]:
            with sqlite3.connect(database) as conn:
                cur = conn.cursor()
                cur.execute(
                    "INSERT INTO resources (name, max_charges, description, recharge, creature_id) VALUES (?, ?, ?, ?, ?)",
                    (resource["name"], resource["max_charges"], resource["description"], resource["recharge"], creature_id)
                )
                conn.commit()


def sql_insert(database, tablename, insert_values, return_variable = None):
    """Insert dict into database as new row"""

    # Variable validation
    if database == None or tablename == None or insert_values == None or len(insert_values) == 0:
        return

    # Build sql statement start
    insert_string = "INSERT INTO " + tablename + " ("
    values_string = "VALUES ("
    parameters = tuple(insert_values.values())

    # Build sql string from dict keys
    first_value = True
    for key in insert_values:
        if not first_value:
            insert_string += ", "
            values_string += ", "
        first_value = False
        insert_string += key
        values_string += "?"

    # Build sql statement end
    sql_string = insert_string + ") " + values_string + ")"

    # Add query for optional return variable
    if return_variable:
        sql_string += " returning " + return_variable

    # Insert dictionary as new database row
    with sqlite3.connect(database) as conn:
        cur = conn.cursor()
        cur.execute(sql_string, parameters)
        if return_variable:
            return_value = cur.fetchone()[0]
        conn.commit()

    # Return variable
    if return_variable:
        return return_value


def sql_update(database, tablename, update_values, update_location):
    """Update database row with dict"""

    # Variable validation
    if database == None or tablename == None or update_values == None or len(update_values) == 0 or update_location == None or len(update_location) == 0:
        return

    # Build sql statement start
    sql_string = "UPDATE " + tablename + " SET "
    parameters = tuple(update_values.values()) + tuple(update_location.values())

    # Build sql string from update dict keys
    first_value = True
    for key in update_values:
        if not first_value:
            sql_string += ", "
        first_value = False
        sql_string += key + " = ?"

    # Build sql statement connector
    sql_string += " WHERE "

    # Build sql string from location dict keys
    first_value = True
    for key in update_location:
        if not first_value:
            sql_string += ", "
        first_value = False
        sql_string += key + " = ?"

    # Update dictionary
    with sqlite3.connect(database) as conn:
        cur = conn.cursor()
        cur.execute(sql_string, parameters)
        conn.commit()