#!/usr/bin/python3
# SPDX-License-Identifier: GPL-3.0-only
#   Menu Editor & Launcher Recovery for Linux Mint Cinnamon
#   Copyright (C) 2012-2024 Sean Davis <sean@bluesabre.org>
#   Copyright (C) 2026 schnee-and-tetra <308144300+schnee-tetra@users.noreply.github.com>
import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, GObject, Gtk, Pango


class TextEntryButton(Gtk.Stack):
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

    def __init__(
        self, property_name, bold_font=False, required=False, placeholder_text=""
    ):
        super().__init__()
        self._property_name = property_name
        self._value = ""
        self._required = required
        self._placeholder_text = placeholder_text
        self._bold_font = bold_font

        self._button = Gtk.Button.new()
        self._button.connect("clicked", self._on_clicked)
        self._button.set_relief(Gtk.ReliefStyle.NONE)
        self._button.connect("focus-in-event", self._on_button_focus_in)
        self._button.connect("focus-out-event", self._on_button_focus_out)
        self.add(self._button)

        self._label = Gtk.Label.new("")
        self._label.set_xalign(0.0)
        self._label.set_ellipsize(Pango.EllipsizeMode.END)
        self._button.add(self._label)

        self._entry = Gtk.Entry.new()
        self._entry.set_placeholder_text(placeholder_text)
        self._entry.connect("key-press-event", self._on_entry_key_press)
        self._entry.connect("activate", self._on_entry_activate)
        self._entry.connect("changed", self._on_entry_changed)
        self._entry.connect("icon-press", self._on_entry_icon_press)
        self._entry.connect("focus-out-event", self._on_entry_focus_out)
        self.add(self._entry)

        self.set_homogeneous(True)

        self._on_entry_changed(self._entry)

    def set_value(self, value):
        if value is None:
            value = ""
        value = value.strip()
        self._value = value
        self._entry.set_text(value)
        attributes = Pango.AttrList.new()
        if len(value) > 0:
            self._label.set_text(value)
            attributes.insert(Pango.attr_style_new(Pango.Style.NORMAL))
            if self._bold_font:
                attributes.insert(Pango.attr_weight_new(Pango.Weight.BOLD))
                attributes.insert(Pango.attr_size_new(12000))
        else:
            self._label.set_text(self._placeholder_text)
            attributes.insert(Pango.attr_style_new(Pango.Style.ITALIC))
            attributes.insert(Pango.attr_weight_new(Pango.Weight.NORMAL))
        self._label.set_attributes(attributes)
        self.set_visible_child(self._button)
        self.emit("value-changed", self._property_name, self._value)

    def set_editable(self, editable):
        """Enable or disable edit mode for this field."""
        self._button.set_sensitive(editable)

    def get_value(self):
        """Return the current entry text."""
        return self._entry.get_text()

    def _on_button_focus_in(self, button, event):
        button.set_relief(Gtk.ReliefStyle.NORMAL)

    def _on_button_focus_out(self, button, event):
        button.set_relief(Gtk.ReliefStyle.NONE)

    def _on_clicked(self, button):
        self.set_visible_child(self._entry)
        self._entry.grab_focus()

    def commit(self):
        """Commit the current entry value if valid, otherwise cancel."""
        if self._entry.get_icon_name(Gtk.EntryIconPosition.SECONDARY) == "gtk-apply":
            self.set_value(self._entry.get_text().strip())
        else:
            self.cancel()

    def cancel(self):
        """Cancel editing and restore the previous value."""
        self.set_visible_child(self._button)
        self._entry.set_text(self._value)

    def _on_entry_key_press(self, entry, event):
        """Handle key press events in the entry."""
        keyval_name = Gdk.keyval_name(event.get_keyval()[1])
        if keyval_name is None:
            return
        if keyval_name.lower() == "escape":
            self.cancel()
            self._button.grab_focus()

    def _on_entry_activate(self, entry):
        """Handle entry activation (Enter key)."""
        if self._entry.get_icon_name(Gtk.EntryIconPosition.SECONDARY) == "gtk-apply":
            self.commit()
            self._button.grab_focus()
        else:
            self.cancel()

    def _on_entry_changed(self, entry):
        """Update secondary icon based on text validity."""
        text = entry.get_text().strip()
        if self._required and len(text) == 0:
            entry.set_icon_from_icon_name(Gtk.EntryIconPosition.SECONDARY, "gtk-cancel")
        else:
            entry.set_icon_from_icon_name(Gtk.EntryIconPosition.SECONDARY, "gtk-apply")

    def _on_entry_icon_press(self, entry, icon_pos, event):
        """Handle secondary icon press."""
        self._on_entry_activate(entry)

    def _on_entry_focus_out(self, entry, event):
        """Commit changes when losing focus."""
        self.commit()
        return False
