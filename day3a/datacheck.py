#Since we are using a sqlite DB to store information, 
# Let's have a quick peek to see how information is stored.

# import sqlite3

# def check_data_in_db():
#     with sqlite3.connect("my_agent_data.db") as connection:
#         cursor = connection.cursor()
#         result = cursor.execute(
#             "select app_name, session_id, author, content from events"
#         )
#         print([_[0] for _ in result.description])
#         for each in result.fetchall():
#             print(each)


# check_data_in_db()

#There is no author column and no content column. 
# Those fields exist, but only inside the JSON blob stored in event_data
#  — as you saw when you parsed it in Python earlier 
# ("author": "text_chat_bot", "content": {...}). 
# SQLite can't query into JSON text as if it were real columns unless 
# you explicitly use JSON functions.

import sqlite3
import json

def check_data_in_db():
    with sqlite3.connect("my_agent_data.db") as connection:
        cursor = connection.cursor()
        result = cursor.execute(
            "select app_name, session_id, event_data from events"
        )
        for app_name, session_id, event_data in result.fetchall():
            data = json.loads(event_data)
            author = data.get("author")
            content = data.get("content")
            print(app_name, session_id, author, content)

check_data_in_db()