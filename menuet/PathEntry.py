#!/usr/bin/python3
# SPDX-License-Identifier: GPL-3.0-only
#   Menu Editor & Launcher Recovery for Linux Mint Cinnamon
#   Copyright (C) 2012-2024 Sean Davis <sean@bluesabre.org>
#   Copyright (C) 2026 schnee-and-tetra <308144300+schnee-tetra@users.noreply.github.com>
import gettext

_ = gettext.gettext

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GObject, Gtk


class PathEntry(Gtk.Entry):
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

    def __init__(self, use_headerbar):
        super().__init__()

        self._value = ""

        self.set_icon_from_icon_name(
            Gtk.EntryIconPosition.SECONDARY, "folder-open-symbolic"
        )

        self.connect("changed", self._on_entry_changed)
        self.connect("icon-release", self._on_icon_clicked, use_headerbar)

    def set_value(self, value):
        if value is None:
            value = ""
        self.set_text(value)

    def get_value(self):
        return self.get_text()

    def _on_entry_changed(self, widget):
        self.emit("value-changed", "Path", self.get_value())

    def _on_icon_clicked(self, entry, icon_pos, event, use_headerbar):
        """Show the file selection dialog when Path Browse is clicked."""
        # Translators: File Chooser Dialog, window title.
        title = _("Select a working directory")
        action = Gtk.FileChooserAction.SELECT_FOLDER

        dialog = FileChooserDialog(self.get_toplevel(), title, action, use_headerbar)
        dialog.set_filename(self.get_value())
        result = dialog.run()
        if result == Gtk.ResponseType.OK:
            filename = dialog.get_filename()
            self.set_value(filename)
        dialog.destroy()
        entry.grab_focus()


class FileChooserDialog(Gtk.FileChooserDialog):
    def __init__(self, parent, title, action, use_headerbar):
        Gtk.FileChooserDialog.__init__(
            self,
            title=title,
            transient_for=parent,
            action=action,
            use_header_bar=use_headerbar,
        )
        # Translators: File Chooser Dialog, cancel button.
        self.add_button(_("Cancel"), Gtk.ResponseType.CANCEL)
        # Translators: File Chooser Dialog, confirmation button.
        self.add_button(_("OK"), Gtk.ResponseType.OK)
