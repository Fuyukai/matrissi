class Event(object):
    """
    Base class for a single event.
    """

    #: Marks this event as insignificant. An insignificant event will not be dispatched if there are
    #: already too many event handlers running, nor will it be dispatched over the global generic
    #: event dispatcher.
    #: Examples of insignificant events include all ephemeral events, such as typing and read
    #: indicators.
    insignificant: bool
