# This file is part of TallyBot (https://github.com/sagrawalx/tallybot)

import string
from re import search
from datetime import datetime, timedelta

class Label:
    """
    An abstract class to represent a label. 
    
    Any subclass should implement two methods: 
    
    * label(), which returns the label as a string.  
    * get_deadline(), which returns the deadline as a datetime object. 
    """
    def label(self) -> str:
        pass
    
    def deadline(self) -> datetime:
        pass
        
class LabelingScheme:
    """
    An abstract class to represent a labeling scheme. 
    
    Any subclass should implement two methods: 
    
    * topic_match(), which takes as input a topic string and returns a matching
      label as a Label object, if a match exists (else None). 
    * message_match(), which takes as input a message string and returns a
      matching label as a Label object, if a match exists (else None). 
    """
    def topic_match(self, topic: str) -> Label: 
        pass
    
    def message_match(self, message: str) -> Label:
        pass

class StandardLabel(Label):
    """
    A standard label. See the documentation for StandardLabelingScheme below 
    for further information about what this means. The __init__ method is
    for internal use only. Instances of this class should be created only using
    the topic_match() and message_match() methods of StandardLabelingScheme. 
    """
    def __init__(self, labeling : LabelingScheme, label : str, week : int, day : int):
        self._label = label
        self._week = week
        self._day = day
        self._labeling = labeling
    
    def label(self) -> str:
        return self._label
    
    def deadline(self) -> datetime:
        return self._labeling._deadline(self)

class StandardLabelingScheme(LabelingScheme):
    """
    A standard labeling scheme. Labels in this scheme are of the following form
     
    w(\d+)(mon|tue|wed|thu|fri)
    
    In other words, w followed by a number followed by a three-letter weekday
    name. The number represents the week number. The week number and weekday
    together specify a day in the term (on which an assignment is due). 
    
    To instantiate a standard labeling scheme, several parameters need to be
    specified (all together as a dictionary): 
    
    * config["start_date"] -- A date representing the first day of the term,
      ie, to the day specified by w1mon.  
    * config["due_time"] -- A number representing the numbers after midnight
      on which the assignments are due. 
    * config["max_weeks"] -- An integer representing the last week of the term. 
    * config["due_days"] -- The days of the week when assignments are actually
      due. 
    * config["exceptions"] -- Any labels that identify days when no assignments
      are actually due. If this parameter is missing, it defaults to empty. 
    * config["gaps"] -- A list of numbers identifying full-week gaps in the 
      term. For example, if this is [2, 4], it means that calendar weeks 2 and
      4 are skipped over in the week numbering scheme, so that w2mon refers 
      to the third calendar week after start_date, and w3mon to the fifth
      calendar week after start_date. If this parameter is missing, it defaults
      to empty. 
      
    The max_weeks, due_days, and exceptions parameters are used to determine
    well-formedness of labels (they rule out some strings that match the regex
    given above). The start_date, due_time, and gaps parameters help us figure 
    out how to convert between labels and deadlines. 
    
    The regex as given above is used to pattern match in messages (ie, for
    the method message_match). For topics (ie, for the method topic_match()), 
    the same pattern must be contained inside square brackets. 
    
    This class contains the regex given above as a class variable called regex. 
    """
    regex = r"w(\d+)(mon|tue|wed|thu|fri)"

    def __init__(self, config: dict):
        """
        Instantiate a StandardLabelingScheme. See class documentation for
        details. 
        """
        self._start = datetime.combine(config["start_date"], datetime.min.time())
        self._start += timedelta(hours = config["due_time"])
        
        self._max_week = config["max_week"]
        self._due_days = config["due_days"]
        
        self._exceptions = config["exceptions"] \
            if "exceptions" in config.keys() else []
        self._gaps = config["gaps"] \
            if "gaps" in config.keys() else []
        
    def topic_match(self, topic: str) -> StandardLabel: 
        """
        Find a standard label inside a topic and return the label if there
        is a match, else return None. See class documentation for details. 
        """
        match = search(r"\[(" + StandardLabelingScheme.regex + r")\]", topic)
        if match is None:
            return None
        a, b, c = match.group(1), match.group(2), match.group(3)
        return self._create_label(a, b, c)
    
    def message_match(self, message: str) -> StandardLabel:
        """
        Find a standard label inside a topic and return the label if there
        is a match, else return None. See class documentation for details. 
        """
        match = search(StandardLabelingScheme.regex, message)
        if match is None:
            return None
        a, b, c = match.group(0), match.group(1), match.group(2)
        return self._create_label(a, b, c)
                
    def _create_label(self, a: str, b: str, c: str) -> StandardLabel:
        """
        For internal use only. Creates a StandardLabel object from:
        
        * a -- the full label string. 
        * b -- the substring representing the week number. 
        * c -- the substring representing the day of week.
        
        Returns None if the label would be excluded by the max_week, due_days,
        or exceptions parameters, as specified in the class documentation. 
        """
        if a in self._exceptions:
            return None
        b = int(b)
        if b > self._max_week:
            return None
        if c not in self._due_days:
            return None
        
        days_of_week = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4}
        c = days_of_week[c]
        return StandardLabel(self, a, b, c)
            
    def _deadline(self, label: StandardLabel) -> datetime:
        """
        For internal use only. Returns the deadline of the given standard 
        label, using the week number, day, and gaps, as specified in the class
        documentaiton. 
        """
        week = label._week
        day = label._day
        for g in self._gaps:
            if week >= g:
                week += 1
        return self._start + timedelta(days = 7*(week-1) + day)
        
