# This file is part of TallyBot (https://github.com/sagrawalx/tallybot)

import string
import yaml
import os
from datetime import datetime
from zulip_bots.lib import BotHandler
from labelingscheme import *
from userlist import *

class TallyBotHandler:
    def usage(self) -> str:
        return """
        I'm a Zulip bot. I respond via private message to stream messages I'm 
        tagged in, and to private messages sent to me. A private message sent 
        to me must either contain the short specifier (eg, 'sp23') or the full 
        name (eg, 'Spring 2023, Math 11') for the class stream you're 
        interested in getting data about. 
        
        If you are a student (ie, a regular member in the Zulip organization), 
        you will get information about the number of on-time and valid reading
        questions you've submitted to the class stream. 
        
        If you are an instructor or TA (ie, a moderator or administrator in the
        Zulip organization): 
        
        * If, after removing the stream specifier, the message is nonempty and 
          there is a nonempty subset of students whose names contain the 
          message as a substring, I will return counts for just those students 
          in verbose format.
        
        * Otherwise, I will return counts for *all* students in CSV format.
        """
    
    def handle_message(self, message: dict, bot_handler: BotHandler) -> None:
        try: 
            # Extract client
            client = bot_handler._client
            
            # Delete all stream messages mentioning this bot
            clear_stream_mentions(client)
            
            # Minimize message content
            message["content"] = minimize(message["content"])
            
            # Get interlocutor information
            interloc = client.get_user_by_id(message["sender_id"])["user"]
            
            # Should be commented out when deployed
            # if interloc["role"] > 300:
            #     response = "I am offline."
            #     respond(client, interloc, response)
            #     return None
            
            # Delete private message history, if requested
            if "clear" in message["content"]:
                clear_pm_history(client, interloc)
                return None
            
            # Collect configuration data
            config_file = bot_handler.open("config.yml")
            config = get_config(config_file, message)
            config_file.close()
            
            if config is None: 
                response = "No configuration data was matched. You must either "\
                "(a) tag me in a stream message in the class stream that you're "\
                "interested in, or "\
                "(b) send me a private message containing the short specifier "\
                "(eg, 'wi23') or the full name (eg, 'Winter 2023, Math 187A') "\
                "for the class stream that you're interested in. Please try again."
                
                respond(client, interloc, response)
                return None
            
            # Initialize user database
            users = UserList(bot_handler, config["stream_specifier"])
            
            # Use configuration data to instantiate the labeling scheme
            scheme = eval(config.pop("labeling_scheme", "StandardLabelingScheme"))
            assert issubclass(scheme, LabelingScheme)
            labeling = scheme(config.pop("labeler_config"))
            
            # Get messages
            messages = get_messages(bot_handler, users, config, labeling)
            
            if messages is None:
                response = "There was an unexpected problem. Please try again, "\
                "or reach out to a moderator."
                respond(client, interloc, response)
                return None
            
            # Tally messages
            tally = do_tally(messages)
            
            # If interlocutor is a member, return verbose individual count
            if interloc["role"] > 300:
                response = individual_count(tally, interloc["user_id"])
            # Otherwise:
            else:
                # Search user list for names that contain the message
                matches = users.find(message["content"], is_lower=True)
                # If no matching users are found, return all counts
                if len(matches) == 0:
                    response = all_counts(tally, users)
                # Else return all matching counts in verbose format
                else:
                    response = ""
                    for m in matches:
                        response += m["full_name"] + "\n"
                        response += individual_count(tally, m["user_id"])
                        response += "\n\n"
            
            # Issue response
            respond(client, interloc, response) 
        
        # KeyError only if Zulip API returns something unexpected 
        except KeyError as k:
            print(f"The key {k} raised a KeyError. This shouldn't happen..." )
        
        # Return
        finally:
            return None

handler_class = TallyBotHandler

def clear_pm_history(client, interloc: dict) -> None:
    """
    Clear the one-on-one private message history with the interlocutor.
    """
    batch = []
    found_oldest = False
    while not found_oldest: 
        # Run request
        anchor = "newest" if len(batch) == 0 else batch[-1]["id"]
        request = {
            "anchor": anchor,
            "num_before": 5000,
            "num_after": 0,
            "narrow": [
                {"operator": "pm-with", "operand": interloc["email"]}
            ]
        }
        result = client.get_messages(request)
        found_oldest = result["found_oldest"]
        batch = result["messages"]
        
        # Delete messages
        for m in batch:
            client.delete_message(m["id"])
            
