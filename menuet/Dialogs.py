#!/usr/bin/python3
# SPDX-License-Identifier: GPL-3.0-only
#   Menu Editor & Launcher Recovery for Linux Mint Cinnamon
#   Copyright (C) 2012-2024 Sean Davis <sean@bluesabre.org>
#   Copyright (C) 2026 schnee-and-tetra <308144300+schnee-tetra@users.noreply.github.com>
import gettext
import logging
import os

_ = gettext.gettext

from gi.repository import GdkPixbuf, Gtk

import menuet

from . import (
    util,
)

logger = logging.getLogger("menuet")


class AboutDialog(Gtk.AboutDialog):
    def __init__(self, parent, use_headerbar):
        Gtk.AboutDialog.__init__(self, use_header_bar=use_headerbar)

        # Translators: About Dialog, window title.
        icon_path = util.find_icon_path()
        self.set_title(_("About Menuet"))
        self.set_program_name("Menuet")
        if icon_path and os.path.exists(icon_path):
            pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(icon_path, 64, 64, True)
            self.set_logo(pixbuf)
        else:
            self.set_logo_icon_name("menuet")
        self.set_copyright(
            "Copyright © 2012-2024 Sean Davis\nCopyright © 2026 schnee-and-tetra"
        )
        self.set_website("https://github.com/schnee-and-tetra/menuet")
        self.set_version(menuet.__version__)

        # Connect the signal to destroy the AboutDialog when Close is clicked.
        self.connect("response", self.about_close_cb)
        self.set_transient_for(parent)

        # Fix weird bug with duplicate buttons
        if use_headerbar:
            headerbar = self.get_header_bar()
            for child in headerbar.get_children():
                if isinstance(child, Gtk.Button):
                    child.destroy()

    def about_close_cb(self, widget, response):
        """Destroy the AboutDialog when it is closed."""
        widget.destroy()


class SaveOnCloseDialog(Gtk.MessageDialog):
    def __init__(self, parent, use_headerbar):
        # Translators: Save On Close Dialog, window title.
        title = _("Save Changes")
        # Translators: Save On Close Dialog, primary text.
        primary = _("Do you want to save the changes before closing?")
        # Translators: Save On Close Dialog, secondary text.
        secondary = _("If you don't save the launcher, all the changes will be lost.")
        buttons = [
            # Translators: Save On Close Dialog, don't save, then close.
            (_("Don't Save"), Gtk.ResponseType.NO),
            # Translators: Save On Close Dialog, don't save, cancel close.
            (_("Cancel"), Gtk.ResponseType.CANCEL),
            # Translators: Save On Close Dialog, do save, then close.
            (_("Save"), Gtk.ResponseType.YES),
        ]

        Gtk.MessageDialog.__init__(
            self,
            transient_for=parent,
            modal=True,
            message_type=Gtk.MessageType.QUESTION,
            buttons=Gtk.ButtonsType.NONE,
            text=primary,
            use_header_bar=False,
        )
        self.set_title(title)
        self.format_secondary_markup(secondary)
        for button in buttons:
            self.add_button(button[0], button[1])


class SaveOnLeaveDialog(Gtk.MessageDialog):
    def __init__(self, parent, use_headerbar):
        # Translators: Save On Leave Dialog, window title.
        title = _("Save Changes")
        # Translators: Save On Leave Dialog, primary text.
        primary = _("Do you want to save the changes before leaving this launcher?")
        # Translators: Save On Leave Dialog, primary text.
        secondary = _("If you don't save the launcher, all the changes will be lost.")
        buttons = [
            # Translators: Save On Leave Dialog, don't save, then leave.
            (_("Don't Save"), Gtk.ResponseType.NO),
            # Translators: Save On Leave Dialog, don't save, cancel leave.
            (_("Cancel"), Gtk.ResponseType.CANCEL),
            # Translators: Save On Leave Dialog, do save, then leave.
            (_("Save"), Gtk.ResponseType.YES),
        ]

        Gtk.MessageDialog.__init__(
            self,
            transient_for=parent,
            modal=True,
            message_type=Gtk.MessageType.QUESTION,
            buttons=Gtk.ButtonsType.NONE,
            text=primary,
            use_header_bar=False,
        )
        self.set_title(title)
        self.format_secondary_markup(secondary)
        for button in buttons:
            self.add_button(button[0], button[1])


