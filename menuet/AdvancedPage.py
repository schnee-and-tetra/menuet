#!/usr/bin/python3
# SPDX-License-Identifier: GPL-3.0-only
#   Menu Editor & Launcher Recovery for Linux Mint Cinnamon
#   Copyright (C) 2012-2024 Sean Davis <sean@bluesabre.org>
#   Copyright (C) 2026 schnee-and-tetra <308144300+schnee-tetra@users.noreply.github.com>
import gettext

_ = gettext.gettext

import gi

from .FieldLabel import FieldLabel
from .StartupWmClassEntry import StartupWmClassEntry
from .SwitchEntry import SwitchEntry
from .TextEntry import TextEntry

gi.require_version("Gtk", "3.0")
from gi.repository import GObject, Gtk


class AdvancedPage(Gtk.ScrolledWindow):
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
        super().__init__(hadjustment=None, vadjustment=None)

        self._row_index = 0
        self._widgets = {}

        self.set_shadow_type(Gtk.ShadowType.IN)
        self.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)

        self._grid = Gtk.Grid()
        self._grid.set_border_width(12)
        self._grid.set_row_spacing(3)
        self._grid.set_row_homogeneous(True)
        self._grid.set_column_spacing(6)
        self._grid.set_valign(Gtk.Align.START)
        self.add(self._grid)

        self._add_row(
            "GenericName",
            _("Generic Name"),
            _('Generic name of the application, for example "Web Browser".'),
            TextEntry("GenericName"),
        )

        self._add_row(
            "TryExec",
            _("Try Exec"),
            _(
                "Path to an executable file to determine if the program is installed. If the file is not present or is not executable, this entry may not be shown in a menu."
            ),
            TextEntry("TryExec"),
        )

        self._add_row(
            "OnlyShowIn",
            _("Only Show In"),
            _(
                'A list of environments that should display this entry. Other environments will not display this entry. You can only use this key if "NotShowIn" is not set.\n'
                "Possible values include: Budgie, Cinnamon, EDE, GNOME, KDE, LXDE, LXQt, MATE, Pantheon, Razor, ROX, TDE, Unity, XFCE, Old"
            ),
            TextEntry("OnlyShowIn"),
        )

        self._add_row(
            "NotShowIn",
            _("Not Shown In"),
            _(
                'A list of environments that should not display this entry. You can only use this key if "OnlyShowIn" is not set.\n'
                "Possible values include: Budgie, Cinnamon, EDE, GNOME, KDE, LXDE, LXQt, MATE, Pantheon, Razor, ROX, TDE, Unity, XFCE, Old"
            ),
            TextEntry("NotShowIn"),
        )

        self._add_row(
            "MimeType",
            _("Mimetypes"),
            _("The MIME type(s) supported by this application."),
            TextEntry("MimeType"),
        )

        self._add_row(
            "Keywords",
            _("Keywords"),
            _(
                "A list of keywords to describe this entry. You can use these to help searching entries. These are not meant for display, and should not be redundant with the values of Name or GenericName."
            ),
            TextEntry("Keywords"),
        )

        self._add_row(
            "StartupWMClass",
            _("Startup WM Class"),
            _(
                "If specified, the application will be requested to use the string as a WM class or a WM name hint at least in one window."
            ),
            StartupWmClassEntry("StartupWMClass", use_headerbar=use_headerbar),
        )

        self._add_row(
            "Implements",
            _("Implements"),
            _("A list of interfaces that this application implements."),
            TextEntry("Implements"),
        )

        self._add_row(
            "Hidden",
            _("Hidden"),
            _(
                'If set to "True", the result for the user is equivalent to the .desktop file not existing at all.'
            ),
            SwitchEntry("Hidden"),
        )

        self._add_row(
            "DBusActivatable",
            _("DBUS Activatable"),
            _(
                'Set this key to "True" if D-Bus activation is supported for this application and you want to use it.'
            ),
            SwitchEntry("DBusActivatable"),
        )

        self._add_row(
            "PrefersNonDefaultGPU",
            _("Prefers Non-Default GPU"),
            _(
                'Set this key to "True" if this application prefers to be run on a more powerful GPU if available.'
            ),
            SwitchEntry("PrefersNonDefaultGPU"),
        )

        self.show_all()

    def _add_row(self, id, text, tooltip, widget):
        label = FieldLabel(
            label=text,
            key_name=id,
            description=tooltip,
        )
        self._grid.attach(label, 0, self._row_index, 1, 1)

        widget.connect("value-changed", self._on_widget_value_changed)
        self._grid.attach(widget, 1, self._row_index, 1, 1)
        self._widgets[id] = widget

        self._row_index += 1

    def _on_widget_value_changed(self, widget, property_name, value):
        self.emit("value-changed", property_name, value)

    def has_value(self, property_name):
        return property_name in list(self._widgets.keys())

    def set_value(self, property_name, value):
        if self.has_value(property_name):
            self._widgets[property_name].set_value(value)
            return True
        return False

    def get_value(self, property_name):
        if self.has_value(property_name):
            return self._widgets[property_name].get_value()
        return None