def clear_stream_mentions(client) -> None:
    """
    Delete all stream messages mentionining the bot. 
    """
    batch = []
    found_oldest = False
    while not found_oldest: 
        # Run request
        anchor = "newest" if len(batch) == 0 else batch[-1]["id"]
        request = {
            "anchor": "newest",
            "num_before": 5000,
            "num_after": 0,
            "narrow": [{"operator": "is", "operand": "mentioned"}]
        }
        result = client.get_messages(request)
        batch = result["messages"]
        found_oldest = result["found_oldest"]
        
        # Delete messages
        for m in batch:
            if m["type"] == "stream":
                client.delete_message(m["id"])

def respond(client, interloc: dict, response: str, num_lines: int = 150) -> None:
    """
    Uses the given client to send the interlocutor a private message containing 
    the given response. 
    """
    i = 0
    lines = 0
    msg = ""
    while i < len(response):
        if lines < num_lines:
            msg += response[i]
            if response[i] == "\n":
                lines += 1
        if lines == num_lines or i+1 == len(response):
            request = {
                "type": "private",
                "to": [interloc["user_id"]],
                "content": msg,
            }
            client.send_message(request)
            lines = 0
            msg = ""
        i += 1

def minimize(x: str) -> str:
    """
    Converts a string to lower case, removes all punctuation, and strips any
    trailing whitespace. 
    """
    punc_remover = str.maketrans("", "", string.punctuation)
    return x.lower().translate(punc_remover).strip()
    
def get_config(config_file, message: dict) -> dict:
    """
    Extract configuration data from the message. If the message was a stream
    message, configuration data is extracting using the name of the stream. If
    message was a private message, the content of the message must contain a
    specifying information (short specifier or full stream name). If nothing
    matches, returns None. 
    
    If the message is a private message and contains a valid stream specifier,
    this method will modify message["content"] by removing that stream 
    specifier from the string and then stripping any trailing whitespace. 
    """
    configs = yaml.safe_load(config_file)
    
    # If stream message:
    if message["type"] == "stream":
        stream_name = message["display_recipient"]
        for c in configs:
            if c["stream_name"] == stream_name:
                return c
            
    # Else should be a private message:
    elif message["type"] == "private":
        for c in configs:
            # List of possible specifying strings to look for in the message
            names = [c["stream_specifier"], minimize(c["stream_name"])]
            
            # For each possible specifying string...
            for x in names:
                # Try removing that specifying string
                m = message["content"].replace(x, "").strip()
                
                # If something was actually removed, a match was found!
                if len(m) < len(message["content"]):
                    # Truncate the message content by removing the match
                    message["content"] = m
                    
                    # Return the configuration data
                    return c
    
    # If no configuration data was matched ...         
    return None
    
