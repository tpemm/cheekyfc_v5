"""Project configuration bootstrap."""

# Every Fantrax CLI imports project configuration. Initializing the console
# here gives both legacy and current entry points one shared Unicode safeguard.
from fantrax.utils.cli import configure_unicode_console

configure_unicode_console()
