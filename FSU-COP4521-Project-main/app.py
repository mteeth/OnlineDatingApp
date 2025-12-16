from flask import *
from dbConfig import getConnection
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, date
from werkzeug.security import generate_password_hash, check_password_hash
import os
from werkzeug.utils import secure_filename
from flask_socketio import SocketIO, emit, join_room, leave_room
import random


app = Flask(__name__)
socketio = SocketIO(app)
app.secret_key = 'COP4521_GROUP9'
app.config['UPLOAD_FOLDER'] = 'uploads' # where to save uploaded photos

# ------------------------------------------ HELPER FUNCTIONS ----------------------------------------------

# calculates age based on user's given birthdate
def calculateAge(birthdataStr):
    birthdate = datetime.strptime(birthdataStr, "%Y-%m-%d").date()
    today = date.today()
    return today.year - birthdate.year - ((today.month, today.day) < (birthdate.month, birthdate.day))

#returns a compability score based on shared interests and age difference
def calcMatchScore(current, candidate):
    current_tags = set((current['interests'] or "").lower().split(","))
    candidate_tags = set((candidate['interests'] or "").lower().split(","))
    shared_tags = len(current_tags & candidate_tags)
    age_diff = abs(current['age'] - candidate['age'])
    age_score = max(0, 10 - age_diff)
    return shared_tags * 5 + age_score

