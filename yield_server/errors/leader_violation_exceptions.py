'''
This file contains the possible exceptions for leader violations.

These exceptions will be extended to provide a structured way to construct the violation messages.
'''

class BoundHotkeyDeregistrationException(Exception):
    '''
    This exception is raised when a hotkey is deregistered while it is bound to a leader.
    '''
    def __init__(self, hotkey: str, leader_id: int, timestamp: int, violation_message: str):
        self.hotkey = hotkey
        self.leader_id = leader_id
        self.timestamp = timestamp
        super().__init__(violation_message)

    @property
    def violation_message(self) -> str:
        return f"Hotkey {self.hotkey} deregistered while bound to Leader {self.leader_id} causing violation recorded at timestamp {self.timestamp}"

class InvalidStakeException(Exception):
    '''
    This exception is raised when a leader's stake is invalid.
    '''
    pass