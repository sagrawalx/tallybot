# This file is part of TallyBot (https://github.com/sagrawalx/tallybot)

import os
from csv import DictReader, DictWriter

class UserList:
    """
    A UserList object maintains a list of users active on each stream. 
    
    It is essentially a dict, with keys being integer user ids and values
    being dictionaries that contain information about each user. So far, the
    value dicts contain the following fields:
    
    - "user_id" -- The user id is repeated here
    - "email" -- The email address of the user in the Zulip organization
    - "role" -- The role type of user, as returned by Zulip
    - "delivery_email" -- The personal email address of the user
    - "full_name" -- The full name of the user
    
    To initialize this dict, a local file is read. However, if the get
    method requests a user_id that is not in the dict, we request the relevant
    data from the Zulip API. We then update the local file and the dict
    in memory.
    """
    field_names = ["user_id", "email", "role", "delivery_email", "full_name"]

    def __init__(self, bot_handler, label):
        # Initialize
        name = f"data_users_{label}.csv"
        self.filepath = os.path.join(bot_handler._root_dir, name)
        self.client = bot_handler._client
        
        # Create file if needed
        csvfile = open(self.filepath, "a", newline="")
        csvfile.close()
        
        # Load data from file
        self.users = {}
        with open(self.filepath, newline="") as csvfile:
            reader = DictReader(csvfile)
            for user in reader:
                user["user_id"] = int(user["user_id"])
                user["role"] = int(user["role"])
                self.users[user["user_id"]] = user
        
        # If no users were found, initialize file with header line
        if len(self.users) == 0:
            with open(self.filepath, "w", newline="") as csvfile:
                writer = DictWriter(csvfile, self.field_names)
                writer.writeheader()
        
    def get(self, user_id):
        """
        Get user information. 
        
        Use the list in memory (read from a file) if possible. Otherwise,
        make the request using the Zulip API. 
        """
        user_id = int(user_id)
        # Return from exisiting data if possible
        if user_id in self.users.keys():
            return self.users[user_id]
        # Otherwise, request from client and store
        else:
            return self.get_from_client(user_id)
        
    def get_from_client(self, user_id):
        """
        Request user information using the client. Add the result to the
        existing list in memory, and return the data. 
        """
        # Request and filter
        user = self.client.get_user_by_id(user_id)["user"]
        user = { k: user[k] for k in self.field_names }
        
        # Write data to file
        with open(self.filepath, "a", newline="") as csvfile:
            writer = DictWriter(csvfile, self.field_names)
            writer.writerow(user)
        
        # Append data to list and return
        self.users[int(user_id)] = user
        
        return user
        
    def keys(self):
        """
        Return an iterator that goes through the list of user ids of users
        in this user list.
        """
        return self.users.keys()
    
    
