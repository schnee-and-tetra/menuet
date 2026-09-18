#!/usr/bin/python3
# SPDX-License-Identifier: GPL-3.0-only
#   Menu Editor & Launcher Recovery for Linux Mint Cinnamon
#   Copyright (C) 2012-2024 Sean Davis <sean@bluesabre.org>
#   Copyright (C) 2026 schnee-and-tetra <308144300+schnee-tetra@users.noreply.github.com>
import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GObject, Gtk


class TextEntry(Gtk.Entry):
    __gsignals__ = {
        "value-changed": (
            GObject.SignalFlags.RUN_FIRST,
            None,
            (
                str,
                str,
            ),
        ),
    }

    def __init__(self, property_name):
        super().__init__()
        self._property_name = property_name

        self.set_hexpand(True)

        self.connect("changed", self._on_changed)

    def set_value(self, value):
        if value is None:
            value = ""
        self.set_text(value)

    def get_value(self):
        return self.get_text()

    def _on_changed(self, widget):
        self.emit("value-changed", self._property_name, self.get_value())
