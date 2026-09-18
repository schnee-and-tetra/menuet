#!/usr/bin/python3
# SPDX-License-Identifier: GPL-3.0-only
#   Menu Editor & Launcher Recovery for Linux Mint Cinnamon
#   Copyright (C) 2012-2024 Sean Davis <sean@bluesabre.org>
#   Copyright (C) 2026 schnee-and-tetra <308144300+schnee-tetra@users.noreply.github.com>
import gettext

_ = gettext.gettext

import gi

from .LabelWithHidingButton import LabelWithHidingButton

gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, GObject, Gtk, Pango


class FilenameLabel(LabelWithHidingButton):
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

    def __init__(self):
        super().__init__(
            label="", icon_name="edit-copy-symbolic", icon_size=Gtk.IconSize.BUTTON
        )
        self._value = None

        label = self.get_label()
        label.set_ellipsize(Pango.EllipsizeMode.MIDDLE)
        label.set_xalign(0.0)
        label.set_yalign(1.0)

        attributes = Pango.AttrList.new()
        attributes.insert(Pango.attr_style_new(Pango.Style.ITALIC))
        attributes.insert(Pango.attr_weight_new(Pango.Weight.NORMAL))
        label.set_attributes(attributes)

        button = self.get_button()
        button.set_tooltip_text(_("Copy"))
        button.connect("clicked", self._button_clicked_cb)

    def set_value(self, value):
        if value is None or value == "":
            value = None
            text = ""
        else:
            text = value
        self._label.set_text(text)
        self._label.set_tooltip_text(text)
        self._value = value
        self.emit("value-changed", "Filename", self._value)

    def get_value(self):
        return self._value

    def _button_clicked_cb(self, widget):
        if self._value is None:
            return
        clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        clipboard.set_text(self._value, -1)
