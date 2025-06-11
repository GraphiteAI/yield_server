class InvalidSignature(Exception):
    '''
    Raised when a signature is invalid
    '''
    pass

class InvalidSS58Address(Exception):
    '''
    Raised when an SS58 address is invalid
    '''
    pass

class InvalidMessage(Exception):
    '''
    Raised when a message is invalid
    '''
    pass

class InvalidJWT(Exception):
    '''
    Raised when a JWT is invalid
    '''
    pass