class DeleteDialog(Gtk.MessageDialog):
    def __init__(self, parent, primary, use_headerbar):
        # Translations: Delete Dialog, secondary text. Notifies user that
        # the file cannot be restored once deleted.
        secondary = _("This cannot be undone.")
        Gtk.MessageDialog.__init__(
            self,
            transient_for=parent,
            modal=True,
            message_type=Gtk.MessageType.QUESTION,
            buttons=Gtk.ButtonsType.OK_CANCEL,
            text=primary,
            use_header_bar=False,
        )
        self.format_secondary_markup(secondary)


class RevertDialog(Gtk.MessageDialog):
    def __init__(self, parent, use_headerbar):
        # Translators: Revert Dialog, window title.
        title = _("Restore Launcher")
        # Translators: Revert Dialog, primary text. Confirmation to revert
        # all changes since the last file save.
        primary = _("Are you sure you want to restore this launcher?")
        # Translators: Revert Dialog, secondary text.
        secondary = _(
            "All changes since the last saved state will be lost "
            "and cannot be restored automatically."
        )
        buttons = [
            # Translators: Revert Dialog, cancel button.
            (_("Cancel"), Gtk.ResponseType.CANCEL),
            # Translators: Revert Dialog, confirmation button.
            (_("Restore Launcher"), Gtk.ResponseType.OK),
        ]

        Gtk.MessageDialog.__init__(
            self,
            transient_for=parent,
            modal=True,
            message_type=Gtk.MessageType.QUESTION,
            buttons=Gtk.ButtonsType.NONE,
            text=primary,
            use_header_bar=False,
        )
        self.set_title(title)
        self.format_secondary_markup(secondary)
        for button in buttons:
            self.add_button(button[0], button[1])


class LauncherRemovedDialog(Gtk.MessageDialog):
    def __init__(self, parent, use_headerbar):
        # Translators: Launcher Removed Dialog, primary text. Indicates that
        # the selected application is no longer installed.
        primary = _("No Longer Installed")
        # Translators: Launcher Removed Dialog, secondary text.
        secondary = _(
            "This launcher has been removed from the "
            "system.\nSelecting the next available item."
        )

        Gtk.MessageDialog.__init__(
            self,
            transient_for=parent,
            modal=True,
            message_type=Gtk.MessageType.INFO,
            buttons=Gtk.ButtonsType.OK,
            text=primary,
            use_header_bar=False,
        )
        self.format_secondary_markup(secondary)


class NotFoundInPathDialog(Gtk.MessageDialog):
    def __init__(self, parent, command, use_headerbar):
        # Translators: Not Found In PATH Dialog, primary text. Indicates
        # that the provided script was not found in any PATH directory.
        primary = _('Could not find "%s" in your PATH.') % command

        path = os.getenv("PATH", "").split(":")
        secondary = "<b>PATH:</b>\n{}".format("\n".join(path))
        Gtk.MessageDialog.__init__(
            self,
            transient_for=parent,
            modal=True,
            message_type=Gtk.MessageType.ERROR,
            buttons=Gtk.ButtonsType.OK,
            text=primary,
            use_header_bar=False,
        )
        self.format_secondary_markup(secondary)
        self.connect("response", self.response_cb)

    def response_cb(self, widget, user_data):
        widget.destroy()


class SaveErrorDialog(Gtk.MessageDialog):
    def __init__(self, parent, filename, use_headerbar):
        # Translators: Save Error Dialog, primary text.
        primary = _('Failed to save "%s".') % filename
        # Translators: Save Error Dialog, secondary text.
        secondary = _("Do you have write permission to the file and directory?")

        Gtk.MessageDialog.__init__(
            self,
            transient_for=parent,
            modal=True,
            message_type=Gtk.MessageType.ERROR,
            buttons=Gtk.ButtonsType.OK,
            text=primary,
            use_header_bar=False,
        )
        self.format_secondary_markup(secondary)
        self.connect("response", self.response_cb)

    def response_cb(self, widget, user_data):
        widget.destroy()


