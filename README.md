n online dating web application that makes use of front-end and back-end libraries

A lack of simple and completely free ways to meet and connect with other people. A lot of dating platforms have a lot of features hidden behind paywalls. Ours is entirely free and we show users other users based similar interests. We also take users ages into account when showing potential matches, so they're more likely to connect with someone in a similar stage of life.

The moderator and admin dashboards only show on the home page to users who have their role set to 'admin' or 'moderator' in the SQL database. You match with another user in the "See Who Likes You" page if someone liked you first or you may send a like and hope to get matched in the "Start Matching" page The chatting functionality is only available to users who have matched together.

STANDARD PYTHON LIBRARIES os random datetime concurrent.futures.ThreadPoolExecutor

NON-STANDARD PYTHON LIBRARIES mysql.connector Flask Flask-SocketIO Werkzeug.security Werkzeug.utils

DOCUMENTATION Flask Documentation - For building web routes, handling sessions, and templates MySQL Connector/Python Developer Guide - For interacting with our MySQL database Werkzeug Documentation - for password hashing and creating secure filenames for photos Flask-SocketIO Documentation - WebSocket Support for chatting feature

DATABASE MySQL - Used a relational database to store all user data. Tables include: users, photos, likes, rejected_likes, matches, messages, blocks, & reports

AI TOOLS Copilot - Generating CSS and JavaScript for use with sockets. Generating another JavaScript function to hide the text box for the report button

MISC. Pexels - Stock images to use while testing users profiles and anywhere a profile is shown in the application

Blocked Users Page - A page that allows users to see who they have blocked and gives the user the ability to unblock or report any user they have blocked.

Moderator Dashboard - Allows moderators to view reports and take action on said reports. Moderator dashboard shows who made the report, who the report was against, the reason the user reported the other, the date the report was made, reported users current ban status, and buttons to either ban the user or dismiss the report.

Admin Dashboard - Allows admins to see a table of all users. This tables shows users full names, emails, and roles. The table also has actions for admins to edit a users profile, view a users messages, and delete a user. The admin dashboard also has the moderator dashboards reports table below it.

Trey - Login/Logout functionality, Profiles and editing of profiles, Likes, Matches, Mod Dashboard

Martin - Browsing functionality, viewing blocked list and unblocking users, Admin dasboard

Gerrell - Guest functionality, delete profile (user and admin) functionality, fixed browsing, blocked list and unblocking.
