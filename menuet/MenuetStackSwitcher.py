#!/usr/bin/python3
# SPDX-License-Identifier: GPL-3.0-only
#   Menu Editor & Launcher Recovery for Linux Mint Cinnamon
#   Copyright (C) 2012-2024 Sean Davis <sean@bluesabre.org>
#   Copyright (C) 2026 schnee-and-tetra <308144300+schnee-tetra@users.noreply.github.com>
from gi.repository import Gtk


class StackSwitcherBox(Gtk.Box):
    def __init__(self):
        Gtk.Box.__init__(self, orientation=Gtk.Orientation.VERTICAL, spacing=6)

        self._stack = Gtk.Stack()
        self._stack.set_transition_type(Gtk.StackTransitionType.NONE)
        self._stack.set_transition_duration(500)

        self._switcher = Gtk.StackSwitcher()
        self._switcher.set_stack(self._stack)
        self._switcher.set_property("valign", Gtk.Align.CENTER)
        self._switcher.set_property("halign", Gtk.Align.CENTER)

        self.pack_start(self._switcher, False, False, 0)
        self.pack_start(self._stack, True, True, 0)

    def get_stack(self):
        return self._stack

    def get_switcher(self):
        return self._switcher

    def add_child(self, child, name, title):
        self._stack.add_titled(child, name, title)
