__version__ = "0.0.0"

version_split = __version__.split(".")
__spec_version__ = (
    (1000 * int(version_split[0]))
    + (10 * int(version_split[1]))
    + (1 * int(version_split[2]))
)

# Import all submodules.
from . import backend
from . import endpoints
from . import utils
from . import middleware
from . import core
from . import errors
from . import config
from . import utils