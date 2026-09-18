#!/usr/bin/python3
# SPDX-License-Identifier: GPL-3.0-only
#   Menu Editor & Launcher Recovery for Linux Mint Cinnamon
#   Copyright (C) 2012-2024 Sean Davis <sean@bluesabre.org>
#   Copyright (C) 2026 schnee-and-tetra <308144300+schnee-tetra@users.noreply.github.com>
import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Pango


class Section(Gtk.Frame):
    def __init__(self, label):
        super().__init__(label=label)

        label = self.get_label_widget()

        if label is not None:
            attributes = Pango.AttrList.new()
            attributes.insert(Pango.attr_weight_new(Pango.Weight.BOLD))
            label.set_attributes(attributes)

        self.set_shadow_type(Gtk.ShadowType.NONE)