# checks if uploaded file has an image extension
def allowedFile(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in {'jpg', 'jpeg', 'png'}

# help check if person is authorized to visit certain pages (and with what permissions)
def isUserAuthorized(userId):
    return "user_id" in session and session["user_id"] == userId

# ------------------------------------------ HOME PAGE ----------------------------------------------

@app.route("/")
def home():
    return render_template("home.html")

# ------------------------------------------ CREATE ACCOUNT ----------------------------------------------

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        # get form data from user
        firstName = request.form["first_name"]
        lastName = request.form["last_name"]
        email = request.form["email"]
        rawPassword = request.form["password"]
        hashedPassword = generate_password_hash(rawPassword)
        phone = request.form["phone"]
        birthdate = request.form["birthdate"]
        gender = request.form["gender"]

        # connect to database
        connect = getConnection()
        cursor = connect.cursor()

        # make sure the email address or phone number don't exist already
        cursor.execute("SELECT * FROM users WHERE email = %s OR phone = %s", (email, phone))
        if cursor.fetchone():
            connect.close()
            return "Email or phone already registered."
        
        # insert new user
        cursor.execute("""
            INSERT INTO users (first_name, last_name, email, phone, password, birthdate, gender)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (firstName, lastName, email, phone, hashedPassword, birthdate, gender))

        connect.commit()
        cursor.execute("SELECT LAST_INSERT_ID()")
        userId = cursor.fetchone()[0]

        session["user_id"] = userId # log user in after registration so they can finish their profile

        connect.close()
        return redirect(f"/edit_profile/{userId}")  # redirect the user to finish creating their profile
    
    return render_template("register.html")

# ------------------------------------------ SHOW USER'S OWN PROFILE ----------------------------------------------

@app.route("/profile/<int:userId>")
def userProfile(userId):
    if not isUserAuthorized(userId):
        return redirect("/login")

    connect = getConnection()
    cursor = connect.cursor(dictionary=True)
    # get users info
    cursor.execute("SELECT * FROM users WHERE id = %s", (userId,))
    user = cursor.fetchone()
    # get users photos
    cursor.execute("SELECT * FROM photos WHERE user_id = %s", (userId,))
    photoRows = cursor.fetchall()
    photos = [row["photo_url"] for row in photoRows]

    connect.close()

    if not user:
        return "User not found."
    
    user["age"] = calculateAge(str(user["birthdate"]))  # add calculated age to users info
    
    return render_template("profile.html", user=user, photos=photos)

# ------------------------------------------ EDIT PROFILE ----------------------------------------------

@app.route("/edit_profile/<int:userId>", methods=["GET", "POST"])
def editProfile(userId):
    if not isUserAuthorized(userId):
        return redirect("/login")

    connect = getConnection()
    cursor = connect.cursor(dictionary=True)

    if request.method == "POST":
        bio = request.form.get("bio")
        orientation = request.form.get("orientation")
        selectedInterests = request.form.getlist("interests")
        interestText = ",".join(selectedInterests)

        # update bio, orientation, and interests
        cursor.execute("""
            UPDATE users SET bio = %s, orientation = %s, interests = %s, profile_complete = 1
            WHERE id = %s
        """, (bio, orientation, interestText, userId))
        connect.commit()

        # handle uploaded photos
        photos = request.files.getlist("photos")
        uploadCount = 0
        for photo in photos:
            if photo and allowedFile(photo.filename):
                filename = secure_filename(photo.filename)  # creates and holds a safe file name for the photos
                userFolder = os.path.join(app.config['UPLOAD_FOLDER'], f"user_{userId}")    # builds the path for the users folder in the uploads folder
                os.makedirs(userFolder, exist_ok=True)  # makes the folder if it doesn't exist
                filePath = os.path.join(userFolder, filename)
                photo.save(filePath)

                photoUrl = f"user_{userId}/{filename}"
                cursor.execute(
                    "INSERT INTO photos (user_id, photo_url) VALUES (%s, %s)",
                    (userId, photoUrl)
                )
                uploadCount += 1
        
        connect.commit()
        connect.close()
        return redirect(f"/profile/{userId}")
    
    # if someone visits the edit page show their existing info instead of an empty form
    cursor.execute("SELECT * FROM users WHERE id = %s", (userId,))
    user = cursor.fetchone()
    # get users photos if they have any
    cursor.execute("SELECT photo_url FROM photos WHERE user_id = %s", (userId,))
    photos = [row["photo_url"] for row in cursor.fetchall()]
    # get users interests
    cursor.execute("SELECT interests FROM users WHERE id = %s", (userId,))
    row = cursor.fetchone()
    connect.close()

    presetInterests = [
        "Music", "Sports", "Traveling", "Movies", "TV Shows", "Reading", "Gaming", "Fitness", "Cooking", "Baking", "Art", "Tech", "Nature", "Comedy", "Anime", "Memes"
    ]
    userInterests = row["interests"].split(",") if row["interests"] else []

    return render_template("edit_profile.html", user=user, photos=photos, presetInterests=presetInterests, userInterests=userInterests)

# tells flask to fetch a persons photos from the uploads folder
@app.route('/uploads/<path:filename>')
def uploadedFile(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

# ------------------------------------------ DELETE PHOTO (EDIT PROFILE) ----------------------------------------------

@app.route("/delete_photo", methods=["POST"])
def deletePhoto():
    if "user_id" not in session:
        return redirect("/login")
    
    userId = session["user_id"]
    photoUrl = request.form.get("photo_url")

    if not photoUrl:
        return redirect(f"/edit_profile/{userId}")
    
    connect = getConnection()
    cursor = connect.cursor()

    # delete from database
    cursor.execute("DELETE FROM photos WHERE user_id = %s AND photo_url = %s", (userId, photoUrl))
    connect.commit()
    connect.close()

    # delete from uploads folder
    photoPath = os.path.join(app.config["UPLOAD_FOLDER"], photoUrl)
    if os.path.exists(photoPath):
        os.remove(photoPath)

    return redirect(f"/edit_profile/{userId}")

# ------------------------------------------ LOGIN ----------------------------------------------

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]

        # connect to database and find user by their email
        connect = getConnection()
        cursor = connect.cursor(dictionary=True)
        cursor.execute("SELECT id, password, role, banned FROM users WHERE email = %s", (email,))
        user = cursor.fetchone()
        
        if user and user["banned"]:
            connect.close()
            return "Account has been banned."
        
        connect.close()

        if user and check_password_hash(user["password"], password):
            # store user id and user role in session
            session["user_id"] = user["id"]
            session["role"] = user["role"]
            return redirect("/")
        else:
            # login failure
            return "Invalid email or password"
        
    return render_template("login.html")

# ------------------------------------------ LOGOUT ----------------------------------------------

@app.route("/logout")
def logout():
    # clear the session to log user out
    session.clear()
    return redirect("/")

# ------------------------------------------ BROWSING ----------------------------------------------

@app.route("/browse", methods=["GET", "POST"])
def browse():
    print("Passed Users (session):", session.get("passed_users"))
    userId = session.get("user_id")
    if not userId:
        return redirect("/login")
    
    if "passed_users" not in session:
        session["passed_users"] = []

    connect = getConnection()
    cursor = connect.cursor(dictionary=True)

    if request.method == "POST":
        likedId = request.form.get("liked_id")
        action = request.form.get("action")  # like or pass
        message = request.form.get("message", None)

        if action == "like" and likedId:
            cursor.execute("""
                insert into likes (liker_id, liked_id, message)
                values (%s, %s, %s)
            """, (userId, likedId, message))
        connect.commit()

    # get current user's gender, orientation, and age
    cursor.execute("select * from users where id = %s", (userId,))
    currentUser = cursor.fetchone()
    currentUser["age"] = calculateAge(str(currentUser["birthdate"]))
    gender = currentUser["gender"]
    orientation = currentUser["orientation"]

    passed = session.get("passed_users", [])

    # AI Assisted (placeholders to help the pass users actually be skipped)
    if passed:
        placeholders = ','.join(['%s'] * len(passed))
        passedClause = f"AND u.id NOT IN ({placeholders})"
    else:
        passedClause = ""

    # build orientation-based filters
    if orientation == "straight":
        targetGender = ["female"] if gender == "male" else ["male"]
        targetOrientations = ["straight", "bisexual"]
    elif orientation == "gay":
        targetGender = [gender]
        targetOrientations = ["gay", "bisexual"]
    elif orientation == "bisexual":
        targetGender = ["male", "female"]
        targetOrientations = ["straight", "gay", "bisexual"]
    else:
        targetGender = ["male", "female"]
        targetOrientations = ["straight", "gay", "bisexual"]

    genderSql = ", ".join(["%s"] * len(targetGender))
    orientationSql = ", ".join(["%s"] * len(targetOrientations))

    # query to find potential matches
    if orientation == "bisexual":
        # bisexual men should see: gay men, bisexual men, straight women, & bisexual women
        # bisexual women should see: straight men, bisexual men, gay women, & bisexual women
        query = f"""
            SELECT u.*, timestampdiff(year, u.birthdate, curdate()) as age
            FROM users u
            WHERE u.id != %s 
            AND u.gender IN ({genderSql})
            AND u.orientation IN ({orientationSql})
            AND (
                (u.gender = %s AND u.orientation IN ('gay', 'bisexual')) OR
                (u.gender != %s AND u.orientation IN ('straight', 'bisexual'))
            )
            AND NOT EXISTS (SELECT 1 FROM likes WHERE liker_id = %s AND liked_id = u.id)
            AND NOT EXISTS (SELECT 1 FROM blocks WHERE (blocker_id = %s AND blocked_id = u.id) OR (blocker_id = u.id AND blocked_id = %s))
            {passedClause}
        """
        params = [userId] + targetGender + targetOrientations + [gender, gender, userId, userId, userId]
        if passed:
            params += passed
    else:
        query = f"""
            SELECT u.*, timestampdiff(year, u.birthdate, curdate()) as age
            FROM users u
            WHERE u.id != %s
            AND u.gender IN ({genderSql})
            AND u.orientation IN ({orientationSql})
            AND NOT EXISTS (SELECT 1 FROM likes WHERE liker_id = %s AND liked_id = u.id)
            AND NOT EXISTS (SELECT 1 FROM blocks WHERE (blocker_id = %s AND blocked_id = u.id) OR (blocker_id = u.id AND blocked_id = %s))
            {passedClause}
        """
        params = [userId] + targetGender + targetOrientations + [userId, userId, userId]
        if passed:
            params += passed

    cursor.execute(query, params)
    candidates = cursor.fetchall()

    # use parallelism to score candidates
    def scoreWrapper(candidate):
        return {
            "user": candidate,
            "score": calcMatchScore(currentUser, candidate)
        }

    with ThreadPoolExecutor() as pool:
        results = list(pool.map(scoreWrapper, candidates))

    connect.close()

    if not results:
        return render_template("browse.html", profile=None)

    # randomly select one user from top 5 highest scored candidates
    topCandidates = sorted(results, key=lambda x: x["score"], reverse=True)[:5]

    selected = random.choice(topCandidates)["user"]

    # get photos
    connect = getConnection()
    cursor = connect.cursor(dictionary=True)
    cursor.execute("select photo_url from photos where user_id = %s", (selected["id"],))
    photoRows = cursor.fetchall()
    selected["photos"] = [row["photo_url"] for row in photoRows]
    selected["age"] = calculateAge(str(selected["birthdate"]))
    connect.close()

    return render_template("browse.html", profile=selected)

# ------------------------------------------ GUEST BROWSING ----------------------------------------------
@app.route('/guest_browse')
def guestBrowse():
    print("Viewed IDs (session):", session.get("viewed_ids"))
    connect = getConnection()
    cursor = connect.cursor(dictionary=True)

    # Get the list of already viewed IDs from session (or start fresh)
    viewed_ids = session.get('viewed_ids', [])

    # Build the placeholder string for SQL safely
    placeholders = ','.join(['%s'] * len(viewed_ids)) if viewed_ids else '0'
    query = f"""
        SELECT * FROM users
        WHERE id NOT IN ({placeholders})
        ORDER BY RAND()
        LIMIT 1
    """
    cursor.execute(query, tuple(viewed_ids))  # Pass the actual tuple, not wrapped in another

    user = cursor.fetchone()

    if user:
        user["age"] = calculateAge(str(user["birthdate"]))
        # Save the viewed ID to session so it’s not repeated
        viewed_ids.append(user['id'])
        session['viewed_ids'] = viewed_ids

        # Fetch photos
        cursor.execute("SELECT photo_url FROM photos WHERE user_id = %s", (user['id'],))
        photos = [row['photo_url'] for row in cursor.fetchall()]
        return render_template("guest_view.html", user=user, photos=photos)

    else:
        # No more users to view
        return render_template("guest_view.html", user=None)
    
# ------------------------------------------ PASS USER --------------------------------------------------
@app.route("/pass_user/<int:user_id>", methods=["POST"]) #AI assisted
def pass_user(user_id):
    passed = session.get("passed_users", [])
    if user_id not in passed:
        passed.append(user_id)
    session["passed_users"] = passed
    return redirect("/browse")

# ------------------------------------------ REFRESH BROWSING -------------------------------------------
@app.route("/refresh_browse", methods=["POST"])
def refresh_browse():
    session.pop("passed_users", None)
    return redirect("/browse")

# ------------------------------------------ REFRESH GUEST BROWSING -------------------------------------
@app.route("/refresh_guest", methods=["POST"])
def refresh_guest():
    session.pop("viewed_ids", None)
    return redirect(url_for("guestBrowse"))

# ------------------------------------------ LIKES RECIEVED ----------------------------------------------

@app.route("/likes")
def likesReceived():
    userId = session.get("user_id")
    if not userId:
        return redirect("/login")
    
    connect = getConnection()
    cursor = connect.cursor(dictionary=True)

    cursor.execute("""
        SELECT likes.id AS like_id, users.id AS user_id, users.first_name, users.gender, users.orientation, likes.message, TIMESTAMPDIFF(YEAR, users.birthdate, CURDATE()) AS age
        FROM likes
        JOIN users ON likes.liker_id = users.id
        WHERE likes.liked_id = %s
        AND NOT EXISTS (
            SELECT 1 FROM rejected_likes
            WHERE rejected_likes.liker_id = likes.liker_id AND rejected_likes.liked_id = likes.liked_id
        )
        AND NOT EXISTS (
            SELECT 1 FROM blocks 
            WHERE (blocker_id = %s AND blocked_id = likes.liker_id) OR (blocker_id = likes.liker_id AND blocked_id = %s)
        )
        ORDER BY likes.created_at DESC
    """, (userId, userId, userId))
    likes = cursor.fetchall()
    connect.close()
    return render_template("likes.html", likes=likes)

# ------------------------------------------ VIEW OTHER'S PROFILE ----------------------------------------------

@app.route("/view_profile/<int:userId>")
def viewProfile(userId):
    currentUserId = session.get("user_id")
    if not currentUserId:
        return redirect("/login")

    source = request.args.get("source")
    
    connect = getConnection()
    cursor = connect.cursor(dictionary=True)

    # fetch user info
    cursor.execute("SELECT * FROM users WHERE id = %s", (userId,))
    user = cursor.fetchone()

    if not user:
        connect.close()
        return "User not found."
    
    # fetch photos
    cursor.execute("SELECT photo_url FROM photos WHERE user_id = %s", (userId,))
    photoRows = cursor.fetchall()
    photos = [row["photo_url"] for row in photoRows]
    connect.close()

    user["age"] = calculateAge(str(user["birthdate"]))

    return render_template("view_profile.html", user=user, photos=photos, source=source)

# ------------------------------------------ HANDLING YOUR RESPONSE WHEN A USER LIKES YOU ----------------------------------------------

@app.route("/handle_like_response", methods=["POST"])
def handleLikeResponse():
    if "user_id" not in session:
        return redirect("/login")
    
    likedId = session["user_id"]
    likerId = int(request.form.get("liker_id"))
    action = request.form.get("action")

    connect = getConnection()
    cursor = connect.cursor()

    if action == "match":
        # add matches to table
        user1, user2 = sorted([likedId, likerId])
        cursor.execute("""
            INSERT IGNORE INTO matches (user1_id, user2_id)
            VALUES (%s, %s)
        """, (user1, user2))
        
        #remove from likes
        cursor.execute("DELETE FROM likes WHERE liker_id = %s AND liked_id = %s", (likerId, likedId))

    elif action == "pass":
        # record rejection
        cursor.execute("""
            INSERT INTO rejected_likes (liker_id, liked_id)
            VALUE (%s, %s)
        """, (likerId, likedId))

        # remove from likes too
        cursor.execute("DELETE FROM likes WHERE liker_id = %s AND liked_id = %s", (likerId, likedId))

    connect.commit()
    connect.close()

    return redirect("/likes")

# ------------------------------------------ MATCHES ----------------------------------------------

@app.route("/matches")
def matchesList():
    userId = session.get("user_id")
    if not userId:
        return redirect("/login")
    
    connect = getConnection()
    cursor = connect.cursor(dictionary=True)

    cursor.execute("""
        SELECT m.id AS match_id, u.id AS user_id, u.first_name, u.gender, u.orientation, TIMESTAMPDIFF(YEAR, u.birthdate, CURDATE()) AS age
        FROM matches m
        JOIN users u ON (u.id = CASE
            WHEN m.user1_id = %s THEN m.user2_id
            ELSE m.user1_id END)
        WHERE m.user1_id = %s OR m.user2_id = %s
        AND NOT EXISTS (
            SELECT 1 FROM blocks 
            WHERE (blocker_id = %s AND blocked_id = u.id) OR (blocker_id = u.id AND blocked_id = %s)
        )
        ORDER BY m.matched_at DESC
    """, (userId, userId, userId, userId, userId))

    matches = cursor.fetchall()
    connect.close()

    return render_template("matches.html", matches=matches)

# ------------------------------------------ CHAT W/ MATCH ----------------------------------------------

@app.route("/chat/<int:matchId>")
def chat(matchId):
    userId = session.get("user_id")
    if not userId:
        return redirect("/login")
    
    connect = getConnection()
    cursor = connect.cursor(dictionary=True)

    # check if the match_id is valid and involves the current user
    cursor.execute("""
        SELECT * FROM matches WHERE id = %s AND (user1_id = %s OR user2_id = %s)                   
    """, (matchId, userId, userId))
    match = cursor.fetchone()

    if not match:
        connect.close()
        return "Invalid match or access unauthorized."

    # identify chat partner
    chatPartnerId = match["user2_id"] if match["user1_id"] == userId else match["user1_id"]
    
    # check if either user has blocked the other
    cursor.execute("""
        SELECT 1 FROM blocks 
        WHERE (blocker_id = %s AND blocked_id = %s) OR (blocker_id = %s AND blocked_id = %s)
    """, (userId, chatPartnerId, chatPartnerId, userId))
    
    if cursor.fetchone():
        connect.close()
        return "User has been blocked."
    
    cursor.execute("SELECT first_name FROM users WHERE id = %s", (chatPartnerId,))
    partner = cursor.fetchone()

    # fetch previous messages
    cursor.execute("""
        SELECT * FROM messages WHERE (sender_id = %s AND receiver_id = %s) OR (sender_id = %s AND receiver_id = %s)
        ORDER BY timestamp ASC
    """, (userId, chatPartnerId, chatPartnerId, userId))
    messages = cursor.fetchall()

    connect.close()

    return render_template("chat.html", messages=messages, matchId=matchId, partner=partner, userId = userId)

# ------------------------------------------ SOCKET HANDLING ----------------------------------------------
@socketio.on("send_message")
def handleSendMessage(data):
    senderId = data["sender_id"]
    matchId = data["match_id"]
    content = data["content"]

    # get receiverId based on match
    connect = getConnection()
    cursor = connect.cursor(dictionary=True)
    cursor.execute("SELECT * FROM matches WHERE id = %s", (matchId,))
    match = cursor.fetchone()

    if not match:
        return  #invalid match
    
    receiverId = match["user2_id"] if match ["user1_id"] == senderId else match["user1_id"]
    
    # check if either user has blocked the other
    cursor.execute("""
        SELECT 1 FROM blocks 
        WHERE (blocker_id = %s AND blocked_id = %s) OR (blocker_id = %s AND blocked_id = %s)
    """, (senderId, receiverId, receiverId, senderId))
    
    if cursor.fetchone():
        connect.close()
        return  # blocked user cannot send messages

    # save message to DB
    cursor.execute("""
        INSERT INTO messages (match_id, sender_id, receiver_id, content)
        VALUES (%s, %s, %s, %s)                   
    """, (matchId, senderId, receiverId, content))
    connect.commit()

    # get sender name
    cursor.execute("SELECT first_name FROM users WHERE id = %s", (senderId,))
    senderName = cursor.fetchone()["first_name"]
    connect.close()

    emit("receive_message", {"sender_id": senderId, "sender_name": senderName, "content": content}, room=f"match_{matchId}")

@socketio.on("join_room")
def handleJoinRoom(data):
    room = f"match_{data['match_id']}"
    join_room(room)

@socketio.on("leave_room")
def handleLeaveRoom(data):
    matchId = data["match_id"]
    leave_room(f"match_{matchId}")

# ------------------------------------------ REPORT OTHER USER ----------------------------------------------

@app.route("/report_user", methods=["POST"])
def reportUser():
    reporterId = session.get("user_id")
    reportedId = request.form.get("reported_id")
    reason = request.form.get("reason", "")
    sourcePage = request.form.get("source_page", "browse")  # browse, likes, or matches

    if not reporterId or not reportedId or reporterId == int(reportedId):
        return redirect("/")
    
    reportedId = int(reportedId)
    
    connect = getConnection()
    cursor = connect.cursor()
    
    cursor.execute("""
        INSERT INTO reports (reporter_id, reported_id, reason)
        VALUES (%s, %s, %s)                   
    """, (reporterId, reportedId, reason))
    
    # handle based on source page
    if sourcePage == "browse":
        # act as a pass, also remove from likes if exists, add to rejected_likes
        cursor.execute("DELETE FROM likes WHERE liker_id = %s AND liked_id = %s", (reporterId, reportedId))
        cursor.execute("""
            INSERT INTO rejected_likes (liker_id, liked_id)
            VALUES (%s, %s)
        """, (reporterId, reportedId))
        
    elif sourcePage == "likes":
        # act as a pass
        cursor.execute("DELETE FROM likes WHERE liker_id = %s AND liked_id = %s", (reportedId, reporterId))
        
    elif sourcePage == "matches":
        # act as an unmatch
        cursor.execute("DELETE FROM matches WHERE (user1_id = %s AND user2_id = %s) OR (user1_id = %s AND user2_id = %s)", 
                      (reporterId, reportedId, reportedId, reporterId))
    
    connect.commit()
    connect.close()

    # redirect back to the source page
    if sourcePage == "browse":
        return redirect("/browse")
    elif sourcePage == "likes":
        return redirect("/likes")
    elif sourcePage == "matches":
        return redirect("/matches")
    else:
        return redirect("/")

# ------------------------------------------ BLOCK OTHER USER ----------------------------------------------

@app.route("/block_user", methods=["POST"])
def blockUser():
    blockerId = session.get("user_id")
    blockedId = request.form.get("blocked_id")
    sourcePage = request.form.get("source_page", "browse")  # browse, likes, or matches

    if not blockerId or not blockedId or blockerId == int(blockedId):
        return redirect("/")
    
    blockedId = int(blockedId)
    
    connect = getConnection()
    cursor = connect.cursor()

    # add to blocks table
    cursor.execute("INSERT IGNORE INTO blocks (blocker_id, blocked_id) VALUES (%s, %s)", (blockerId, blockedId))

    # remove likes, matches, and messages
    cursor.execute("DELETE FROM likes WHERE (liker_id = %s AND liked_id = %s) OR (liker_id = %s AND liked_id = %s)", (blockerId, blockedId, blockedId, blockerId))
    cursor.execute("DELETE FROM matches WHERE (user1_id = %s AND user2_id = %s) OR (user1_id = %s AND user2_id = %s)", (blockerId, blockedId, blockedId, blockerId))

    connect.commit()
    connect.close()

    # redirect back to the source page
    if sourcePage == "browse":
        return redirect("/browse")
    elif sourcePage == "likes":
        return redirect("/likes")
    elif sourcePage == "matches":
        return redirect("/matches")
    else:
        return redirect("/")
# ------------------------------------------ BLOCKED USERS ------------------------------------------------
@app.route("/blockedUsers")
def blockedUsers():
    userId = session.get("user_id")
    if not userId:
        return redirect("/")
    
    connect = getConnection()
    cursor = connect.cursor(dictionary=True)

    query = """
        SELECT u.id, u.first_name, u.last_name, u.email
        FROM blocks b
        JOIN users u ON u.id = b.blocked_id
        WHERE b.blocker_id = %s
    """
    cursor.execute(query, (userId,))
    blocked = cursor.fetchall()

    cursor.close()
    return render_template("blocked_users.html", blocked=blocked)

# ------------------------------------------ UNBLOCK USER -------------------------------------------------
@app.route("/unblock_user", methods=["POST"])
def unblockUser():
    blockerId = session.get("user_id")
    blockedId = request.form.get("blocked_id")

    if not blockerId or not blockedId or blockerId == int(blockedId):
        return redirect("/")
    
    connect = getConnection()
    cursor = connect.cursor()
    cursor.execute("DELETE FROM blocks WHERE blocker_id = %s AND blocked_id = %s", (blockerId, blockedId))
    connect.commit()
    cursor.close()

    return redirect("/blockedUsers")


# ------------------------------------------ UNMATCH W/ USER ----------------------------------------------

@app.route("/unmatch/<int:matchId>", methods=["POST"])
def unmatch(matchId):
    userId = session.get("user_id")

    connect = getConnection()
    cursor = connect.cursor(dictionary=True)

    cursor.execute("SELECT * FROM matches WHERE id = %s", (matchId,))
    match = cursor.fetchone()

    if not match or (userId != match["user1_id"] and userId != match ["user2_id"]):
        connect.close()
        return redirect("/matches")

    cursor.execute("DELETE FROM matches WHERE id = %s", (matchId,))
    connect.commit()
    connect.close()

    return redirect("/matches")

# ------------------------------------------ MODERATOR DASHBOARD ----------------------------------------------

@app.route("/moderator/dashboard")
def moderatorDashboard():
    userId = session.get("user_id")
    if not userId:
        return redirect("/login")
    
    connect = getConnection()
    cursor = connect.cursor(dictionary=True)

    cursor.execute("SELECT role FROM users WHERE id = %s", (userId,))
    roleResult = cursor.fetchone()
    if not roleResult or roleResult["role"] != "moderator":
        connect.close()
        return "Access Denied"

    # get reports
    cursor.execute("""
        SELECT reports.id AS report_id, u1.first_name AS reporter_name, u2.first_name AS reported_name, 
               reports.reported_id, u2.banned AS reported_banned, reports.reason, reports.created_at
        FROM reports
        JOIN users u1 ON reports.reporter_id = u1.id
        JOIN users u2 ON reports.reported_id = u2.id
        ORDER BY reports.created_at DESC
    """)
    reports = cursor.fetchall()
    connect.close()

    return render_template("moderator_dashboard.html", reports=reports)

# ------------------------------------------ MODERATOR/ADMIN - BAN USER ----------------------------------------------

@app.route("/moderator/ban_user/<int:userId>", methods=["POST"])
def banUser(userId):
    moderatorId = session.get("user_id")
    connect = getConnection()
    cursor = connect.cursor(dictionary=True)

    #check for moderator access
    cursor.execute("SELECT role FROM users where id = %s", (moderatorId,))
    role = cursor.fetchone()
    if not role or role["role"] not in ["moderator", "admin"]:
        connect.close()
        return "Access Denied"
    
    # set banned status
    cursor.execute("UPDATE users SET banned = 1 WHERE id = %s", (userId,))
    connect.commit()
    connect.close()

    if role["role"] == "admin":
        return redirect("/admin/dashboard")
    return redirect("/moderator/dashboard")

# ------------------------------------------ MODERATOR/ADMIN - UNBAN USER ----------------------------------------------

@app.route("/moderator/unban_user/<int:userId>", methods=["POST"])
def unbanUser(userId):
    moderatorId = session.get("user_id")
    connect = getConnection()
    cursor = connect.cursor(dictionary=True)

    #check for moderator access
    cursor.execute("SELECT role FROM users where id = %s", (moderatorId,))
    role = cursor.fetchone()
    if not role or role["role"] not in ["moderator", "admin"]:
        connect.close()
        return "Access Denied"
    
    # set unbanned status
    cursor.execute("UPDATE users SET banned = 0 WHERE id = %s", (userId,))
    connect.commit()
    connect.close()

    if role["role"] == "admin":
        return redirect("/admin/dashboard")
    return redirect("/moderator/dashboard")

# ------------------------------------------ MODERATOR/ADMIN - DELETE REPORT ----------------------------------------------

@app.route("/moderator/delete_report/<int:reportId>", methods=["POST"])
def deleteReport(reportId):
    userId = session.get("user_id")
    if not userId:
        return redirect("/login")
    connect = getConnection()
    cursor = connect.cursor(dictionary=True)
    cursor.execute("SELECT role FROM users WHERE id = %s", (userId,))
    role = cursor.fetchone()
    if not role or role["role"] not in ["moderator", "admin"]:
        connect.close()
        return "Access Denied"
    
    cursor.execute("DELETE FROM reports WHERE id = %s", (reportId,))
    connect.commit()
    connect.close()

    if role["role"] == "admin":
        return redirect("/admin/dashboard")
    return redirect("/moderator/dashboard")

# ------------------------------------------ ADMIN DASHBOARD ----------------------------------------------
@app.route("/admin/dashboard")
def adminDashboard():
    userId = session.get("user_id")
    if not userId:
        return redirect("/login")
    
    connect = getConnection()
    cursor = connect.cursor(dictionary=True)

    cursor.execute("SELECT role FROM users WHERE id = %s", (userId,))
    roleResult = cursor.fetchone()
    if not roleResult or roleResult["role"] != "admin":
        connect.close()
        return "Access Denied"

    cursor.execute("SELECT * FROM users ORDER BY created_at DESC")
    users = cursor.fetchall()

    # get reports
    cursor.execute("""
        SELECT reports.id AS report_id, u1.first_name AS reporter_name, u2.first_name AS reported_name, 
               reports.reported_id, u2.banned AS reported_banned, reports.reason, reports.created_at
        FROM reports
        JOIN users u1 ON reports.reporter_id = u1.id
        JOIN users u2 ON reports.reported_id = u2.id
        ORDER BY reports.created_at DESC
    """)
    reports = cursor.fetchall()
    connect.close()

    return render_template("admin_dashboard.html", users=users, reports=reports)

# ------------------------------------------ ADMIN VIEW MESSAGES ----------------------------------------------
@app.route("/admin/messages/<int:userId>")
def adminViewMessages(userId):
    adminId = session.get("user_id")
    if not adminId:
        return redirect("/login")

    connect = getConnection()
    cursor = connect.cursor(dictionary=True)
    cursor.execute("SELECT role FROM users WHERE id = %s", (adminId,))
    role = cursor.fetchone()
    
    if not role or role["role"] != "admin":
        connect.close()
        return "Access Denied"

    cursor.execute("""
        SELECT m.*, u1.first_name AS sender_name, u2.first_name AS receiver_name
        FROM messages m
        JOIN users u1 ON m.sender_id = u1.id
        JOIN users u2 ON m.receiver_id = u2.id
        WHERE m.sender_id = %s OR m.receiver_id = %s
        ORDER BY m.timestamp DESC
    """, (userId, userId))
    
    messages = cursor.fetchall()
    connect.close()

    return render_template("admin_messages.html", messages=messages, targetUserId=userId)


# ------------------------------------------ ADMIN EDIT USER PROFILE ----------------------------------------------
@app.route("/admin/edit_user/<int:userId>", methods=["GET", "POST"])
def adminEditUser(userId):
    adminId = session.get("user_id")
    if not adminId:
        return redirect("/login")

    connect = getConnection()
    cursor = connect.cursor(dictionary=True)
    cursor.execute("SELECT role FROM users WHERE id = %s", (adminId,))
    role = cursor.fetchone()

    if not role or role["role"] != "admin":
        connect.close()
        return "Access Denied"

    if request.method == "POST":
        first_name = request.form.get("first_name")
        last_name = request.form.get("last_name")
        bio = request.form.get("bio")
        orientation = request.form.get("orientation")

        cursor.execute("""
            UPDATE users 
            SET first_name = %s, last_name = %s, bio = %s, orientation = %s 
            WHERE id = %s
        """, (first_name, last_name, bio, orientation, userId))
        connect.commit()
        connect.close()
        return redirect("/admin/dashboard")

    cursor.execute("SELECT * FROM users WHERE id = %s", (userId,))
    user = cursor.fetchone()
    
    # get user's photos
    cursor.execute("SELECT photo_url FROM photos WHERE user_id = %s", (userId,))
    photos = [row["photo_url"] for row in cursor.fetchall()]
    connect.close()
    
    return render_template("admin_edit_user.html", user=user, photos=photos)

# ------------------------------------------ ADMIN DELETE PHOTO ----------------------------------------------

@app.route("/admin/delete_photo/<int:userId>", methods=["POST"])
def adminDeletePhoto(userId):
    adminId = session.get("user_id")
    if not adminId:
        return redirect("/login")

    connect = getConnection()
    cursor = connect.cursor(dictionary=True)
    cursor.execute("SELECT role FROM users WHERE id = %s", (adminId,))
    role = cursor.fetchone()

    if not role or role["role"] != "admin":
        connect.close()
        return "Access Denied"
    
    photoUrl = request.form.get("photo_url")
    if not photoUrl:
        connect.close()
        return redirect(f"/admin/dashboard/{userId}")
    
    #delete photo from database
    cursor.execute("DELETE FROM photos WHERE user_id = %s AND photo_url = %s", (userId, photoUrl))
    connect.commit()
    connect.close()

    #delete photo from uploads folder
    photoPath = os.path.join(app.config["UPLOAD_FOLDER"], photoUrl)
    if os.path.exists(photoPath):
        os.remove(photoPath)

    return redirect(f"/admin/edit_user/{userId}")

# ------------------------------------------ DELETE ACCOUNT ------------------------------------
@app.route("/delete_profile", methods=["POST"])
def delete_profile():
    userId = session.get("user_id")
    if not userId:
        return redirect("/login")

    connect = getConnection()
    cursor = connect.cursor()
    
    # delete user's photos
    cursor.execute("DELETE FROM photos WHERE user_id = %s", (userId,))

    # delete likes, matches, messages, reports and blocks
    cursor.execute("DELETE FROM likes WHERE liker_id = %s OR liked_id = %s", (userId, userId))
    cursor.execute("DELETE FROM matches WHERE user1_id = %s OR user2_id = %s", (userId, userId))
    cursor.execute("DELETE FROM messages WHERE sender_id = %s OR receiver_id = %s", (userId, userId))
    cursor.execute("DELETE FROM blocks WHERE blocker_id = %s OR blocked_id = %s", (userId, userId))
    cursor.execute("DELETE FROM reports WHERE reporter_id = %s OR reported_id = %s", (userId, userId))
    cursor.execute("DELETE FROM rejected_likes WHERE liker_id = %s OR liked_id = %s", (userId, userId))
    
    # delete user from users table
    cursor.execute("DELETE FROM users WHERE id = %s", (userId,))

    connect.commit()
    connect.close()

    # clear the session
    session.clear()

    return redirect("/")

# ------------------------------------ ADMIN DELETE ACCOUNT ------------------------------------
@app.route("/admin/delete_user/<int:userId>", methods=["POST"])
def adminDeleteUser(userId):
    adminId = session.get("user_id")
    if not adminId:
        return redirect("/login")

    connect = getConnection()
    cursor = connect.cursor(dictionary=True)
    cursor.execute("SELECT role FROM users WHERE id = %s", (adminId,))
    role = cursor.fetchone()

    if not role or role["role"] != "admin":
        connect.close()
        return "Access Denied"
    
    # delete user's photos
    cursor.execute("DELETE FROM photos WHERE user_id = %s", (userId,))

    # delete likes, matches, messages, reports and blocks
    cursor.execute("DELETE FROM likes WHERE liker_id = %s OR liked_id = %s", (userId, userId))
    cursor.execute("DELETE FROM matches WHERE user1_id = %s OR user2_id = %s", (userId, userId))
    cursor.execute("DELETE FROM messages WHERE sender_id = %s OR receiver_id = %s", (userId, userId))
    cursor.execute("DELETE FROM blocks WHERE blocker_id = %s OR blocked_id = %s", (userId, userId))
    cursor.execute("DELETE FROM reports WHERE reporter_id = %s OR reported_id = %s", (userId, userId))
    cursor.execute("DELETE FROM rejected_likes WHERE liker_id = %s OR liked_id = %s", (userId, userId))
    
    # delete user from users table
    cursor.execute("DELETE FROM users WHERE id = %s", (userId,))

    connect.commit()
    connect.close()

    return redirect("/admin/dashboard")
# ------------------------------------------ MAIN ----------------------------------------------

if __name__ == '__main__':
    socketio.run(app, debug=True)