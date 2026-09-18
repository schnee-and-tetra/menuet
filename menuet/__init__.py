#!/usr/bin/python3
# SPDX-License-Identifier: GPL-3.0-only
#   Menu Editor & Launcher Recovery for Linux Mint Cinnamon
#   Copyright (C) 2012-2024 Sean Davis <sean@bluesabre.org>
#   Copyright (C) 2026 schnee-and-tetra <308144300+schnee-tetra@users.noreply.github.com>
import gettext
import logging
import optparse
import os
import sys

_ = gettext.gettext

from menuet import MenuetApplication

__version__ = "1.0.0"


# lint:disable
class NullHandler(logging.Handler):
    def emit(self, record):
        pass


def set_up_logging(opts):
    """Set up logging for menuet"""
    # add a handler to prevent basicConfig
    root = logging.getLogger()
    null_handler = NullHandler()
    root.addHandler(null_handler)

    formatter = logging.Formatter(
        "%(asctime)s.%(msecs)03d %(levelname)s:%(name)s: %(funcName)s() '%(message)s'",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    logger = logging.getLogger("menuet")
    logger_sh = logging.StreamHandler()
    logger_sh.setFormatter(formatter)
    logger.addHandler(logger_sh)

    # Set the logging level to show debug messages.
    try:
        if opts.verbose:
            logger.setLevel(logging.DEBUG)
            project_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            log_file_path = os.path.join(project_dir, "menuet.log")
            handler = logging.FileHandler(log_file_path, encoding="utf-8")
            handler.setFormatter(formatter)
            logger.addHandler(handler)
            logger.debug("logging enabled")
    except TypeError:
        pass


def parse_options():
    """Support for command line options"""
    parser = optparse.OptionParser(version=f"%prog {__version__}")
    parser.add_option(
        "-v",
        "--verbose",
        action="count",
        dest="verbose",
        # Translators: Command line option to display debug messages on stdout
        help=_("Show debug messages"),
    )
    parser.add_option(
        "-b",
        "--headerbar",
        action="count",
        dest="headerbar",
        # Translators: Command line option to switch layout
        help=_("Use headerbar layout (client side decorations)"),
    )
    parser.add_option(
        "-t",
        "--toolbar",
        action="count",
        dest="toolbar",
        # Translators: Command line option to switch layout
        help=_("Use toolbar layout (server side decorations)"),
    )
    (options, args) = parser.parse_args()

    set_up_logging(options)

    return options


def main():
    """Main application for Menuet"""
    opts = parse_options()

    # Run the application.
    app = MenuetApplication.Application()
    if opts.headerbar is not None:
        app.use_headerbar = True
    elif opts.toolbar is not None:
        app.use_toolbar = True

    exit_status = app.run(None)
    sys.exit(exit_status)
