#!/usr/bin/python3
# SPDX-License-Identifier: GPL-3.0-only
#   Menu Editor & Launcher Recovery for Linux Mint Cinnamon
#   Copyright (C) 2012-2024 Sean Davis <sean@bluesabre.org>
#   Copyright (C) 2026 schnee-and-tetra <308144300+schnee-tetra@users.noreply.github.com>
import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GObject, Gtk


class SwitchEntry(Gtk.Switch):
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

        self.set_halign(Gtk.Align.END)
        self.set_valign(Gtk.Align.CENTER)
        self.set_margin_end(1)

        self.connect("notify::active", self._on_changed)

    def set_value(self, value):
        self.set_active(value)

    def get_value(self):
        return self.get_active()

    def _on_changed(self, status, widget):
        self.emit("value-changed", self._property_name, self.get_value())
