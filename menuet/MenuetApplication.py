#!/usr/bin/python3
# SPDX-License-Identifier: GPL-3.0-only
#   Menu Editor & Launcher Recovery for Linux Mint Cinnamon
#   Copyright (C) 2012-2024 Sean Davis <sean@bluesabre.org>
#   Copyright (C) 2016-2018 OmegaPhil <OmegaPhil@startmail.com>
#   Copyright (C) 2026 schnee-and-tetra <308144300+schnee-tetra@users.noreply.github.com>
import gettext
import hashlib
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import time

_ = gettext.gettext

from gi import require_version

require_version("Gtk", "3.0")
from gi.repository import Gdk, Gio, GLib, GObject, Gtk

from . import (
    Dialogs,
    MenuEditor,
    MenuetHistory,
    MenuetTreeview,
    MenuetXdg,
    util,
)
from .ApplicationEditor import ApplicationEditor
from .CategoryEditor import category_lookup
from .Headerbar import Headerbar
from .Toolbar import Toolbar
from .util import (
    MenuItemTypes,
    check_keypress,
    getCurrentDesktop,
    getRelatedKeys,
    getRelativeName,
)

require_version("Gtk", "3.0")

logger = logging.getLogger("menuet")

session = os.getenv("DESKTOP_SESSION", "")
root = os.getuid() == 0

current_desktop = getCurrentDesktop()


