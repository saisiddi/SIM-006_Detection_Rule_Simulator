"""Package entry point for ``python -m sim_006``.

Delegates to the CLI implemented in :mod:`sim_006.cli`.
"""

import sys

from sim_006.cli import main

if __name__ == "__main__":
    sys.exit(main())
