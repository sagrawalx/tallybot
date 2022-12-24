import string
import os
import yaml
import zulip
from datetime import datetime
from zulip_bots.lib import BotHandler
from labelingscheme import *

class TallyBotHandler:
    def usage(self) -> str:
        return """
        I'm a Zulip bot. I respond via private message to stream messages I'm 
        tagged in, and to private messages sent to me. A private message sent 
        to me must either contain the short specifier (eg, 'wi23') or the full 
        name (eg, 'Winter 2023, Math 187A') for the class stream you're 
        interested in getting data about. 
        
        If you are a student (ie, a regular member in the Zulip organization), 
        you will get information about the number of on-time and valid reading
        questions you've submitted to the class stream. 
        
        If you are an instructor or TA (ie, a moderator or administrator in the
        Zulip organization): 
        
        * If your message contains a reading assignment label (eg, 'w1fri'), I
          will return all reading questions for that day (as a bulleted list).
        
        * Otherwise, I will return scores for all students who have submitted
          reading questions to the relevant stream (in CSV format).
        """
    
    def handle_message(self, message: dict, bot_handler: BotHandler) -> None:
        try: 
            # Extract client
            client = bot_handler._client
            
            # Minimize message content
            message["content"] = minimize(message["content"])
            
            # Get interlocutor information
            interloc: dict = client.get_user_by_id(message["sender_id"])["user"]
               
            # Delete interlocutors's message if stream message
            # if message["type"] == "stream":
            #     wrap(client.delete_message(message["id"]))
            
            # Delete all stream messages mentioning this bot
            clear_stream_mentions(client)
            
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
            
            # Use configuration data to instantiate the labeling scheme
            scheme = eval(config.pop("labeling_scheme", "StandardLabelingScheme"))
            assert issubclass(scheme, LabelingScheme)
            labeling = scheme(config.pop("labeler_config"))
            
            # Get messages
            messages = get_messages(client, config, labeling)
            
            if messages is None:
                response = "There was an unexpected problem. Please try again, "\
                "or reach out to a moderator."
                respond(client, interloc, response)
                return None
            
            # If sender of message is a moderator, administrator, or owner:
            if interloc["role"] <= 300:
                label:Label = labeling.message_match(message["content"])
                
                # If message contains assignment code, do daily tabulation
                if label is not None:
                    response = do_daily(messages, label, config["stream_specifier"])
                
                # Otherwise, do overall count tabulation
                else:
                    response = do_counts(messages)
            
            # If sender of message is a member, tabulate personal counts
            else:
                response = do_personal(messages, interloc)
            
            # Issue response    
            respond(client, interloc, response)
        
        # This shouldn't happen! It might if of the calls to the Zulip client 
        # returns something unexpected... 
        except KeyError as k:
            print(f"The key {k} raised a KeyError. This shouldn't happen..." )
        
        # Return
        finally:
            return None

handler_class = TallyBotHandler

def clear_pm_history(client: zulip.Client, interloc: dict) -> None:
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
            
def clear_stream_mentions(client : zulip.Client) -> None:
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

def respond(client: zulip.Client, interloc: dict, response: str) -> None:
    """
    Uses the given client to send the interlocutor a private message containing 
    the given response. 
    """
    request = {
        "type": "private",
        "to": [interloc["user_id"]],
        "content": response,
    }
    client.send_message(request)

def minimize(x: str) -> str:
    """
    Converts a string to lower case and removes all punctuation. 
    """
    punc_remover = str.maketrans("", "", string.punctuation)
    return x.lower().translate(punc_remover)
    
def get_config(config_file, message: dict) -> dict:
    """
    Extract configuration data from the message. If the message was a stream
    message, configuration data is extracting using the name of the stream. If
    message was a private message, the content of the message must contain a
    specifying information (short specifier or full stream name). If nothing
    matches, returns None. 
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
            if c["stream_specifier"] in message["content"]:
                return c
            elif minimize(c["stream_name"]) in message["content"]:
                return c
    
    # If no configuration data was matched          
    return None
    
def get_messages(client: zulip.Client, config: dict, labeling: LabelingScheme) -> list:
    """
    Returns a list of all messages by members whose topic has a match for the
    labeling scheme, ie, for which the topic_match() method of the given
    labeling scheme returns something other than None. 
    """
    # Get messages
    messages = []
        
    batch = []
    found_oldest = False
    while not found_oldest: 
        # Run request
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
                sender = client.get_user_by_id(m["sender_id"])["user"]
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
                        reactor = client.get_user_by_id(r["user"]["id"])["user"]
                        if reactor["role"] <= 300:
                            valid = False
                            break
                
                # Add message to output list
                messages.append({
                    "id" : m["id"], 
                    "sender_id" : sender["user_id"], 
                    "sender_name" : sender["full_name"],
                    "sender_email" : sender["delivery_email"],
                    "label" : label.label(),
                    "content" : m["content"],
                    "timestamp" : timestamp,
                    "on_time" : (timestamp <= label.deadline()),
                    "valid" : valid
                })
    
    return messages
    
def do_daily(messages: list, label: Label, stream_specifier: str) -> str:
    """
    Return list of all messages that had a matching label in their topic as
    a markdown-formatted bulleted list. 
    """
    # Header
    response = f"Reading questions for {stream_specifier} {label.label()} \n\n"
    # Data
    for m in messages:
        if m["label"] == label.label():
            response += f"* ({m['sender_name']}) {m['content']}\n"
    
    return response
    
def do_counts(messages: list) -> str:
    """
    Return list of total counts by user's email address in CSV format. 
    """
    # Header for CSV
    response = "email,count\n"
    # CSV data
    users = set([m["sender_email"] for m in messages])
    count = { u : 0 for u in users }
    for u in users:
        count[u] = len(set([m["label"] for m in messages \
            if m["sender_email"] == u and m["on_time"] and m["valid"]]))
        response += f"{u},{count[u]}\n"
        
    return response
    
def do_personal(messages : list, interloc : dict) -> str:
    """
    Return total number of on-time and valid messages for the interlocutor as a
    string. If there were late and/or invalid_emoji messages, these counts are
    returned as well. 
    """
    # Make a dictionary where keys are assignment labels, and values are 
    # dictionaries with two keys: "on_time" (true iff any of the messages
    # corresponding to that assignment was on time), and "valid" (true iff any 
    # of the messages corresponding to that assignment is valid)
    assignment = {}
    for m in messages:
        if m["sender_id"] == interloc["user_id"]:
            a = m["label"]
            if a not in assignment.keys():
                assignment[a] = { "on_time" : False, "valid" : False}
            assignment[a]["on_time"] = assignment[a]["on_time"] or m["on_time"]
            assignment[a]["valid"] = assignment[a]["valid"] or m["valid"]
    
    # Filter the dictionary into separate lists
    credit = [a for a, v in assignment.items() if v["on_time"] and v["valid"]]
    late = [a for a, v in assignment.items() if not v["on_time"]]
    invalid = [a for a, v in assignment.items() if v["on_time"] and not v["valid"]]
    
    # Formulate response
    response = f"On-time posts with valid reading questions: {len(credit)}"
    if len(credit) > 0:
        response += " (" + (", ".join(credit)) + ")"
    if len(late) > 0:
        response += f".\nLate posts: {len(late)}"
        response += " (" + (", ".join(late)) + ")"
    if len(invalid) > 0:
        response += f".\nOther posts: {len(invalid)}"
        response += " (" + (", ".join(invalid)) + ")"   
    response += "."
    
    return response

