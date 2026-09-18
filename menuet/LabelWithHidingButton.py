#!/usr/bin/python3
# SPDX-License-Identifier: GPL-3.0-only
#   Menu Editor & Launcher Recovery for Linux Mint Cinnamon
#   Copyright (C) 2012-2024 Sean Davis <sean@bluesabre.org>
#   Copyright (C) 2026 schnee-and-tetra <308144300+schnee-tetra@users.noreply.github.com>
import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, Gtk


class LabelWithHidingButton(Gtk.EventBox):
    def __init__(self, label, icon_name, icon_size):
        super().__init__()

        box = Gtk.Box.new(orientation=Gtk.Orientation.HORIZONTAL, spacing=3)
        self.add(box)

        self._label = Gtk.Label.new(label)
        self._label.set_xalign(0.0)

        box.add(self._label)

        self._button = Gtk.Button.new_from_icon_name(icon_name, icon_size)
        self._button.set_name("hideybutton")
        self._button.set_opacity(0.0)

        context = self._button.get_style_context()
        context.add_class("flat")

        box.add(self._button)

        self.add_events(
            Gdk.EventMask.ENTER_NOTIFY_MASK | Gdk.EventMask.LEAVE_NOTIFY_MASK
        )

        self._label_entered = False
        self._button_entered = False
        self._button_focused = False

        self.connect("enter-notify-event", self._enter_notify_cb, self._button)
        self.connect("leave-notify-event", self._leave_notify_cb, self._button)

        self._button.connect(
            "enter-notify-event", self._button_enter_notify_cb, self._button
        )
        self._button.connect(
            "leave-notify-event", self._button_leave_notify_cb, self._button
        )

        self._button.connect("focus-in-event", self._button_focus_in_cb, self._button)
        self._button.connect("focus-out-event", self._button_focus_out_cb, self._button)

    def get_button(self):
        return self._button

    def get_label(self):
        return self._label

    def _toggle_button_visibility(self, button):
        if self._label_entered or self._button_entered or self._button_focused:
            button.set_opacity(1.0)
        else:
            button.set_opacity(0.0)

    def _enter_notify_cb(self, widget, event, button):
        self._label_entered = True
        self._toggle_button_visibility(button)

    def _leave_notify_cb(self, widget, event, button):
        self._label_entered = False
        self._toggle_button_visibility(button)

    def _button_enter_notify_cb(self, widget, event, button):
        self._button_entered = True
        self._toggle_button_visibility(button)

    def _button_leave_notify_cb(self, widget, event, button):
        self._button_entered = False
        self._toggle_button_visibility(button)

    def _button_focus_in_cb(self, widget, event, button):
        self._button_focused = True
        self._toggle_button_visibility(button)

    def _button_focus_out_cb(self, widget, event, button):
        self._button_focused = False
        self._toggle_button_visibility(button)