class MenuetWindow(Gtk.ApplicationWindow):
    """The Menuet application window."""

    __gsignals__ = {  # noqa: RUF012
        "about": (GObject.SIGNAL_RUN_FIRST, GObject.TYPE_NONE, (GObject.TYPE_BOOLEAN,)),
        "help": (GObject.SIGNAL_RUN_FIRST, GObject.TYPE_NONE, (GObject.TYPE_BOOLEAN,)),
        "quit": (GObject.SIGNAL_RUN_FIRST, GObject.TYPE_NONE, (GObject.TYPE_BOOLEAN,)),
        "action-enabled": (
            GObject.SignalFlags.RUN_FIRST,
            GObject.TYPE_NONE,
            (
                GObject.TYPE_STRING,
                GObject.TYPE_BOOLEAN,
            ),
        ),
    }

    def __init__(self, app, headerbar_pref=True):
        """Initialize the Menuet application."""
        self.desktop_environment_lockout()
        self.root_lockout()

        self.action_items = {}
        # Set up icons
        base_dir = os.path.dirname(os.path.abspath(__file__))
        self.local_icons_dir = os.path.normpath(os.path.join(base_dir, "assets"))
        if not os.path.exists(self.local_icons_dir):
            base_dir = os.path.dirname(os.path.abspath(__file__))
            self.local_icons_dir = os.path.normpath(
                os.path.join(base_dir, "..", "assets")
            )
        if os.path.exists(self.local_icons_dir):
            icon_theme = Gtk.IconTheme.get_default()
            icon_theme.prepend_search_path(self.local_icons_dir)

        # Set up History
        self.history = MenuetHistory.History()
        self.history.connect("undo-changed", self.on_undo_changed)
        self.history.connect("redo-changed", self.on_redo_changed)
        self.history.connect("revert-changed", self.on_revert_changed)

        # Steal the window contents for the GtkApplication.
        self.configure_application_window(app)

        self.values = {}
        self.is_registered_status = False
        user_data_dir = GLib.get_user_data_dir()  # Usually '~/.local/share'
        self.user_apps_dir = os.path.join(user_data_dir, "applications")
        self.user_dirs_dir = os.path.join(user_data_dir, "desktop-directories")
        self.user_cache_menu_dir = os.path.join(GLib.get_user_cache_dir(), "menus")
        # Set up the actions and toolbar
        self.configure_application_actions()

        add_menu = self.get_add_menu()

        self.search_box = Gtk.SearchEntry.new()
        self.search_box.set_placeholder_text(_("Search"))
        self.search_box.set_icon_from_icon_name(
            Gtk.EntryIconPosition.PRIMARY, "edit-find-symbolic"
        )
        self.search_box.connect("icon-press", self.on_search_cleared)

        self.use_headerbar = headerbar_pref
        if headerbar_pref:
            self.configure_headerbar(add_menu)
        else:
            self.configure_application_toolbar(add_menu)

        # Configure events for the headerbar or toolbar (they have the same
        # setup)
        self.connect_toolbar()
        self.configure_css()

        # Set up the application browser
        self.configure_application_treeview()
        self.configure_menu_restart_infobar()
        self.show_all()
        self.on_apps_browser_cursor_changed(None, None)

    def connect_toolbar(self):
        """Register toolbar and headerbar widgets for sensitivity management
        and wire "clicked" events for classic toolbar mode.
        """
        self.insert_action_item("add_button", self.add_button)
        # (widget, Gtk.Action name, initial sensitivity)
        toolbar_widgets = [
            (self.save_button, "save_launcher", False),
            (self.undo_button, "undo", False),
            (self.redo_button, "redo", False),
            (self.revert_button, "revert", False),
            (self.delete_button, "delete", False),
            (self.reload_treeview_btn, "reload_treeview", True),
            (self.register_cmenu_btn, "register_cmenu", False),
            (self.unregister_cmenu_btn, "unregister_cmenu", False),
            (self.restart_cinnamon_shell_btn, "restart_cinnamon_shell", True),
        ]
        if not self.use_headerbar:
            for widget, action_name, _sensitive in toolbar_widgets:
                widget.connect("clicked", self.activate_action_cb, action_name)
        for widget, action_name, sensitive in toolbar_widgets:
            widget.set_sensitive(sensitive)
            self.insert_action_item(action_name, widget)

    def insert_action_item(self, key, widget):
        if key not in self.action_items.keys():
            self.action_items[key] = []
        self.action_items[key].append(widget)

    def get_add_menu(self):
        menu = Gio.Menu.new()

        menu_items = {
            "app.add_launcher": _("Add _Launcher"),
            "app.add_directory": _("Add _Directory"),
            "app.add_separator": _("Add _Separator"),
        }

        for action_name, label in menu_items.items():
            menu.append(label, action_name)

        return menu

    def is_cinnamon_desktop(self):
        """Detect whether the Cinnamon desktop environment is active."""
        current_desktop = os.getenv("XDG_CURRENT_DESKTOP", "").lower()
        if current_desktop:
            return "cinnamon" in current_desktop
        session_name = os.getenv("DESKTOP_SESSION", "").lower()
        return "cinnamon" in session_name

    def is_linux_mint(self):
        """Detect whether the OS is Linux Mint."""
        os_release_id = ""
        try:
            with open("/etc/os-release", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("ID="):
                        os_release_id = (
                            line.split("=", 1)[1].strip().strip('"').strip("'").lower()
                        )
                        break
        except OSError:
            pass
        if os_release_id == "linuxmint":
            return True
        return os.path.exists("/etc/linuxmint/info")

    def desktop_environment_lockout(self):
        if not (self.is_cinnamon_desktop() and self.is_linux_mint()):
            # Translators: This error is displayed when the application is
            # run outside Linux Mint's Cinnamon desktop environment. The
            # application exits once the dialog is dismissed.
            dialog = Dialogs.UnsupportedDesktopDialog(None, False)
            dialog.run()
            sys.exit(1)

    def root_lockout(self):
        if root:
            # Translators: This error is displayed when the application is run
            # as a root user. The application exits once the dialog is
            # dismissed.
            primary = _("Menuet cannot be run as root.")

            docs_url = "https://github.com/schnee-and-tetra/menuet/"

            # Translators: This link goes to the online documentation with more
            # information.
            secondary = (
                _(
                    "Please see the "
                    "<a href='%s'>online documentation</a> "
                    "for more information."
                )
                % docs_url
            )

            dialog = Gtk.MessageDialog(
                message_type=Gtk.MessageType.ERROR,
                buttons=Gtk.ButtonsType.CLOSE,
                text=primary,
                use_header_bar=False,
            )
            dialog.format_secondary_markup(secondary)
            dialog.run()
            sys.exit(1)

    def menu_load_failure(self):
        primary = _("Menuet failed to load.")

        docs_url = "https://github.com/schnee-and-tetra/menuet/"

        # Translators: This link goes to the online documentation with more
        # information.
        secondary = (
            _(
                "The default menu could not be found. Please see the "
                "<a href='%s'>online documentation</a> "
                "for more information."
            )
            % docs_url
        )

        secondary += "\n\n<big><b>{}</b></big>".format(_("Diagnostics"))

        diagnostics = util.getMenuDiagnostics()
        for k, v in diagnostics.items():
            secondary += f"\n<b>{k}</b>: {v}"

        dialog = Gtk.MessageDialog(
            message_type=Gtk.MessageType.ERROR,
            buttons=Gtk.ButtonsType.CLOSE,
            text=primary,
            use_header_bar=False,
        )
        dialog.format_secondary_markup(secondary)

        label = self.find_secondary_label(dialog)
        if label is not None:
            label.set_selectable(True)

        dialog.run()
        sys.exit(1)

    def find_secondary_label(self, container):
        try:
            children = container.get_children()
            if len(children) == 0:
                return None
            if isinstance(children[0], Gtk.Label):
                return children[1]
            for child in children:
                label = self.find_secondary_label(child)
                if label is not None:
                    return label
        except AttributeError:
            pass
        except IndexError:
            pass
        return None

    def configure_application_window(self, app):
        window_title = "Menuet"

        # Initialize the GtkApplicationWindow.
        Gtk.Window.__init__(self, title=window_title, application=app)
        self.set_wmclass(window_title, "Menuet")

        # Restore the window properties.
        icon_path = util.find_icon_path()
        self.set_title("Menuet")
        if icon_path and os.path.exists(icon_path):
            self.set_icon_from_file(icon_path)
        self.set_default_size(1024, 768)
        self.set_size_request(640, 480)

        # Reparent the widgets.
        box = Gtk.Box.new(Gtk.Orientation.VERTICAL, 0)
        self.add(box)

        self.toolbar_container = Gtk.Box.new(Gtk.Orientation.VERTICAL, 0)
        box.pack_start(self.toolbar_container, False, False, 0)

        self.infobar_container = Gtk.Box.new(Gtk.Orientation.VERTICAL, 0)
        box.pack_start(self.infobar_container, False, False, 0)

        self.panes = Gtk.Paned.new(Gtk.Orientation.HORIZONTAL)
        box.pack_start(self.panes, True, True, 0)

        # Connect any window-specific events.
        self.connect("key-press-event", self.on_window_keypress_event)
        self.connect("delete-event", self.on_window_delete_event)

    def configure_css(self):
        screen = Gdk.Screen.get_default()
        if screen is None:
            return

        css = """
        #MenuetSidebarToolbar {
            border-left-width: 0;
            border-right-width: 0;
            border-bottom-width: 0;
            border-radius: 0;
        }
        #MenuetSidebarScroll.frame {
            border-left-width: 0;
            border-right-width: 0;
        }
        #helpbutton {
            padding: 0;
        }
        #hideybutton {
            padding: 0;
            border-radius: 0;
            min-height: 18px;
            min-width: 18px;
        }
        """

        style_provider = Gtk.CssProvider.new()
        style_provider.load_from_data(bytes(css.encode()))

        Gtk.StyleContext.add_provider_for_screen(
            screen, style_provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

    def configure_headerbar(self, add_menu):
        """Configure the headerbar (Modern environment)."""
        headerbar = Headerbar()
        # Official standard action-linked generation
        self.add_button = headerbar.add_menu_button_from_action(
            self.actions["add_launcher"], add_menu
        )
        self.save_button = headerbar.add_button_from_action(
            self.actions["save_launcher"]
        )
        self.undo_button = headerbar.add_button_from_action(self.actions["undo"])
        self.redo_button = headerbar.add_button_from_action(self.actions["redo"])
        self.revert_button = headerbar.add_button_from_action(self.actions["revert"])
        self.delete_button = headerbar.add_button_from_action(self.actions["delete"])
        self.reload_treeview_btn = headerbar.add_button_from_action(
            self.actions["reload_treeview"]
        )
        self.register_cmenu_btn = headerbar.add_button_from_action(
            self.actions["register_cmenu"]
        )
        self.unregister_cmenu_btn = headerbar.add_button_from_action(
            self.actions["unregister_cmenu"]
        )
        self.restart_cinnamon_shell_btn = headerbar.add_button_from_action(
            self.actions["restart_cinnamon_shell"]
        )

        headerbar.add_search(self.search_box)

        self.set_titlebar(headerbar)
        headerbar.show_all()

    def configure_application_actions(self):
        """Configure the GtkActions that are used in the Menuet
        application."""
        self.actions = {}

        # Add Launcher
        self.actions["add_launcher"] = Gtk.Action(
            name="add_launcher",
            # Translators: Add Launcher action label
            label=_("Add _Launcher…"),
            # Translators: Add Launcher action tooltip
            tooltip=_("Add Launcher…"),
            stock_id=Gtk.STOCK_NEW,
        )

        # Add Directory
        self.actions["add_directory"] = Gtk.Action(
            name="add_directory",
            # Translators: Add Directory action label
            label=_("Add _Directory…"),
            # Translators: Add Directory action tooltip
            tooltip=_("Add Directory…"),
            stock_id=Gtk.STOCK_NEW,
        )

        # Add Separator
        self.actions["add_separator"] = Gtk.Action(
            name="add_separator",
            # Translators: Add Separator action label
            label=_("_Add Separator…"),
            # Translators: Add Separator action tooltip
            tooltip=_("Add Separator…"),
            stock_id=Gtk.STOCK_NEW,
        )

        # Save Launcher
        self.actions["save_launcher"] = Gtk.Action(
            name="save_launcher",
            # Translators: Save Launcher action label
            label=_("_Save"),
            # Translators: Save Launcher action tooltip
            tooltip=_("Save"),
            stock_id=Gtk.STOCK_SAVE,
        )

        # Undo
        self.actions["undo"] = Gtk.Action(
            name="undo",
            # Translators: Undo action label
            label=_("_Undo"),
            # Translators: Undo action tooltip
            tooltip=_("Undo"),
            stock_id=Gtk.STOCK_UNDO,
        )

        # Redo
        self.actions["redo"] = Gtk.Action(
            name="redo",
            # Translators: Redo action label
            label=_("_Redo"),
            # Translators: Redo action tooltip
            tooltip=_("Redo"),
            stock_id=Gtk.STOCK_REDO,
        )

        # Revert
        self.actions["revert"] = Gtk.Action(
            name="revert",
            # Translators: Revert action label
            label=_("_Revert"),
            # Translators: Revert action tooltip
            tooltip=_("Revert"),
            stock_id=Gtk.STOCK_REVERT_TO_SAVED,
        )
        # Delete
        self.actions["delete"] = Gtk.Action(
            name="delete",
            # Translators: Delete action label
            label=_("_Delete"),
            # Translators: Delete action tooltip
            tooltip=_("Delete"),
            stock_id=Gtk.STOCK_DELETE,
        )
        # Reload / Refresh Action
        self.actions["reload_treeview"] = Gtk.Action(
            name="reload_treeview",
            # Translators: Reload action label
            label=_("Reload _Treeview"),
            # Translators: Reload action tooltip
            tooltip=_("Refresh and reload cache database"),
            icon_name="reload_treeview",
        )
        # Install / Register Action
        self.actions["register_cmenu"] = Gtk.Action(
            name="register_cmenu",
            # Translators: Install action label
            label=_("_Register Cinnamon Menu"),
            # Translators: Install action tooltip
            tooltip=_("Register and display launcher in Cinnamon Menu"),
            icon_name="register_cmenu",
        )
        # Uninstall / Unregister Action
        self.actions["unregister_cmenu"] = Gtk.Action(
            name="unregister_cmenu",
            # Translators: Uninstall action label
            label=_("_Unregister Cinnamon Menu"),
            # Translators: Uninstall action tooltip
            tooltip=_("Unregister and hide launcher from the Cinnamon Menu"),
            icon_name="unregister_cmenu",
        )
        # Force Apply/Refresh GMenu Action
        self.actions["restart_cinnamon_shell"] = Gtk.Action(
            name="restart_cinnamon_shell",
            # Translators: restart_cinnamon_shell action label
            label=_("Restart Cinnamon _Shell"),
            # Translators: restart_cinnamon_shell action tooltip
            tooltip=_("Restart Cinnamon Shell and reload desktop environment"),
            icon_name="linuxmint-logo-ring",
        )
        # Quit
        self.actions["quit"] = Gtk.Action(
            name="quit",
            # Translators: Quit action label
            label=_("_Quit"),
            # Translators: Quit action tooltip
            tooltip=_("Quit"),
            stock_id=Gtk.STOCK_QUIT,
        )

        # About
        self.actions["about"] = Gtk.Action(
            name="about",
            # Translators: About action label
            label=_("_About"),
            # Translators: About action tooltip
            tooltip=_("About"),
            stock_id=Gtk.STOCK_ABOUT,
        )

        # Connect the GtkAction events.
        self.actions["add_launcher"].connect("activate", self.on_add_launcher_cb)
        self.actions["add_directory"].connect("activate", self.on_add_directory_cb)
        self.actions["add_separator"].connect("activate", self.on_add_separator_cb)
        self.actions["save_launcher"].connect("activate", self.on_save_launcher_cb)
        self.actions["undo"].connect("activate", self.on_undo_cb)
        self.actions["redo"].connect("activate", self.on_redo_cb)
        self.actions["revert"].connect("activate", self.on_revert_cb)
        self.actions["delete"].connect("activate", self.on_delete_cb)
        self.actions["reload_treeview"].connect("activate", self.on_reload_treeview_cb)
        self.actions["register_cmenu"].connect("activate", self.on_register_cmenu_cb)
        self.actions["unregister_cmenu"].connect(
            "activate", self.on_unregister_cmenu_cb
        )
        self.actions["restart_cinnamon_shell"].connect(
            "activate", self.on_restart_cinnamon_shell_cb
        )
        self.actions["quit"].connect("activate", self.on_quit_cb)
        self.actions["about"].connect("activate", self.on_about_cb)

    def configure_menu_restart_infobar(self):
        self.menu_restart_infobar = Gtk.InfoBar.new()
        self.menu_restart_infobar.set_message_type(Gtk.MessageType.WARNING)
        self.menu_restart_infobar.set_no_show_all(True)
        self.infobar_container.add(self.menu_restart_infobar)

        content = self.menu_restart_infobar.get_content_area()

        label = Gtk.Label.new(_("Your applications menu may need to be restarted."))
        label.show()
        content.add(label)

        self.menu_restart_infobar.add_button(
            _("Restart menu..."), Gtk.ResponseType.ACCEPT
        )

        self.menu_restart_infobar.set_show_close_button(True)
        self.menu_restart_infobar.set_default_response(Gtk.ResponseType.CLOSE)

        self.menu_restart_infobar.connect(
            "response", self.on_menu_restart_infobar_response
        )

    def on_menu_restart_infobar_response(self, infobar, response_id):
        if response_id == Gtk.ResponseType.CLOSE:
            infobar.hide()
        elif response_id == Gtk.ResponseType.ACCEPT:
            self.execute_cinnamon_refresh()
            infobar.hide()

    def configure_application_toolbar(self, add_menu):
        """Configure the application toolbar (Classic/Traditional environment)."""
        toolbar = Toolbar()
        self.toolbar_container.add(toolbar)

        self.add_button = toolbar.add_menu_button("list-add", _("Add..."), add_menu)

        toolbar.add_separator()

        self.save_button = toolbar.add_button("document-save", _("Save"))

        toolbar.add_separator()

        self.undo_button = toolbar.add_button("edit-undo", _("Undo"))
        self.redo_button = toolbar.add_button("edit-redo", _("Redo"))

        toolbar.add_separator()

        self.revert_button = toolbar.add_button("document-revert", _("Revert"))

        toolbar.add_separator()
        self.delete_button = toolbar.add_button("edit-delete", _("Delete..."))
        toolbar.add_separator()
        self.reload_treeview_btn = toolbar.add_button(
            "reload_treeview_color", _("Reload Treeview")
        )
        self.register_cmenu_btn = toolbar.add_button(
            "register_cmenu_color", _("Register Cinnamon Menu")
        )
        self.unregister_cmenu_btn = toolbar.add_button(
            "unregister_cmenu_color", _("Unregister Cinnamon Menu")
        )
        self.restart_cinnamon_shell_btn = toolbar.add_button(
            "linuxmint-logo-ring", _("Restart Cinnamon Shell")
        )
        self.insert_action_item("add_launcher", self.add_button)
        self.insert_action_item("save_launcher", self.save_button)
        self.insert_action_item("undo", self.undo_button)
        self.actions["undo"].set_sensitive(False)
        self.insert_action_item("redo", self.redo_button)
        self.actions["redo"].set_sensitive(False)
        self.insert_action_item("revert", self.revert_button)
        self.insert_action_item("delete", self.delete_button)
        self.insert_action_item("reload_treeview", self.reload_treeview_btn)
        self.insert_action_item("register_cmenu", self.register_cmenu_btn)
        self.insert_action_item("unregister_cmenu", self.unregister_cmenu_btn)
        self.insert_action_item(
            "restart_cinnamon_shell", self.restart_cinnamon_shell_btn
        )
        separator = toolbar.add_separator()
        separator.set_draw(False)
        separator.set_expand(True)

        toolbar.add_search(self.search_box)

        toolbar.show_all()

    def configure_application_treeview(self):
        """Configure the menu-browsing GtkTreeView."""
        self.treeview = MenuetTreeview.Treeview(self)
        if not self.treeview.loaded:
            self.menu_load_failure()

        self.panes.add(self.treeview)

        self.editor = ApplicationEditor(use_headerbar=self.use_headerbar)
        self.panes.add(self.editor)

        self.treeview.set_search_entry(self.search_box)
        self.search_box.connect("changed", self.on_app_search_changed, True)
        self.treeview.set_can_select_function(self.get_can_select)
        self.treeview.connect("cursor-changed", self.on_apps_browser_cursor_changed)
        self.treeview.connect(
            "add-directory-enabled", self.on_apps_browser_add_directory_enabled
        )
        self.treeview.connect(
            "requires-menu-reload", self.on_apps_browser_requires_menu_reload
        )
        self.treeview.reset_cursor()

        self.editor.connect("value-changed", self.on_smart_widget_changed)

    def get_can_select(self):
        """Check if it's safe to leave the current selection."""
        if not self.save_button.get_sensitive():
            return True

        dialog = Dialogs.SaveOnLeaveDialog(self, self.use_headerbar)
        response = dialog.run()
        dialog.destroy()

        # Cancel prevents leaving this launcher.
        if response == Gtk.ResponseType.CANCEL:
            return False

        # Don't Save allows leaving this launcher, deleting 'new'.
        if response == Gtk.ResponseType.NO:
            filename = self.treeview.get_selected_filename()
            if filename is None:
                self.delete_launcher()
                return False
            return True

        # Save and move on.
        self.save_launcher()
        return True

    def activate_action_cb(self, widget, action_name):
        """Activate the specified GtkAction."""
        self.actions[action_name].activate()

    # History Signals
    def on_undo_changed(self, history, enabled):
        """Toggle undo functionality when history is changed."""
        self.undo_button.set_sensitive(enabled)

    def on_redo_changed(self, history, enabled):
        """Toggle redo functionality when history is changed."""
        self.redo_button.set_sensitive(enabled)

    def on_revert_changed(self, history, enabled):
        """Toggle revert functionality when history is changed."""
        self.revert_button.set_sensitive(enabled)
        self.save_button.set_sensitive(enabled)
        self.actions["save_launcher"].set_sensitive(enabled)
        self.emit("action-enabled", "save_launcher", enabled)

    # Generic Treeview functions
    def treeview_add(self, treeview, row_data):
        """Append the specified row_data to the treeview."""
        model = treeview.get_model()
        model.append(row_data)

    def treeview_remove(self, treeview):
        """Remove the selected row from the treeview."""
        model, treeiter = treeview.get_selection().get_selected()
        if model is not None and treeiter is not None:
            model.remove(treeiter)

    def treeview_clear(self, treeview):
        """Remove all items from the treeview."""
        model = treeview.get_model()
        model.clear()

    def treeview_get_selected_text(self, treeview, column):
        """Return selected item's text value stored at the given column (text
        is the expected data type)."""

        # Note that the categories treeview is configured to only allow one row
        # to be selected
        model, treeiter = treeview.get_selection().get_selected()
        if model is not None and treeiter is not None:
            return model[treeiter][column]
        else:
            return ""

    # Categories

    def on_smart_widget_changed(self, widget, key, value):
        self.set_value(key, value, False)

        if key == "Filename":
            self.set_editor_filename(value)

    def cleanup_actions(self):
        """Cleanup the Actions treeview. Remove any rows where name or command
        have not been set."""
        self.editor.remove_incomplete_actions()

    # Window events
    def on_window_keypress_event(self, widget, event, user_data=None):
        """Handle window keypress events."""
        # Ctrl-N (Add New Launcher)
        if check_keypress(event, ["Control", "n"]):
            self.actions["add_launcher"].activate()
            return True
        # Ctrl-Delete (Delete Selected Item)
        if check_keypress(event, ["Control", "Delete"]):
            self.actions["delete_launcher"].activate()
            return True
        # Alt-Up (Move Item Up)
        if check_keypress(event, ["Mod1", "Up"]):
            self.actions["move_up"].activate()
            return True
        # Alt-Down (Move Item Down)
        if check_keypress(event, ["Mod1", "Down"]):
            self.actions["move_down"].activate()
            return True
        # Ctrl-F (Find)
        if check_keypress(event, ["Control", "f"]):
            self.search_box.grab_focus()
            return True
        # Ctrl-S (Save)
        if check_keypress(event, ["Control", "s"]):
            self.actions["save_launcher"].activate()
            return True
        # Ctrl-Q (Quit)
        if check_keypress(event, ["Control", "q"]):
            self.actions["quit"].activate()
            return True
        return False

    def on_window_delete_event(self, widget, event):
        """Save changes on close."""
        if not self.save_button.get_sensitive():
            return False

        # Unsaved changes
        dialog = Dialogs.SaveOnCloseDialog(self, self.use_headerbar)
        response = dialog.run()
        dialog.destroy()

        # Cancel prevents the application from closing.
        if response == Gtk.ResponseType.CANCEL:
            return True
        # Don't Save allows the application to close.
        if response == Gtk.ResponseType.NO:
            return False

        # Save and close.
        self.save_launcher()
        return False

    # Applications Treeview
    def on_apps_browser_requires_menu_reload(self, widget, required):
        self.menu_restart_infobar.show()

    def on_apps_browser_add_directory_enabled(self, widget, enabled):
        """Update the Add Directory menu item when the selected row is
        changed."""
        # Always allow creating sub directories
        enabled = True

        self.actions["add_directory"].set_sensitive(enabled)
        self.emit("action-enabled", "add_directory", enabled)

    def on_apps_browser_cursor_changed(self, widget, value):
        """Update the editor frame when the selected row is changed."""
        # Block re-entry during active I/O to prevent data corruption and crashes.

        missing = False

        # Clear history
        self.history.clear()

        # Hide the Name and Comment editors
        self.editor.cancel()

        # Prevent updates to history.
        self.history.block()
        try:
            # Clear the individual entries.
            for key in [
                "Exec",
                "Path",
                "Terminal",
                "StartupNotify",
                "NoDisplay",
                "GenericName",
                "TryExec",
                "OnlyShowIn",
                "NotShowIn",
                "MimeType",
                "Keywords",
                "StartupWMClass",
                "Implements",
                "Categories",
                "Hidden",
                "DBusActivatable",
                "PrefersNonDefaultGPU",
                "X-GNOME-UsesNotifications",
            ]:
                self.set_value(key, None)

            # Clear the Actions and Icon.
            self.set_value("Actions", None, store=True)
            self.set_value("Icon", None, store=True)

            model, row_data = self.treeview.get_selected_row_data()
            if row_data is None:
                return

            item_type = row_data[MenuEditor.COL_TYPE]

            # If the selected row is a separator, hide the editor.
            if item_type == MenuItemTypes.SEPARATOR:
                self.editor.hide()
                # Translators: Separator menu item
                self.set_value("Name", _("Separator"), store=True)
                self.set_value("Comment", "", store=True)
                self.set_value("Filename", None, store=True)
                self.set_value("Type", "Separator", store=True)

            # Otherwise, show the editor and update the values.
            else:
                filename = self.treeview.get_selected_filename()
                new_launcher = filename is None

                # Check if this file still exists
                if (not new_launcher) and (not os.path.isfile(filename)):
                    # If it does not, try to fallback...
                    basename = getRelativeName(filename)
                    filename = util.getSystemLauncherPath(basename)
                    if filename is not None:
                        row_data[MenuEditor.COL_FILENAME] = filename
                        self.treeview.update_launcher_instances(filename, row_data)

                if new_launcher or (filename is not None):
                    self.editor.show()
                    name = row_data[MenuEditor.COL_NAME]
                    comment = row_data[MenuEditor.COL_COMMENT]

                    # Top-level items are categories at the root of the menu.
                    # Lock name and icon for the 'Unregistered Apps' node to prevent editing.
                    parent_node = self.treeview.get_parent()
                    if parent_node is not None and len(parent_node) >= 2:
                        is_top_level = parent_node[1] is None
                    else:
                        is_top_level = False
                    if is_top_level and name == _("Unregistered Apps"):
                        self.editor.set_name_editable(False)
                        self.editor.set_icon_editable(False)
                        self.editor.set_comment_editable(False)
                    else:
                        self.editor.set_name_editable(True)
                        self.editor.set_icon_editable(True)
                        self.editor.set_comment_editable(True)

                    self.set_value(
                        "Icon", row_data[MenuEditor.COL_ICON_NAME], store=True
                    )
                    self.set_value("Name", name, store=True)
                    self.set_value("Comment", comment, store=True)
                    self.set_value("Filename", filename, store=True)

                    if item_type == MenuItemTypes.APPLICATION:
                        self.editor.show_all()
                        entry = MenuetXdg.MenuetDesktopEntry(filename)
                        for key in getRelatedKeys(item_type, key_only=True):
                            if key in [
                                "Actions",
                                "Comment",
                                "Filename",
                                "Icon",
                                "Name",
                            ]:
                                continue
                            self.set_value(key, entry[key], store=True)
                        self.set_value("Actions", entry.get_actions(), store=True)
                        self.set_value("Type", "Application")
                    else:
                        entry = MenuetXdg.MenuetDesktopEntry(filename)
                        for key in getRelatedKeys(item_type, key_only=True):
                            if key in ["Comment", "Filename", "Icon", "Name"]:
                                continue
                            self.set_value(key, entry[key], store=True)
                        self.set_value("Type", "Directory")

                else:
                    dialog = Dialogs.LauncherRemovedDialog(self, self.use_headerbar)
                    dialog.run()
                    dialog.destroy()
                    missing = True
        finally:
            self.history.unblock()

        if self.treeview.get_parent()[1] is None:
            self.treeview.set_sortable(False)
            move_up_enabled = not self.treeview.is_first()
            move_down_enabled = not self.treeview.is_last()
        else:
            self.treeview.set_sortable(True)
            if item_type in [
                MenuItemTypes.APPLICATION,
                MenuItemTypes.LINK,
                MenuItemTypes.SEPARATOR,
            ]:
                move_up_enabled = True
                move_down_enabled = True
            else:
                move_up_enabled = not self.treeview.is_first()
                move_down_enabled = not self.treeview.is_last()

        self.treeview.set_move_up_enabled(move_up_enabled)
        self.treeview.set_move_down_enabled(move_down_enabled)

        # Remove this item if it happens to be gone.
        if missing:
            self.delete_launcher()

    def on_app_search_changed(self, widget, expand=False):
        """Update search results when query text is modified."""
        query = widget.get_text()
        is_empty = len(query) == 0

        # Enable action buttons when search is empty, disable them during active search.
        add_actions_enabled = is_empty

        # Toggle clear icon and searchable state based on query presence.
        if is_empty:
            widget.set_icon_from_icon_name(Gtk.EntryIconPosition.SECONDARY, None)
            self.treeview.set_searchable(False, expand)
        else:
            widget.set_icon_from_icon_name(
                Gtk.EntryIconPosition.SECONDARY, "edit-clear-symbolic"
            )
            self.treeview.set_searchable(True)

        # Update sensitivity for all add-related actions and widgets at once.
        action_names = [
            "add_launcher",
            "add_directory",
            "add_separator",
            "add_button",
        ]
        for name in action_names:
            if name in self.action_items:
                for action_widget in self.action_items[name]:
                    action_widget.set_sensitive(add_actions_enabled)
            if name in self.actions:
                self.actions[name].set_sensitive(add_actions_enabled)
                self.emit("action-enabled", name, add_actions_enabled)

        # Run search filter if query exists.
        if not is_empty:
            self.treeview.search(self.search_box.get_text())

        # Control delete button sensitivity and tooltips (LP: #1751616).
        self.delete_button.set_sensitive(is_empty)
        if is_empty:
            self.delete_button.set_tooltip_text(_("Delete..."))
        else:
            self.delete_button.set_tooltip_text(
                _("You cannot delete this file while a search is active.")
            )

    def on_search_cleared(self, widget, event, user_data=None):
        """Generic search cleared callback function."""
        widget.set_text("")

    # Setters and Getters
    def set_editor_filename(self, filename):
        """Set the editor filename."""
        # Since the filename has changed, check if it is now writable...
        if filename is None or os.access(filename, os.W_OK):
            self.delete_button.set_sensitive(True)
            self.delete_button.set_tooltip_text(_("Delete..."))
        else:
            self.delete_button.set_sensitive(False)
            self.delete_button.set_tooltip_text(
                # Translators: This error is displayed when the user does not
                # have sufficient file system permissions to delete the
                # selected file.
                _("You do not have permission to delete this file.")
            )

        # Disable deletion if we're in search mode (LP: #1751616)
        if self.search_box.get_text() != "":
            self.delete_button.set_sensitive(False)
            self.delete_button.set_tooltip_text(
                _("You cannot delete this file while a search is active.")
            )

    def get_inner_value(self, key):
        """Get the value stored for key."""
        return self.values.get(key)

    def set_inner_value(self, key, value):
        """Set the value stored for key."""
        self.values[key] = value

    # Reference: Desktop Entry Specification (Quoting and Field Codes)
    # https://specifications.freedesktop.org/desktop-entry-spec/latest/

    def set_value(self, key, value, adjust_widget=True, store=False):
        """Set the DesktopSpec key, value pair in the editor."""
        if store:
            self.history.store(key, value)
        if not self.get_inner_value(key) == value:
            self.history.append(key, self.get_inner_value(key), value)
            self.set_inner_value(key, value)
        if not adjust_widget:
            return
        else:
            self.editor.set_value(key, value)
            if key == "Filename":
                self.set_editor_filename(value)

    def get_value(self, key):
        """Return the value stored for the specified key."""
        return self.editor.get_value(key)

    # Action Functions
    def add_launcher(self):
        """Add Launcher callback function."""
        # Translators: Placeholder text for a newly created launcher.
        name = _("New Launcher")
        display_name = name
        # Translators: Placeholder text for a newly created launcher's
        # description.
        comment = ""
        categories = ""
        item_type = MenuItemTypes.APPLICATION
        icon_name = "application-x-executable"
        icon = Gio.ThemedIcon.new(icon_name)
        filename = None
        executable = ""
        new_row_data = [
            name,
            display_name,
            comment,
            executable,
            categories,
            item_type,
            icon,
            icon_name,
            filename,
            True,
        ]

        model, parent_data = self.treeview.get_parent_row_data()
        model, row_data = self.treeview.get_selected_row_data()

        # Exit early if no row is selected (LP #1556664)
        if not row_data:
            return

        # Add to the treeview on the current level or as a child of a selected
        # directory
        dir_selected = row_data[MenuEditor.COL_TYPE] == MenuItemTypes.DIRECTORY
        if dir_selected:
            self.treeview.add_child(new_row_data)
        else:
            self.treeview.append(new_row_data)

        if parent_data is not None and not dir_selected:
            # A parent item has been found, and the current selection is not a
            # directory, so the resulting item will be placed at the current level
            # fetch the parent's categories
            parent_directory = parent_data[MenuEditor.COL_FILENAME]

        elif parent_data is not None and dir_selected:
            # A directory lower than the top-level has been selected - the
            # launcher will be added into it (e.g. as the first item),
            # therefore it essentially has a parent of the current selection
            parent_directory = row_data[MenuEditor.COL_FILENAME]

        else:
            # Parent was not found, this is a toplevel category
            parent_directory = None

        self.editor.clear_categories()
        self.editor.insert_required_categories(parent_directory)

        self.actions["save_launcher"].set_sensitive(True)
        self.emit("action-enabled", "save_launcher", True)
        self.save_button.set_sensitive(True)

        self.editor.take_focus()

    def add_directory(self):
        """Add Directory callback function."""
        # Translators: Placeholder text for a newly created directory.
        name = _("New Directory")
        display_name = name
        # Translators: Placeholder text for a newly created directory's
        # description.
        comment = ""
        categories = ""
        item_type = MenuItemTypes.DIRECTORY
        icon_name = "folder"
        icon = Gio.ThemedIcon.new(icon_name)
        filename = None
        executable = ""
        row_data = [
            name,
            display_name,
            comment,
            executable,
            categories,
            item_type,
            icon,
            icon_name,
            filename,
            True,
            True,
        ]

        self.treeview.append(row_data)

        self.actions["save_launcher"].set_sensitive(True)
        self.emit("action-enabled", "save_launcher", True)
        self.save_button.set_sensitive(True)

        self.editor.take_focus()

    def add_separator(self):
        """Add Separator callback function."""
        name = _("Separator")
        display_name = name
        # Translators: Separator menu item
        tooltip = _("Separator")
        categories = ""
        filename = None
        icon_name = "content-loading-symbolic"
        icon = Gio.ThemedIcon.new(icon_name)
        item_type = MenuItemTypes.SEPARATOR
        filename = None
        executable = ""
        row_data = [
            name,
            display_name,
            tooltip,
            executable,
            categories,
            item_type,
            icon,
            icon_name,
            filename,
            False,
            False,
        ]

        self.treeview.append(row_data)

        self.save_button.set_sensitive(False)

        self.treeview.update_menus()

    def list_str_to_list(self, value):
        if isinstance(value, list):
            return value
        values = []
        for val in value.replace(",", ";").split(";"):
            cleaned = val.strip()
            if cleaned:
                values.append(cleaned)
        return values

    def _run_update_desktop_database(self, directory):
        if directory and os.path.exists(directory):
            subprocess.Popen(
                ["update-desktop-database", directory],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

    def _format_desktop_value(self, keyfile, group, key):
        """Safely extract values from GLib.KeyFile and format them to specification."""
        try:
            # Explicitly restrict list formatting (semicolon separation) to designated keys only
            list_keys = {"Categories", "Keywords", "OnlyShowIn"}

            if key in list_keys:
                try:
                    val_list = keyfile.get_string_list(group, key)
                    if isinstance(val_list, tuple):
                        val_list = val_list[0]
                    cleaned = [
                        str(item).strip() for item in val_list if str(item).strip()
                    ]
                    return ";".join(cleaned) + ";" if cleaned else ""
                except (GLib.Error, KeyError, ValueError):
                    pass

            # Handle boolean values
            try:
                val_bool = keyfile.get_boolean(group, key)
                if isinstance(val_bool, tuple):
                    val_bool = val_bool[0]
                return "true" if val_bool else "false"
            except (GLib.Error, KeyError, ValueError):
                pass

            # Handle double/float values
            try:
                val_double = keyfile.get_double(group, key)
                if isinstance(val_double, tuple):
                    val_double = val_double[0]
                return str(val_double)
            except (GLib.Error, KeyError, ValueError):
                pass

            # Fallback to standard string extraction for all other keys
            val_str = keyfile.get_string(group, key)
            if isinstance(val_str, tuple):
                val_str = val_str[0]
            return str(val_str)

        except (GLib.Error, KeyError, ValueError):
            return None

    def _validate_desktop(self, filename):
        """Perform validation and apply fallback states if validation fails."""
        validation_result = util.validate_desktop_file(filename)
        if validation_result is not None:
            self.is_registered_status = False
            self.set_value("OnlyShowIn", "Old;", adjust_widget=True, store=False)
            self.values["OnlyShowIn"] = "Old;"
            return True
        return False

    def write_desktop_file_custom(self, filename, keyfile):
        """Safely export GLib.KeyFile contents into standard .desktop format."""
        try:
            # Helper function to generate lines from keyfile
            def generate_lines(kf):
                lines = []
                groups_res = kf.get_groups()
                groups = groups_res[0] if isinstance(groups_res, tuple) else groups_res
                if "Desktop Entry" in groups:
                    groups.remove("Desktop Entry")
                    groups.insert(0, "Desktop Entry")
                for group in groups:
                    lines.append(f"[{group}]\n")
                    keys_res = kf.get_keys(group)
                    keys = keys_res[0] if isinstance(keys_res, tuple) else keys_res
                    if group == "Desktop Entry":
                        ordered_preferred = [
                            "Type",
                            "Name",
                            "GenericName",
                            "Comment",
                            "Exec",
                            "Icon",
                            "Terminal",
                            "Categories",
                            "Keywords",
                            "OnlyShowIn",
                            "NoDisplay",
                            "Actions",
                            "Version",
                        ]
                        sorted_keys = [k for k in ordered_preferred if k in keys]
                        sorted_keys.extend([k for k in keys if k not in sorted_keys])
                        keys = sorted_keys
                    for key in keys:
                        val_str = self._format_desktop_value(kf, group, key)
                        if val_str is not None:
                            lines.append(f"{key}={val_str}\n")
                    lines.append("\n")
                return lines

            # Initial write to disk
            lines = generate_lines(keyfile)
            with open(filename, "w", encoding="utf-8") as f:
                f.writelines(lines)
            os.chmod(filename, 0o755)

            # Validate and apply fallback if validation fails
            if self._validate_desktop(filename):
                # Update keyfile with the fallback value and re-write to disk
                keyfile.set_string("Desktop Entry", "OnlyShowIn", "Old;")
                lines = generate_lines(keyfile)
                with open(filename, "w", encoding="utf-8") as f:
                    f.writelines(lines)
                os.chmod(filename, 0o755)

            return True

        except (GLib.Error, OSError) as e:
            logger.error(f"Failed to write desktop file custom: {e}")
            return False

    def write_launcher(self, filename):
        """Save the current launcher values via GLib.KeyFile parsing loops."""

        keyfile = GLib.KeyFile.new()

        for key, ktype, required in getRelatedKeys(self.get_value("Type")):
            if key == "Version":
                keyfile.set_string("Desktop Entry", "Version", "1.1")
                continue

            if key == "Actions":
                action_list = []
                for show, name, displayed, command in self.editor.get_actions():
                    group_name = f"Desktop Action {name}"
                    keyfile.set_string(group_name, "Name", displayed)
                    keyfile.set_string(group_name, "Exec", command)
                    if show:
                        action_list.append(name)
                keyfile.set_string_list("Desktop Entry", key, action_list)
                continue

            value = self.get_value(key)
            if ktype is str and len(value) > 0:
                keyfile.set_string("Desktop Entry", key, value)
            if ktype is float and value != 0:
                keyfile.set_double("Desktop Entry", key, value)
            if ktype is bool and value is not False:
                keyfile.set_boolean("Desktop Entry", key, value)
            if ktype is list:
                value = self.list_str_to_list(value)
                if len(value) > 0:
                    keyfile.set_string_list("Desktop Entry", key, value)

        return self.write_desktop_file_custom(filename, keyfile)

    def _unblock_history(self):
        """Ensure history is unblocked for both window and editor."""
        self.history.unblock()
        if hasattr(self, "editor") and hasattr(self.editor, "history"):
            self.editor.history.unblock()

    def save_launcher(self, temp=False):
        """Save the current launcher details, remove from the current directory
        if it no longer has the required category."""

        item_type = None
        original_filename = None
        filename = None
        key_temporary = "menuet-temporary-"

        if temp:
            filename = tempfile.mkstemp(".desktop", key_temporary)[1]
        else:
            original_filename = self.get_value("Filename")
            item_type = self.get_value("Type")
            name = self.get_value("Name")

            if original_filename and key_temporary in original_filename:
                safe_name = "".join(
                    [c if c.isalnum() or c in "._-" else "-" for c in name]
                )
                base_dir = os.path.dirname(original_filename)
                original_filename = os.path.join(base_dir, f"{safe_name}.desktop")

            test_filename = util.getSaveFilename(
                name, original_filename, item_type, force_update=True
            )
            if (
                original_filename
                and os.path.abspath(original_filename) != os.path.abspath(test_filename)
                and os.path.exists(test_filename)
            ):
                use_hb = getattr(self, "use_headerbar", False)
                dialog = Dialogs.DuplicateLauncherDialog(self, item_type, use_hb)
                response = dialog.run()
                dialog.destroy()
                if response == Gtk.ResponseType.YES:
                    unique_id = int(time.time() * 1000) % 10000
                    name = f"{name}_{unique_id}"
                else:
                    self._unblock_history()
                    return False
            filename = util.getSaveFilename(name, original_filename, item_type)

        logger.debug(f'Saving launcher as "{filename}"')

        if not temp:
            model, row_data = self.treeview.get_selected_row_data()
            if row_data is None:
                dialog = Dialogs.SaveErrorDialog(self, filename, self.use_headerbar)
                dialog.run()
                self._unblock_history()
                return False

            item_type = row_data[MenuEditor.COL_TYPE]

            model, parent_data = self.treeview.get_parent_row_data()
            parent_directory = (
                parent_data[MenuEditor.COL_FILENAME]
                if parent_data is not None
                else None
            )

            self.history.block()
            try:
                self.editor.insert_required_categories(parent_directory)
                self.cleanup_actions()
            finally:
                self.history.unblock()

        try:
            if not self.write_launcher(filename):
                dialog = Dialogs.SaveErrorDialog(self, filename, self.use_headerbar)
                dialog.run()
                self._unblock_history()
                return False

            if temp:
                self._unblock_history()
                return filename

            # Clean up zombie file if path/ID has changed.
            if original_filename and os.path.abspath(
                original_filename
            ) != os.path.abspath(filename):
                if os.path.exists(original_filename):
                    try:
                        selection = self.treeview.view.get_selection()
                        sel_model, treeiter = selection.get_selected()
                        if treeiter is not None:
                            self.treeview.xdg_menu_uninstall(
                                sel_model, treeiter, original_filename
                            )
                    except (GLib.Error, TypeError, AttributeError) as e:
                        logger.error(f"xdg_menu_uninstall failed: {e}")

                    try:
                        os.remove(original_filename)
                    except OSError as e:
                        logger.error(f"Failed to remove physical file: {e}")

                row_data[MenuEditor.COL_FILENAME] = filename

            # Register/update with system menus and sync state.
            # self.treeview.xdg_menu_install(filename)
            self.set_value("Filename", filename)

            name = self.get_value("Name")
            comment = self.get_value("Comment")
            executable = self.get_value("Exec")
            categories = self.get_value("Categories")
            icon_name = self.get_value("Icon")
            hidden = self.get_value("Hidden") or self.get_value("NoDisplay")

            self.treeview.update_selected(
                name,
                comment,
                executable,
                categories,
                item_type,
                icon_name,
                filename,
                not hidden,
            )
            self.history.clear()
            self.treeview.update_launcher_instances(original_filename, row_data)
            self.treeview.update_menus()
            self.update_launcher_category_dirs()

        except (OSError, GLib.Error, KeyError, AttributeError, TypeError) as e:
            logger.error(str(e))
            self._unblock_history()
            return False

        self._unblock_history()
        return True

    def filter_and_convert_categories(self, categories_list):
        """Detect non-XDG compliant category strings, convert them into hash IDs,
        and automatically generate corresponding stealth .directory mapping files."""
        cleaned_categories = []
        os.makedirs(self.user_dirs_dir, exist_ok=True)
        for cat in categories_list:
            cat_striped = cat.strip()
            if not cat_striped:
                continue

            # Pass through pseudo-categories and already hashed keys.
            if cat_striped in ["Other", "OLD", "Old"] or cat_striped.startswith(
                "menuet-"
            ):
                cleaned_categories.append(cat_striped)
                continue

            # XDG Specification Check: allow only alphanumeric characters, hyphens, and underscores.
            is_pure_xdg = all(
                char.isalnum() or char in ["-", "_"] for char in cat_striped
            )
            if is_pure_xdg:
                cleaned_categories.append(cat_striped)
            else:
                hasher = hashlib.md5(cat_striped.encode("utf-8"))
                hash_str = hasher.hexdigest()[:8]
                hash_category_id = f"menuet-{hash_str}"
                cleaned_categories.append(hash_category_id)

                directory_filepath = os.path.join(
                    self.user_dirs_dir, f"{hash_category_id}.directory"
                )
                try:
                    if not os.path.exists(directory_filepath):
                        directory_content = (
                            "[Desktop Entry]\n"
                            "Type=Directory\n"
                            f"Name={cat_striped}\n"
                            "Icon=folder\n"
                        )
                        with open(directory_filepath, "w", encoding="utf-8") as f_dir:
                            f_dir.write(directory_content)
                except (OSError, UnicodeError) as e:
                    logger.error(f"Failed to generate directory file: {e}")
        return cleaned_categories

    def move_node_pseudo(self, filename, target_category_id):
        """Safely retrieve the native data store and perform node relocation
        without breaking active selection states."""
        if not hasattr(self, "treeview") or not self.treeview:
            return

        model = None
        try:
            if hasattr(self.treeview, "get_model"):
                model = self.treeview.get_model()
            if model is None and hasattr(self.treeview, "model"):
                model = self.treeview.model
        except (RuntimeError, AttributeError, TypeError) as e:
            logger.error(f"Failed to fetch active store model: {e}")

        if model is None:
            logger.error(
                "Unable to resolve native GTK model container from treeview layout."
            )
            return

        source_iter = None
        target_parent_iter = None
        row_data_copy = None

        # Flatten tree branch to avoid recursive loop vulnerabilities during iteration.
        def _get_all_iters(store, parent_iter=None):
            iters = []
            current_iter = store.iter_children(parent_iter)
            while current_iter is not None:
                iters.append(store.iter_copy(current_iter))
                if store.iter_has_child(current_iter):
                    iters.extend(_get_all_iters(store, current_iter))
                current_iter = store.iter_next(current_iter)
            return iters

        all_nodes = []
        first_iter = model.get_iter_first()
        while first_iter is not None:
            all_nodes.append(model.iter_copy(first_iter))
            if model.iter_has_child(first_iter):
                all_nodes.extend(_get_all_iters(model, first_iter))
            first_iter = model.iter_next(first_iter)

        for treeiter in all_nodes:
            current_fn = model.get_value(treeiter, 8)  # COL_FILENAME
            current_id = model.get_value(treeiter, 1)  # COL_DISPLAY_NAME / entry_id
            if current_fn and os.path.basename(current_fn) == filename:
                source_iter = model.iter_copy(treeiter)
                row_data_copy = [
                    model.get_value(treeiter, i) for i in range(model.get_n_columns())
                ]
            if current_id == target_category_id:
                target_parent_iter = model.iter_copy(treeiter)

        if source_iter and row_data_copy:
            if target_category_id == "unregistered_apps":
                row_data_copy[7] = "document-open-recent-symbolic"  # COL_ICON_NAME
                row_data_copy[6] = Gio.ThemedIcon.new(
                    "document-open-recent-symbolic"
                )  # COL_G_ICON
            else:
                real_icon = self.get_value("Icon") or "application-x-executable"
                row_data_copy[7] = real_icon
                row_data_copy[6] = Gio.ThemedIcon.new(real_icon)

            model.append(target_parent_iter, row_data_copy)
            model.remove(source_iter)
            if hasattr(self.treeview, "show_all"):
                self.treeview.show_all()

    def register_cmenu(self, widget=None):
        """Process categories into XDG-compliant hashes, handle validation,
        and promote nodes to production GMenu branches."""

        if hasattr(self, "editor"):
            self.editor.commit()

        production_filename = self.get_value("Filename")
        if not production_filename or not os.path.exists(production_filename):
            if not self.save_launcher():
                logger.error("Pre-save pipeline failed. Aborting CMenu registry.")
                return False
            production_filename = self.get_value("Filename")

        raw_categories_str = self.get_value("Categories") or ""
        raw_categories_list = [
            c.strip() for c in raw_categories_str.split(";") if c.strip()
        ]
        cleaned_categories = self.filter_and_convert_categories(raw_categories_list)

        safe_categories_str = ";".join(cleaned_categories) + ";"
        self.set_value(
            "Categories", safe_categories_str, adjust_widget=True, store=False
        )

        self.set_value("OnlyShowIn", None)
        self.is_registered_status = True

        if not self.write_launcher(production_filename):
            logger.error("Failed to write standardized data to launcher.")
            return False

        target_basename = os.path.basename(production_filename)

        if self._validate_desktop:
            self.write_launcher(production_filename)

            dialog = Dialogs.ValidationErrorDialog(self, self.use_headerbar)
            dialog.run()
            dialog.destroy()

            self.move_node_pseudo(target_basename, "unregistered_apps")
            return True
        else:
            is_currently_in_temp = False
            model, row_data = self.treeview.get_selected_row_data()
            if (
                row_data
                and row_data[MenuEditor.COL_ICON_NAME]
                == "document-open-recent-symbolic"
            ):
                is_currently_in_temp = True

            if is_currently_in_temp:
                item_type = self.get_value("Type")
                dialog = Dialogs.ConfirmPromotionDialog(
                    self, item_type, self.use_headerbar
                )
                response = dialog.run()
                dialog.destroy()
                if response != Gtk.ResponseType.YES:
                    return False

            primary_cat = cleaned_categories[0] if cleaned_categories else ""

            self.move_node_pseudo(target_basename, primary_cat)
            self._run_update_desktop_database(os.path.dirname(production_filename))
            self.execute_cinnamon_refresh()

            return True

    def unregister_cmenu(self, widget=None):
        """Safely hide the active launcher by injecting the 'OnlyShowIn=Old;' barrier
        and demoting the node back to the temporary buffer."""

        production_filename = self.get_value("Filename")
        if not production_filename or not os.path.exists(production_filename):
            logger.error("Target production desktop file not found.")
            return False

        self.is_registered_status = False

        self.set_value("OnlyShowIn", "Old;", adjust_widget=True, store=False)
        self.values["OnlyShowIn"] = "Old;"

        TEMP_CLOCK_ICON = "document-open-recent-symbolic"
        self.set_value("Icon", TEMP_CLOCK_ICON, adjust_widget=True, store=False)

        if not self.write_launcher(production_filename):
            logger.error("Failed to inject isolation attributes into the file.")
            return False

        target_basename = os.path.basename(production_filename)
        self.move_node_pseudo(target_basename, "unregistered_apps")
        self._run_update_desktop_database(os.path.dirname(production_filename))
        self.execute_cinnamon_refresh()

        return True

    def execute_cinnamon_refresh(self):
        """Restart the Cinnamon shell or run post-registry sync."""

        if hasattr(self, "execute_post_registry_sync"):
            self.execute_post_registry_sync()
            return

        cinnamon_bin = shutil.which("cinnamon")
        if cinnamon_bin is None:
            logger.warning(
                "execute_cinnamon_refresh: 'cinnamon' binary not found in PATH"
            )
            return
        subprocess.Popen(
            [cinnamon_bin, "--replace"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    def restart_cinnamon_shell(self, widget=None):
        """Restart the Cinnamon Menu Shell to apply menu changes."""

        title = _("Refresh Cinnamon Menu")
        primary = _(
            "Do you want to restart the Cinnamon Menu Shell to apply the changes?"
        )
        secondary = _(
            "This will restart the Cinnamon Menu Shell using 'cinnamon --replace' and apply the current menu changes. "
            "The screen may briefly flicker during the restart."
        )
        dialog = Gtk.MessageDialog(
            transient_for=self,
            modal=True,
            message_type=Gtk.MessageType.WARNING,
            buttons=Gtk.ButtonsType.YES_NO,
            text=primary,
        )
        dialog.set_title(title)
        dialog.format_secondary_markup(secondary)
        response = dialog.run()
        dialog.destroy()

        if response == Gtk.ResponseType.YES:
            # Update desktop database.
            apps_dir = getattr(self, "user_apps_dir", "")
            self._run_update_desktop_database(apps_dir)

            # Restart the Cinnamon Menu Shell to apply menu changes.
            self.execute_cinnamon_refresh()

            return True

        return False

    def reload_treeview(self):
        """Bust global caches and hot-swap the native data model cleanly."""
        try:
            Gio.AppInfo.reset_type_associations("application/x-desktop")
        except GLib.Error as e:
            logger.warning(f"Failed to reset type associations: {e}")
            Gio.AppInfo.get_all()
        try:
            if (
                hasattr(self, "treeview")
                and self.treeview is not None
                and hasattr(self.treeview, "view")
            ):
                new_treestore = MenuEditor.get_treestore()
                if new_treestore is not None:
                    self.treeview.view.set_model(new_treestore)
                    for attr in ("treestore", "model"):
                        if hasattr(self.treeview, attr):
                            setattr(self.treeview, attr, new_treestore)
                            break

                self.treeview.show_all()
                if hasattr(self.treeview, "reset_cursor"):
                    self.treeview.reset_cursor()
                self.on_apps_browser_cursor_changed(None, None)
        except (GLib.Error, RuntimeError, AttributeError, TypeError) as e:
            logger.error(e)

    def update_launcher_categories(self, remove, add):
        """Synchronize launcher required categories dynamically."""
        original_filename = self.get_value("Filename")
        if original_filename is None or not os.path.isfile(original_filename):
            return
        item_type = self.get_value("Type")
        name = self.get_value("Name")

        save_filename = util.getSaveFilename(
            name, original_filename, item_type, force_update=True
        )
        logger.debug(f'Saving launcher as "{save_filename}"')

        keyfile = GLib.KeyFile.new()
        keyfile.load_from_file(original_filename, GLib.KeyFileFlags.NONE)
        try:
            categories = keyfile.get_string_list("Desktop Entry", "Categories")
        except GLib.Error:
            categories = None

        if categories is None:
            categories = []

        for category in remove:
            if category in categories:
                categories.remove(category)

        for category in add:
            if category not in categories:
                categories.append(category)

        categories = [cat for cat in categories if cat.strip() != ""]
        categories.sort()
        categories = self.filter_and_convert_categories(categories)

        keyfile.set_string_list("Desktop Entry", "Categories", categories)
        self.write_desktop_file_custom(save_filename, keyfile)
        self.set_value("Filename", save_filename)

        model, row_data = self.treeview.get_selected_row_data()
        if row_data is None:
            return
        row_data[MenuEditor.COL_CATEGORIES] = ";".join(categories)
        row_data[MenuEditor.COL_FILENAME] = save_filename
        self.treeview.update_launcher_instances(original_filename, row_data)

    def update_launcher_category_dirs(self):
        """Ensure launcher is present or absent in all top-level directories
        dictated by its categories."""
        model, row_data = self.treeview.get_selected_row_data()
        if row_data is None:
            return

        if row_data[MenuEditor.COL_CATEGORIES]:
            categories = row_data[MenuEditor.COL_CATEGORIES].split(";")[:-1]
        else:
            categories = []
        filename = row_data[MenuEditor.COL_FILENAME]

        required_category_directories = set()
        launcher_instances = self.treeview._get_launcher_instances(filename)
        launchers_in_top_level_dirs = {}

        for instance in launcher_instances:
            _, parent = self.treeview.get_parent(model, instance)
            if (
                parent is not None
                and model[parent][MenuEditor.COL_TYPE] == MenuItemTypes.DIRECTORY
            ):
                required_category_directories.add(model[parent][MenuEditor.COL_NAME])

                _, parent_parent = self.treeview.get_parent(model, parent)
                if parent_parent is None:
                    launchers_in_top_level_dirs[model[parent][MenuEditor.COL_NAME]] = (
                        instance
                    )

        top_level_dirs = {}
        for row in model:
            if row[MenuEditor.COL_TYPE] == MenuItemTypes.DIRECTORY:
                top_level_dirs[row[MenuEditor.COL_NAME]] = model.get_iter(row.path)

        for category in categories:
            if category not in category_lookup.keys():
                continue

            category_group = category_lookup[category]
            directory_name = util.getDirectoryNameFromCategory(category_group)

            if (
                directory_name in top_level_dirs
                and directory_name not in launchers_in_top_level_dirs
            ):
                treeiter = self.treeview.add_child(
                    row_data, top_level_dirs[directory_name], model, False
                )
                launchers_in_top_level_dirs[directory_name] = treeiter

            if directory_name not in required_category_directories:
                required_category_directories.add(directory_name)

        superfluous_dirs = (
            set(launchers_in_top_level_dirs.keys()) - required_category_directories
        )
        _, parent_data = self.treeview.get_parent_row_data()

        for directory_name in superfluous_dirs:
            if (
                parent_data is not None
                and directory_name == parent_data[MenuEditor.COL_NAME]
            ):
                self.treeview.remove_selected(True)
            else:
                self.treeview.remove_iter(
                    model, launchers_in_top_level_dirs[directory_name]
                )

    def delete_separator(self):
        """Remove a separator row from the treeview, update the menu files."""
        self.treeview.remove_selected()

    def delete_launcher(self):
        """Delete the selected launcher."""
        self.treeview.remove_selected()
        self.history.clear()

    def restore_launcher(self):
        """Revert the current launcher."""
        values = self.history.restore()

        # Clear the history
        self.history.clear()

        # Block updates
        self.history.block()

        for key in list(values.keys()):
            self.set_value(key, values[key], store=True)

        # Unblock updates
        self.history.unblock()

    # Callbacks
    def on_add_launcher_cb(self, widget):
        """Add Launcher callback function."""
        self.add_launcher()

    def on_add_directory_cb(self, widget):
        """Add Directory callback function."""
        self.add_directory()

    def on_add_separator_cb(self, widget):
        """Add Separator callback function."""
        self.add_separator()

    def on_save_launcher_cb(self, widget):
        """Save Launcher callback function."""
        # When save button is pressed, maintain isolation barrier for new items in original flow
        if hasattr(self, "editor"):
            self.editor.commit()
        self.save_launcher()

    def on_undo_cb(self, widget):
        """Undo callback function."""
        key, value = self.history.undo()
        self.history.block()
        self.set_value(key, value)
        self.history.unblock()

    def on_redo_cb(self, widget):
        """Redo callback function."""
        key, value = self.history.redo()
        self.history.block()
        self.set_value(key, value)
        self.history.unblock()

    def on_revert_cb(self, widget):
        """Revert callback function."""
        dialog = Dialogs.RevertDialog(self, self.use_headerbar)
        if dialog.run() == Gtk.ResponseType.OK:
            self.restore_launcher()
        dialog.destroy()

    def on_reload_treeview_cb(self, widget):
        """Reload the treeview and refresh the application cache database."""
        self.reload_treeview()

    def on_register_cmenu_cb(self, widget):
        """Register and install memory-buffered launchers into the desktop menu."""
        self.register_cmenu()

    def on_unregister_cmenu_cb(self, widget):
        """Unregister and hide launchers from the desktop menu via only-show-in flags."""
        self.unregister_cmenu()

    def on_restart_cinnamon_shell_cb(self, widget):
        """Force apply all Cmenu changes and completely reset the desktop environment."""
        self.restart_cinnamon_shell()

    def on_delete_cb(self, widget):
        """Delete callback function."""
        model, row_data = self.treeview.get_selected_row_data()
        if row_data is None:
            return

        name = row_data[MenuEditor.COL_NAME]
        item_type = row_data[MenuEditor.COL_TYPE]

        # Prepare the strings
        if item_type == MenuItemTypes.SEPARATOR:
            # Translators: Confirmation dialog to delete the selected
            # separator.
            question = _("Are you sure you want to delete this separator?")
            delete_func = self.delete_separator
        else:
            # Translators: Confirmation dialog to delete the selected launcher.
            question = _('Are you sure you want to delete "%s"?') % name
            delete_func = self.delete_launcher

        dialog = Dialogs.DeleteDialog(self, question, self.use_headerbar)

        # Run
        if dialog.run() == Gtk.ResponseType.OK:
            delete_func()

        dialog.destroy()

    def on_quit_cb(self, widget):
        """Quit callback function.  Send the quit signal to the parent
        GtkApplication instance."""
        self.emit("quit", True)

    def on_about_cb(self, widget):
        """About callback function.  Send the about signal to the parent
        GtkApplication instance."""
        self.emit("about", True)


class Application(Gtk.Application):
    """Menuet GtkApplication"""

    def __init__(self):
        """Initialize the GtkApplication."""
        super().__init__()
        self.use_headerbar = False
        self.use_toolbar = False
        self.settings_file = os.path.expanduser("~/.config/menuet.cfg")

    def set_use_headerbar(self, preference):
        try:
            settings = GLib.KeyFile.new()
            settings.set_boolean("menuet", "UseHeaderbar", preference)
            self.write_desktop_file_custom(self.settings_file, settings)
        except (GLib.Error, OSError) as e:
            logger.error(f"Failed to set use_headerbar preference: {e}")

    def get_use_headerbar(self):
        if not os.path.exists(self.settings_file):
            return None
        try:
            settings = GLib.KeyFile.new()
            settings.load_from_file(self.settings_file, GLib.KeyFileFlags.NONE)
            return settings.get_boolean("menuet", "UseHeaderbar")
        except (GLib.Error, OSError) as e:
            logger.debug(f"Failed to load use_headerbar preference: {e}")
            return None

    def do_activate(self):
        """Handle GtkApplication do_activate."""
        if self.use_toolbar:
            headerbar = False
            self.set_use_headerbar(False)
        elif self.use_headerbar:
            headerbar = True
            self.set_use_headerbar(True)
        elif self.get_use_headerbar() is not None:
            headerbar = self.get_use_headerbar()
        elif current_desktop in ["budgie", "gnome", "pantheon"]:
            headerbar = True
        else:
            headerbar = False

        self.win = MenuetWindow(self, headerbar)
        self.win.show()

        self.win.connect("about", self.about_cb)
        self.win.connect("quit", self.quit_cb)

    def do_startup(self):
        """Handle GtkApplication do_startup."""
        Gtk.Application.do_startup(self)

        self.menu = Gio.Menu()
        section_1_menu = Gio.Menu()
        section_1_menu.append(_("About"), "app.about")
        section_1_menu.append(_("Quit"), "app.quit")
        self.menu.append_section(None, section_1_menu)

        self.set_app_menu(self.menu)

        actions = [
            ("about", self.about_cb),
            ("quit", self.quit_cb),
            ("add_launcher", lambda w, d: self.action_cb(w, d, "add_launcher")),
            ("add_directory", lambda w, d: self.action_cb(w, d, "add_directory")),
            ("add_separator", lambda w, d: self.action_cb(w, d, "add_separator")),
        ]
        for name, callback in actions:
            action = Gio.SimpleAction.new(name, None)
            action.connect("activate", callback)
            self.add_action(action)

    def about_cb(self, widget, data=None):
        dialog = Dialogs.AboutDialog(self.win, self.win.use_headerbar)
        dialog.show()

    def quit_cb(self, widget, data=None):
        self.quit()

    def action_cb(self, widget, data=None, action_name=None):
        self.win.activate_action_cb(None, action_name)
