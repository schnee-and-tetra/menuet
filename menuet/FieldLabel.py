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
from gi.repository import GObject, Gtk, Pango


class FieldLabel(LabelWithHidingButton):
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

    def __init__(self, label, key_name, description, help_text=None, help_url=None):
        super().__init__(
            label=label,
            icon_name="dialog-question-symbolic",
            icon_size=Gtk.IconSize.BUTTON,
        )
        self._value = None

        label = self.get_label()
        label.set_ellipsize(Pango.EllipsizeMode.NONE)

        button = self.get_button()
        button.set_tooltip_markup(_("More information about <i>%s</i>") % key_name)
        button.connect(
            "clicked",
            self._button_clicked_cb,
            key_name,
            description,
        )

    def _button_clicked_cb(self, widget, key_name, description):
        dlg = FieldInfo(
            self.get_toplevel(),
            key_name=key_name,
            description=description,
        )
        dlg.show()


class FieldInfo(Gtk.MessageDialog):
    def __init__(self, parent, key_name, description):
        primary = key_name
        secondary = description

        Gtk.MessageDialog.__init__(
            self,
            transient_for=parent,
            modal=True,
            message_type=Gtk.MessageType.ERROR,
            buttons=Gtk.ButtonsType.CLOSE,
            text=primary,
            use_header_bar=False,
        )
        self.format_secondary_markup(secondary)

        message_area = self.get_content_area().get_children()[0]
        if isinstance(message_area.get_children()[0], Gtk.Image):
            message_area.get_children()[0].destroy()

        self.connect("response", self.response_cb)

    def response_cb(self, widget, response):
        widget.destroy()