class ConfirmPromotionDialog(Gtk.MessageDialog):
    def __init__(self, parent, use_headerbar):
        # Translators: GMenu Registry Confirmation Dialog, window title.
        title = _("Confirm Registration")
        # Translators: GMenu Registry Confirmation Dialog, primary text.
        primary = _(
            "This launcher matches XDG specifications. Do you want to register it into the main menu?"
        )

        Gtk.MessageDialog.__init__(
            self,
            transient_for=parent,
            modal=True,
            message_type=Gtk.MessageType.QUESTION,
            buttons=Gtk.ButtonsType.YES_NO,
            text=primary,
            use_header_bar=False,
        )
        self.set_title(title)


class DuplicateLauncherDialog(Gtk.MessageDialog):
    def __init__(self, parent, item_type, use_headerbar):
        # Translators: Duplicate Launcher Dialog, window title.
        title = _("Duplicate Found")

        # Determine the item label dynamically for clear messaging.
        item_label = _("category") if item_type == "Directory" else _("launcher")

        # Translators: Duplicate Launcher Dialog, primary text.
        primary = (
            _("A %s with the same name already exists. Do you want to save it anyway?")
            % item_label
        )

        # Translators: Duplicate Launcher Dialog, secondary text.
        secondary = _(
            "If you proceed, a unique ID will be appended to the filename to avoid overwriting."
        )

        buttons = [
            # Translators: Duplicate Launcher Dialog, cancel button.
            (_("Cancel"), Gtk.ResponseType.NO),
            # Translators: Duplicate Launcher Dialog, save button.
            (_("Save"), Gtk.ResponseType.YES),
        ]

        Gtk.MessageDialog.__init__(
            self,
            transient_for=parent,
            modal=True,
            message_type=Gtk.MessageType.QUESTION,
            buttons=Gtk.ButtonsType.NONE,
            text=primary,
            use_header_bar=False,
        )
        self.set_title(title)
        self.format_secondary_markup(secondary)
        for button in buttons:
            self.add_button(button[0], button[1])


class ValidationErrorDialog(Gtk.MessageDialog):
    def __init__(self, parent, use_headerbar):
        # Translators: Validation Failure Dialog, window title.
        title = _("Validation Failed")
        # Translators: Validation Failure Dialog, primary text.
        primary = _(
            "Required entry fields are missing or do not match XDG specifications."
        )
        # Translators: Validation Failure Dialog, secondary text.
        secondary = _(
            "This item has been isolated and placed back into the Menuet temporary area."
        )

        Gtk.MessageDialog.__init__(
            self,
            transient_for=parent,
            modal=True,
            message_type=Gtk.MessageType.WARNING,
            buttons=Gtk.ButtonsType.CLOSE,
            text=primary,
            use_header_bar=False,
        )
        self.set_title(title)
        self.format_secondary_markup(secondary)


class UnsupportedDesktopDialog(Gtk.MessageDialog):
    def __init__(self, parent, use_headerbar):
        # Translators: Unsupported Desktop Dialog, window title.
        title = _("Unsupported Desktop Environment")
        # Translators: Unsupported Desktop Dialog, primary text. Shown when
        # Menuet is launched outside the Cinnamon desktop environment.
        primary = _("Menuet only supports Linux Mint's Cinnamon desktop.")
        # Translators: Unsupported Desktop Dialog, secondary text. The
        # application closes once this dialog is dismissed.
        secondary = _(
            "This build of Menuet requires the Cinnamon desktop environment "
            "running on Linux Mint. It cannot guarantee correct menu "
            "behavior elsewhere. Menuet will now close."
        )

        Gtk.MessageDialog.__init__(
            self,
            transient_for=parent,
            modal=True,
            message_type=Gtk.MessageType.ERROR,
            buttons=Gtk.ButtonsType.CLOSE,
            text=primary,
            use_header_bar=use_headerbar,
        )
        self.set_title(title)
        self.format_secondary_markup(secondary)
        self.connect("response", self.response_cb)

    def response_cb(self, widget, user_data):
        widget.destroy()