def get_messages(bot_handler, users: UserList, config: dict, labeling: LabelingScheme) -> list:
    """
    Returns a list of all messages by members whose topic has a match for the
    labeling scheme, ie, for which the topic_match() method of the given
    labeling scheme returns something other than None. 
    """
    # Initialize backup file
    name = f"data_msgs_{config['stream_specifier']}.csv"
    filepath = os.path.join(bot_handler._root_dir, name)
    client = bot_handler._client
      
    # Create backup file if needed
    csvfile = open(filepath, "a", newline="")
    csvfile.close()
    
    # Load messages from backup file
    messages = {}
    with open(filepath, newline="") as csvfile:
        reader = DictReader(csvfile)
        for msg in reader:
            msg["id"] = int(msg["id"])
            msg["sender_id"] = int(msg["sender_id"])
            msg["timestamp"] = datetime.fromisoformat(msg["timestamp"])
            msg["on_time"] = msg["on_time"] == "True"
            msg["valid"] = msg["valid"] == "True"
            messages[msg["id"]] = msg
    
    # Get messages from client    
    batch = []
    found_oldest = False
    while not found_oldest: 
        # Run request for batch of messages
        anchor = "newest" if len(batch) == 0 else batch[-1]["id"]
        request = {
            "anchor": anchor,
            "apply_markdown": "false",
            "num_before": 5000,
            "num_after": 0,
            "narrow": [
                {"operator": "stream", "operand": config["stream_name"]}
            ]
        }
        result = client.get_messages(request)
        batch = result["messages"]
        found_oldest = result["found_oldest"]
        
        # Go through result messages to extract relevant information
        for m in batch:
            keep = True
            
            # Drop bot messages
            if m["sender_full_name"] == "Notification Bot":
                keep = False
            else:
                # Drop moderator messages
                sender = users.get(m["sender_id"])
                if sender["role"] <= 300:
                    keep = False
                else: 
                    # Drop messages whose topics don't match labeling scheme 
                    label = labeling.topic_match(m["subject"])
                    if label is None:
                        keep = False
            
            # Collect data from kept messages
            if keep:
                # Determine if message was on time
                timestamp = datetime.fromtimestamp(m["timestamp"])
                
                # Check to see if there's in invalid_emoji reaction
                valid = True
                for r in m["reactions"]:
                    if r["emoji_name"] == config["invalid_emoji"]:
                        # Check to see if the reactor was a moderator
                        reactor = users.get(r["user"]["id"])
                        if reactor["role"] <= 300:
                            valid = False
                            break
                
                # Consolidate relevant information
                msg = {
                    "id" : m["id"], 
                    "sender_id" : sender["user_id"], 
                    "sender_name" : sender["full_name"],
                    "sender_email" : sender["delivery_email"],
                    "label" : label.label(),
                    "content" : m["content"],
                    "timestamp" : timestamp,
                    "on_time" : (timestamp <= label.deadline()),
                    "valid" : valid
                }
                
                # Add message to message list
                messages[m["id"]] = msg
    
    # Write data to file
    field_names = ["id", "sender_id", "sender_name", "sender_email", "label", "content", "timestamp", "on_time", "valid"]
    with open(filepath, "w", newline="") as csvfile:
        writer = DictWriter(csvfile, field_names)
        writer.writeheader()
        writer.writerows(messages.values())
    
    # Return
    return messages.values()
    
def do_tally(messages: list) -> dict:
    """
    Tallies the messages and returns a dict. 
    
    If tally is the name of the dict being returned, the keys of tally are the 
    user ids that appear in the input list of messages. If x is such a user id, 
    then tally[x] is again a dict with two keys. 
    
    - tally[x]["credit"] is a list of the assignment labels for which the user
      with user id x had at least one on-time and valid post. 
    - tally[x]["no_credit"] is a list of the assignment labels for which the
      user with user id x had only late or invalid posts. 
    """
    # Initial tally of all messages
    initial = {}
    for m in messages:
        x = m["sender_id"]
        a = m["label"]
        if x not in initial.keys():
            initial[x] = {}
        if a not in initial[x].keys():
            initial[x][a] = False
        initial[x][a] = initial[x][a] or (m["on_time"] and m["valid"])
    
    # Consolidate tallies as lists
    tally = {}    
    for x in initial.keys():
        tally[x] = {}
        tally[x]["credit"] = [a for a, v in initial[x].items() if v]
        tally[x]["no_credit"] = [a for a, v in initial[x].items() if not v]
    
    # Return    
    return tally
    
def individual_count(tally: dict, interloc_id: int) -> str:
    """
    Return the total count, the contributing posts, and the non-contributing
    posts of the interlocutor as a string. The input should be a dict of the 
    form that is output by the tally method above. 
    """
    # Extract interlocutor's data from the tally
    interloc_tally = tally.get(interloc_id, {"credit": [], "no_credit": []})
    
    # Generate verbose response
    response = f"Current RQ Count: {len(interloc_tally['credit'])}"
    
    if len(interloc_tally["credit"]) > 0:
        response += f"\nOn-time and Valid RQs: "
        response += ", ".join(interloc_tally["credit"])
    if len(interloc_tally["no_credit"]) > 0:
        response += f"\nLate or Invalid RQs: "
        response += ", ".join(interloc_tally["no_credit"])
    
    # Return
    return response
    
def all_counts(tally: dict, users: UserList) -> str:
    """
    Return a list of names, emails, and counts as CSV. If verbose is True,
    it also outputs a list of assignment labels for which the user got credit, 
    and a list of assignment labels for which the user did not get credit. 
    
    The first argument should be a dict as output by the tally method. 
    """
    # CSV header
    response = "name,email,count"
    response += "\n"
    
    # CSV content
    for x in tally.keys():
        u = users.get(x)
        name = u["full_name"]
        email = u["delivery_email"]
        count = len(tally[x]["credit"])
        response += f"{name},{email},{count}\n"
    
    # Return  
    return response
    
