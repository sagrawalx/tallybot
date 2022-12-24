
TallyBot is a Zulip bot that facilitates flipping classes by performing book-keeping for assignments that ask students to participate in an online discussion. 

# Background

[I](https://sagrawalx.github.io/) typically structure my classes so that students are asked to read some material and submit a Reading Question (RQ) about that material before we discuss it in class. An RQ need not strictly be a question: it can be any comment that shows sincere engagement with the content of the assigned reading, though questions are generally encouraged. I then use these RQs to help frame our in-class discussion of the material. Before writing this bot, I'd experimented with a few ways of soliciting these RQs: 

* I've had students submit RQs via a Google Form. This makes data tabulation easy, but students are unable to see and respond to each other's RQs. 
* I've had students post their RQ to Discord. This allows them to see each other's RQs, and one student's RQ can be a response to someone else's RQ. I tabulated the data manually, and it was fine because it was a very small class, but it would be impossible for a large class. 

As far as I can tell, Discord is set up in a way to make automated data tabulation essentially impossible without very sophisticated NLP. (Discord also lacks native TeX support, which is frustrating.) Zulip's "[topics](https://zulip.com/help/streams-and-topics)" open the door to automated tabulation. This simple Zulip bot implements this automated tabulation. 

# How It Works

## Overview

Roughly, each assignment that asks students to post to Zulip carries a label and a deadline. In my typical labeling scheme, labels are strings like `w3thu`, which indicates an assignment due on Thursday of the 3rd week of the term (at some designated time that can be specified in `config.yml`). The bot looks through Zulip messages in a given stream whose topic contains a match for a label. In other words, students must include this label if the topic of a message they'd like to be counted by the bot. 

## What the Bot Does

The bot reacts to private messages sent to it, and to stream messages in which it is tagged. If the message to the bot contains the word `clear`, it clears the sender's private message history with the bot. Otherwise, the bot will look through messages in a given stream. If the message it is reacting to is a stream message in which it was tagged, that will be the stream whose messages the bot looks through, and to clean up clutter, the bot will delete the stream message in which it was tagged. If a private message is sent to the bot, the message must contain either the full name of the stream or a short stream specifier (which can be specified in `config.yml`). 

For members (ie, students) in the Zulip organization, the bot will count the number of distinct assignment labels that appear among that member's messages. Messages that were posted after the deadline, and messages that were marked as irrelevant, are not counted. Here, "marked as irrelevant" means that a moderator reacts to the message with a designated emoji, which can be specified in `config.yml`). That total count is returned to the user as a response. 

For moderators and admins (ie, instructional staff), the bot will do one of two things: 

* If the message contains an assignment label, the bot will return all messages that match that label. 

* Otherwise, the bot will return total counts for all members (ie, students). Members are specified by their email address. It will be a private message in CSV format with header `email,count`.

## Labeling Schemes

A `Label` is an object which remembers both a string and a deadline, and a `LabelingScheme` allows us to find a `Label` inside a string (either the topic or the content of a Zulip message). The labeling scheme that I like using is implemented as `StandardLabelingScheme` in `labelingscheme.py`. Readers are invited to read the documentation for that class for details about how this works. 

Users familiar with Python can implement an alternative `LabelingScheme` if they don't like mine. It must be a subclass of `LabelingScheme`, and the subclass name can be specified using the `labeling_scheme` key in `config.yml`. Furthermore, `labeler_config` in `config.yml` is a dictionary that is passed to the constructor for the `LabelingScheme`. 

# Setup

At some point I will make this easier to set up. For now, here are the instructions: 

## Install `python-zulip-api`

`cd` into a directory inside which you would like the `python-zulip-api` package to live; for the purposes of these instructions, I will label this directory "`/path/to/`." Then [install](https://zulip.com/api/writing-bots) as follows:

```
git clone https://github.com/zulip/python-zulip-api.git
cd python-zulip-api
python3 ./tools/provision
```

The output should end with a `source` command like the following. **You don't need to run this right now**, but it's probably good to make a note of it: 

```
source /path/to/python-zulip-api/zulip-api-py3-venv/bin/activate
```

## Download and Configure Bot

The following will clone this repository into the correct directory. 

```
cd /path/to/python-zulip-api/zulip_bots/zulip_bots/bots/
git clone https://github.com/sagrawalx/tallybot
```

You'll then want to edit `config.yml` to your liking. 

## Add Bot

[Add a generic bot](https://zulip.com/help/add-a-bot-or-integration) to your Zulip organization. 

* The bot needs to be an administrator. 
* The name you choose here will be used only to invoke the bot. I named it `TallyBot` for consistency, but you can name it whatever you like. 
* The email address can also be set to whatever you like. I used `tally-bot@...`. 

Download it's `zuliprc` file. The file can live anywhere you like; for the purposes of these instructions, I will assume that it lives in `~/downloads/`. 

## Start Bot

Run the following, changing `/path/to/python-zulip-api/zulip-api-py3-venv/bin/activate` and `~/downloads/zuliprc` as needed (see above). Note that, even if you put the `zuliprc` file in the same directory as the bot, you'll have to specify the full path to the file. 

```
source /path/to/python-zulip-api/zulip-api-py3-venv/bin/activate
zulip-run-bot tallybot --config-file ~/downloads/zuliprc
```

This should start up the bot, and the bot can be used while this script continues to run!

# Todo

There's all kinds of things that can be done with this bot. Here are somethings that are on my radar: 

* The bot should have more graceful error handling. 
* The bot should have better help messages. 
* It would be nice if the bot were easier to set up. 

