#!/usr/bin/python3
# SPDX-License-Identifier: GPL-3.0-only
#   Menu Editor & Launcher Recovery for Linux Mint Cinnamon
#   Copyright (C) 2012-2024 Sean Davis <sean@bluesabre.org>
#   Copyright (C) 2016-2018 OmegaPhil <OmegaPhil@startmail.com>
#   Copyright (C) 2026 schnee-and-tetra <308144300+schnee-tetra@users.noreply.github.com>
import gettext
import logging
import os

_ = gettext.gettext

from gi.repository import Gio, GObject, Gtk, Pango

from . import MenuEditor, util
from .util import (
    MenuItemTypes,
    check_keypress,
    escapeText,
    getBasename,
    getRelativeName,
)

logger = logging.getLogger("menuet")


class Treeview(Gtk.Box):
    __gsignals__ = {
        "cursor-changed": (
            GObject.SIGNAL_RUN_LAST,
            GObject.TYPE_BOOLEAN,
            (GObject.TYPE_BOOLEAN,),
        ),
        "add-directory-enabled": (
            GObject.SIGNAL_RUN_LAST,
            GObject.TYPE_BOOLEAN,
            (GObject.TYPE_BOOLEAN,),
        ),
        "requires-menu-reload": (
            GObject.SIGNAL_RUN_LAST,
            GObject.TYPE_BOOLEAN,
            (GObject.TYPE_BOOLEAN,),
        ),
    }

    loaded = False

    def __init__(self, parent):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.parent = parent
        self._last_selected_path = -1
        self._search_terms = None
        self._lock_menus = False

        self.set_size_request(220, -1)

        scrolled = Gtk.ScrolledWindow.new(hadjustment=None, vadjustment=None)
        scrolled.set_shadow_type(Gtk.ShadowType.IN)
        scrolled.set_name("MenuetSidebarScroll")
        self.pack_start(scrolled, True, True, 0)

        treestore = MenuEditor.get_treestore()
        if treestore is not None:
            self.loaded = True
            self._treeview = Gtk.TreeView.new_with_model(treestore)
        else:
            self._treeview = Gtk.TreeView.new()

        self._treeview.set_show_expanders(True)
        self._treeview.set_enable_search(False)
        self._treeview.set_headers_visible(False)
        scrolled.add(self._treeview)

        # Translators: "Search Results" treeview column header
        col = Gtk.TreeViewColumn(_("Search Results"))

        # Icon renderer
        col_cell_img = Gtk.CellRendererPixbuf()
        col_cell_img.set_property("stock-size", Gtk.IconSize.LARGE_TOOLBAR)
        col.pack_start(col_cell_img, False)

        # Text renderer
        col_cell_text = Gtk.CellRendererText()
        col_cell_text.set_property("ellipsize", Pango.EllipsizeMode.END)
        col.pack_start(col_cell_text, True)

        # Set the markup property on the Text cell.
        col.add_attribute(col_cell_text, "markup", MenuEditor.COL_DISPLAY_NAME)

        # Add the cell data func for the text column to render labels.
        col.set_cell_data_func(col_cell_text, self._text_display_func, None)

        # Set the Tooltip column.
        self._treeview.set_tooltip_column(1)

        # Add the cell data func for the pixbuf column to render icons.
        col.set_cell_data_func(col_cell_img, self._icon_name_func, None)

        # Append the column, set the model.
        self._treeview.append_column(col)

        # Configure the treeview events.
        self._treeview.connect("cursor-changed", self._on_treeview_cursor_changed, None)
        self._treeview.connect(
            "key-press-event", self._on_treeview_key_press_event, None
        )
        self._treeview.connect("row-expanded", self._on_treeview_row_expansion, True)
        self._treeview.connect("row-collapsed", self._on_treeview_row_expansion, False)

        self.menu_timeout_id = 0

        self._toolbar = Gtk.Toolbar.new()
        self._toolbar.set_icon_size(Gtk.IconSize.MENU)
        self._toolbar.set_name("MenuetSidebarToolbar")
        self.add(self._toolbar)

        context = self._toolbar.get_style_context()
        context.add_class("inline-toolbar")

        img = Gtk.Image.new_from_icon_name("go-up-symbolic", Gtk.IconSize.MENU)
        self._move_up_button = Gtk.ToolButton.new(img, _("Move Up"))
        self._move_up_button.set_tooltip_text(_("Move Up"))
        self._move_up_button.connect("clicked", self._move_iter, (self._treeview, -1))
        self._toolbar.add(self._move_up_button)

        img = Gtk.Image.new_from_icon_name("go-down-symbolic", Gtk.IconSize.MENU)
        self._move_down_button = Gtk.ToolButton.new(img, _("Move Down"))
        self._move_down_button.set_tooltip_text(_("Move Down"))
        self._move_down_button.connect("clicked", self._move_iter, (self._treeview, 1))
        self._toolbar.add(self._move_down_button)

        img = Gtk.Image.new_from_icon_name(
            "view-sort-ascending-symbolic", Gtk.IconSize.MENU
        )
        self._sort_button = Gtk.ToolButton.new(img, _("Sort Alphabetically"))
        self._sort_button.set_tooltip_text(_("Sort Alphabetically"))
        self._sort_button.connect("clicked", self._sort_iter)
        self._toolbar.add(self._sort_button)

        # Show the treeview, grab focus.
        self.show_all()
        self._treeview.grab_focus()

    def set_sortable(self, sortable):
        self._sort_button.set_sensitive(sortable)

    def set_move_up_enabled(self, enabled):
        self._move_up_button.set_sensitive(enabled)

    def set_move_down_enabled(self, enabled):
        self._move_down_button.set_sensitive(enabled)

    # TreeView Modifiers
    def append(self, row_data):
        """Add a new launcher entry below the current selected one."""
        model, treeiter = self._get_selected_iter()
        model, parent = self.get_parent()

        new_iter = model.insert_after(parent, treeiter)
        self._populate_and_select_iter(model, new_iter, row_data)

        return new_iter

    def prepend(self, row_data):
        """Add a new launcher entry above the current selected one."""
        model, treeiter = self._get_selected_iter()
        parent = self.get_parent()

        new_iter = model.insert_before(parent, treeiter)
        self._populate_and_select_iter(model, new_iter, row_data)

        return new_iter

    def add_child(self, row_data, treeiter=None, model=None, do_select=True):
        """Add a new child launcher to the current selected one, or the specified iter."""
        if treeiter is None or model is None:
            model, treeiter = self._get_selected_iter()

        if treeiter is None:
            return None

        new_iter = model.prepend(treeiter)

        if do_select:
            self._treeview.expand_row(model[treeiter].path, False)

        self._populate_and_select_iter(model, new_iter, row_data, do_select)

        return new_iter

    def remove_selected(self, ui_only=False):
        """Remove the selected launcher, optionally keeping the physical file if ui_only is True."""
        self._last_selected_path = -1
        model, treeiter = self._get_selected_iter()

        item_id = model.get_value(treeiter, 0)  # COL_NAME
        if item_id == "Unregistered Apps":
            return

        filename = None
        del_files = []

        if not ui_only:
            if treeiter is not None:
                filename = model[treeiter][MenuEditor.COL_FILENAME]

            del_dirs, del_apps = self._get_delete_filenames(model, treeiter)
            del_files = del_dirs + del_apps

            self.xdg_menu_uninstall(model, treeiter, filename)

            for del_file in del_files:
                try:
                    os.remove(del_file)
                except (OSError, UnicodeError):
                    pass

        self.xdg_menu_update()
        self._cleanup_applications_merged()

        if not ui_only and (filename is None or filename not in del_files):
            model, parent_data = self.get_parent_row_data()
            if parent_data is not None:
                categories = util.getRequiredCategories(
                    parent_data[MenuEditor.COL_FILENAME]
                )
            else:
                categories = util.getRequiredCategories(None)
            self.parent.update_launcher_categories(categories, [])

        if treeiter is not None:
            path = model.get_path(treeiter)
            if (
                model is not None
                and treeiter is not None
                and not isinstance(model, Gtk.TreeModelFilter)
            ):
                model.remove(treeiter)
            if path:
                self._treeview.set_cursor(path)

        self.update_menus()

    def remove_iter(self, model, treeiter):
        """Remove launcher pointed to by iter from the model only."""
        model.remove(treeiter)

    # Get
    def get_parent(self, model=None, treeiter=None):
        """Get the parent iterator for the current treeiter."""
        parent = None
        if model is None:
            model, treeiter = self._get_selected_iter()
        if treeiter is not None:
            path = model.get_path(treeiter)
            if path.up() and path.get_depth() > 0:
                try:
                    parent = model.get_iter(path)
                except:  # noqa
                    parent = None
        return model, parent

    def is_first(self, model=None, treeiter=None):
        """Return True if the current iter is the first child."""
        if model is None:
            model, treeiter = self._get_selected_iter()
        if treeiter:
            path = model.get_path(treeiter)
            if path.prev():
                return False
        return True

    def _next(self, model, treeiter, path):
        """Advance path to the next sibling."""
        try:
            string = path.to_string()
            parts = string.split(":")
            parts[-1] = str(int(parts[-1]) + 1)
            string = ":".join(parts)
            path = Gtk.TreePath.new_from_string(string)
            model.get_iter(path)
        except (TypeError, ValueError):
            return None
        return path

    def is_last(self, model=None, treeiter=None):
        """Return True if the current iter is the last child."""
        if model is None:
            model, treeiter = self._get_selected_iter()
        if treeiter:
            path = model.get_path(treeiter)
            if self._next(model, treeiter, path) is not None:
                return False
        return True

    def get_parent_filename(self):
        """Get the filename of the parent iter."""
        model, parent = self.get_parent()
        if parent is None:
            return None
        return model[parent][MenuEditor.COL_FILENAME]

    def get_parent_row_data(self):
        """Get the row data of the parent iter."""
        model, parent = self.get_parent()
        if parent is None:
            return model, None
        parent_data: list = model[parent][:]
        return model, parent_data

    def get_selected_filename(self):
        """Return the filename of the current selected treeiter."""
        model, row_data = self.get_selected_row_data()
        if row_data is not None:
            return row_data[MenuEditor.COL_FILENAME]
        return None

    def get_selected_row_data(self):
        """Get the row data of the current selected item."""
        model, treeiter = self._get_selected_iter()
        if model is None or treeiter is None:
            return model, None
        row_data: list = model[treeiter][:]
        return model, row_data

    # Set
    def set_can_select_function(self, can_select_func):
        """Set the external function used for can-select."""
        selection = self._treeview.get_selection()
        selection.set_select_function(self._on_treeview_selection, can_select_func)

    # Update
    def update_launcher_instances(self, filename, row_data):
        """Update all same launchers with the new information."""
        model, treeiter = self._get_selected_iter()
        for instance in self._get_launcher_instances(filename, model):
            for i in range(len(row_data)):
                model[instance][i] = row_data[i]

    def update_selected(
        self,
        name,
        comment,
        executable,
        categories,
        item_type,
        icon_name,
        filename,
        show=True,
    ):
        """Update the application treeview selected row data."""
        model, treeiter = self._get_selected_iter()
        if treeiter is None:
            return

        item_id = model.get_value(treeiter, 0)  # COL_NAME
        if item_id == "Unregistered Apps":
            return

        model[treeiter][MenuEditor.COL_NAME] = name
        model[treeiter][MenuEditor.COL_DISPLAY_NAME] = escapeText(name)
        model[treeiter][MenuEditor.COL_COMMENT] = comment
        model[treeiter][MenuEditor.COL_EXEC] = executable
        model[treeiter][MenuEditor.COL_CATEGORIES] = categories
        model[treeiter][MenuEditor.COL_TYPE] = item_type

        if os.path.isfile(icon_name):
            gfile = Gio.File.parse_name(icon_name)
            icon = Gio.FileIcon.new(gfile)
        else:
            icon = Gio.ThemedIcon.new(icon_name)

        model[treeiter][MenuEditor.COL_G_ICON] = icon
        model[treeiter][MenuEditor.COL_ICON_NAME] = icon_name
        model[treeiter][MenuEditor.COL_FILENAME] = filename
        model[treeiter][MenuEditor.COL_SHOW] = show

        self._last_selected_path = -1
        self._on_treeview_cursor_changed(self._treeview, None)

    # Events
    def _on_treeview_cursor_changed(self, widget, selection):
        """Update the editor frame when the selected row is changed."""
        sel = widget.get_selection()
        if sel:
            treestore, treeiter = sel.get_selected()
            if not treestore or not treeiter:
                return

            path = str(treestore.get_path(treeiter))
            if path == self._last_selected_path:
                return
            self._last_selected_path = path

            self.emit("cursor-changed", True)
            self._update_add_directory()

    def _on_treeview_key_press_event(self, widget, event, user_data=None):
        """Handle treeview keypress events."""
        if check_keypress(event, ["right"]):
            self._set_treeview_selected_expanded(widget, True)
            return True
        elif check_keypress(event, ["left"]):
            self._set_treeview_selected_expanded(widget, False)
            return True
        elif check_keypress(event, ["space"]):
            self._toggle_treeview_selected_expanded(widget)
            return True
        return False

    def _on_treeview_row_expansion(self, treeview, treeiter, column, expanded):
        """Handle row expansion changes."""
        if self._toolbar.get_sensitive():
            model = treeview.get_model()
            row = model[treeiter]
            row[MenuEditor.COL_EXPAND] = expanded

    def _on_treeview_selection(self, sel, store, path, is_selected, can_select_func):
        """Save changes on cursor change."""
        if is_selected:
            return can_select_func()
        return True

    # Helper functions
    def _set_treeview_selected_expanded(self, treeview, expanded=True):
        """Set the expansion of the selected row."""
        sel = treeview.get_selection()
        model, treeiter = sel.get_selected()
        row = model[treeiter]
        if expanded:
            treeview.expand_row(row.path, False)
        else:
            treeview.collapse_row(row.path)

    def _toggle_treeview_selected_expanded(self, treeview):
        """Toggle the expansion of the selected row."""
        expanded = self._get_treeview_selected_expanded(treeview)
        self._set_treeview_selected_expanded(treeview, not expanded)

    def _text_display_func(self, col, renderer, treestore, treeiter, user_data):
        """CellRenderer function to set text style for each row."""
        show = treestore[treeiter][MenuEditor.COL_SHOW]
        if show:
            renderer.set_property("style", Pango.Style.NORMAL)
        else:
            renderer.set_property("style", Pango.Style.ITALIC)
        separator = treestore[treeiter][MenuEditor.COL_TYPE] == MenuItemTypes.SEPARATOR
        renderer.set_property("sensitive", not separator)
        renderer.set_property("style-set", True)

    def _icon_name_func(self, col, renderer, treestore, treeiter, user_data):
        """CellRenderer function to set gicon for each row."""
        renderer.set_property("gicon", treestore[treeiter][MenuEditor.COL_G_ICON])
        separator = treestore[treeiter][MenuEditor.COL_TYPE] == MenuItemTypes.SEPARATOR
        renderer.set_property("sensitive", not separator)

    def _get_selected_iter(self):
        """Return the current treeview model and selected iter."""
        model, treeiter = self._treeview.get_selection().get_selected()
        return model, treeiter

    def _populate_and_select_iter(self, model, treeiter, row_data, do_select=True):
        """Fill the specified treeiter with data and optionally select it."""
        for i in range(len(row_data)):
            model[treeiter][i] = row_data[i]

        if do_select:
            path = model.get_path(treeiter)
            self._treeview.set_cursor(path)

    def _get_deletable_launcher(self, filename):
        """Return True if the launcher is available for deletion."""
        return os.path.exists(filename)

    def _get_delete_filenames(self, model, treeiter):
        """Return a list of files to be deleted after uninstall."""
        directories = []
        applications = []

        filename = model[treeiter][MenuEditor.COL_FILENAME]
        block_run = False

        if filename is not None:
            basename = getRelativeName(filename)
            original = util.getSystemLauncherPath(basename)
            item_type = model[treeiter][MenuEditor.COL_TYPE]
            if original is None and item_type == MenuItemTypes.DIRECTORY:
                pass
            else:
                block_run = True

        if model.iter_has_child(treeiter) and not block_run:
            for i in range(model.iter_n_children(treeiter)):
                child_iter = model.iter_nth_child(treeiter, i)
                filename = model[child_iter][MenuEditor.COL_FILENAME]
                if filename is not None:
                    if filename.endswith(".directory"):
                        d, a = self._get_delete_filenames(model, child_iter)
                        directories = directories + d
                        applications = applications + a
                        directories.append(filename)
                    else:
                        if self._get_deletable_launcher(filename):
                            applications.append(filename)

        filename = model[treeiter][MenuEditor.COL_FILENAME]
        if filename is not None:
            if filename.endswith(".directory"):
                directories.append(filename)
            else:
                if self._get_deletable_launcher(filename):
                    applications.append(filename)
        return directories, applications

    def _get_treeview_selected_expanded(self, treeview):
        """Return True if the selected row is currently expanded."""
        sel = treeview.get_selection()
        model, treeiter = sel.get_selected()
        row = model[treeiter]
        return treeview.row_expanded(row.path)

    def _get_launcher_instances(self, filename, model=None, parent=None):
        """Return a list of all treeiters referencing this filename."""
        if filename is None:
            return []
        if model is None:
            model, treeiter = self._get_selected_iter()
        treeiters = []
        for n_child in range(model.iter_n_children(parent)):
            treeiter = model.iter_nth_child(parent, n_child)
            if treeiter is None:
                continue
            iter_filename = model[treeiter][MenuEditor.COL_FILENAME]
            if iter_filename == filename:
                treeiters.append(treeiter)
            if model.iter_has_child(treeiter):
                treeiters += self._get_launcher_instances(filename, model, treeiter)
        return treeiters

    def _get_n_launcher_instances(self, filename):
        """Return the count of all treeiters referencing this filename."""
        return len(self._get_launcher_instances(filename))

    def _is_menu_locked(self):
        """Return True if menu editing is currently locked."""
        return self._lock_menus

    def _update_add_directory(self):
        """Prevent adding subdirectories to system menus."""
        add_enabled = True
        prefix = util.getDefaultMenuPrefix()

        treestore, treeiter = self._get_selected_iter()
        model, parent_iter = self.get_parent()
        while parent_iter is not None:
            filename = treestore[parent_iter][MenuEditor.COL_FILENAME]
            if getBasename(filename).startswith(prefix):
                add_enabled = False
            model, parent_iter = self.get_parent(treestore, parent_iter)

        self.emit("add-directory-enabled", add_enabled)

    # Search
    def search(self, terms):
        """Search the treeview for the specified terms."""
        self._search_terms = str(terms.lower())
        model: Gtk.TreeModelFilter = self._treeview.get_model()
        model.refilter()

    def set_searchable(self, searchable, expand=False):
        """Set the TreeView searchable."""
        model = self._treeview.get_model()
        if model is None:
            return

        if searchable:
            self._lock_menus = True
            self._treeview.set_headers_visible(True)
            self._toolbar.set_sensitive(False)

            if expand:
                self._treeview.expand_all()

            if not isinstance(model, Gtk.TreeModelFilter):
                model = model.filter_new()
                self._treeview.set_model(model)
                model.set_visible_func(self._treeview_match_func)

        else:
            self._lock_menus = False
            self._treeview.set_headers_visible(False)
            self._toolbar.set_sensitive(True)

            if isinstance(model, Gtk.TreeModelFilter):
                f_model, f_iter = self._get_selected_iter()

                model = model.get_model()
                self._treeview.set_model(model)

                self._treeview.collapse_all()
                for n_child in range(model.iter_n_children(None)):
                    treeiter = model.iter_nth_child(None, n_child)
                    if treeiter is None:
                        continue
                    row = model[treeiter]
                    if row[MenuEditor.COL_FILENAME]:
                        self._treeview.expand_row(row.path, False)

                if (f_model is not None) and (f_iter is not None):
                    row_data = f_model[f_iter][:]
                    selected_iter = self._get_iter_by_data(row_data, model, parent=None)
                else:
                    selected_iter = model.get_iter_first()

                if selected_iter is not None:
                    path = model.get_path(selected_iter)
                    self._treeview.set_cursor(path)

    def _treeview_match(self, model, treeiter, query):
        """Match subfunction for filtering search results."""
        name = model[treeiter][MenuEditor.COL_NAME]
        comment = model[treeiter][MenuEditor.COL_COMMENT]
        executable = model[treeiter][MenuEditor.COL_EXEC]
        item_type = model[treeiter][MenuEditor.COL_TYPE]
        desktop = model[treeiter][MenuEditor.COL_FILENAME]

        if item_type == MenuItemTypes.SEPARATOR:
            return False

        if not name:
            name = ""
        if not comment:
            comment = ""
        if not executable:
            executable = ""

        self._treeview.expand_all()

        if query in name.lower():
            return True
        if query in comment.lower():
            return True
        if query in executable.lower():
            return True

        desktop = desktop.replace("menuet-", "")
        desktop = desktop.replace("alacarte-", "")
        if query in desktop.lower():
            return True

        if item_type == MenuItemTypes.DIRECTORY:
            return self._treeview_match_directory(query, model, treeiter)

        return False

    def _treeview_match_directory(self, query, model, treeiter):
        """Match subfunction for matching directory children."""
        for child_i in range(model.iter_n_children(treeiter)):
            child = model.iter_nth_child(treeiter, child_i)
            if self._treeview_match(model, child, query):
                return True
        return False

    def _treeview_match_func(self, model, treeiter, data=None):
        """Match function for filtering search results."""
        if self._search_terms == "":
            return True
        return self._treeview_match(model, treeiter, self._search_terms)

    # XDG Menu Commands
    def xdg_menu_install(self, filename, parent=None):
        """No-op: relies on Cinnamon's file-system monitoring."""
        logger.debug(f"xdg_menu_install: no-op for {filename}")

    def xdg_menu_uninstall(self, model, treeiter, filename):
        """No-op: relies on Cinnamon's file-system monitoring."""
        logger.debug(f"xdg_menu_uninstall: no-op for {filename}")

    def xdg_menu_update(self):
        """No-op: relies on Cinnamon's file-system monitoring."""
        logger.debug("xdg_menu_update: no-op")

    def update_menus(self):
        """No-op: relies on Cinnamon's file-system monitoring."""
        logger.debug("update_menus: no-op")

    def _cleanup_applications_merged(self):
        """No-op: relies on Cinnamon's file-system monitoring."""
        logger.debug("_cleanup_applications_merged: no-op")

    # TreeView iter tricks
    def _move_iter(self, widget, user_data):
        """Move the currently selected row up or down in the tree."""
        treeview, relative_position = user_data

        sel = treeview.get_selection().get_selected()
        if sel:
            model, selected_iter = sel
            item_id = model.get_value(selected_iter, 0)  # COL_NAME
            if item_id == "Unregistered Apps":
                return
            selected_type = model[selected_iter][MenuEditor.COL_TYPE]

            model, parent = self.get_parent(model, selected_iter)
            if parent:
                categories = util.getRequiredCategories(
                    model[parent][MenuEditor.COL_FILENAME]
                )
            else:
                categories = util.getRequiredCategories(None)

            if relative_position < 0:
                sibling_iter = model.iter_previous(selected_iter)
            else:
                sibling_iter = model.iter_next(selected_iter)

            if sibling_iter:
                sibling_path = model.get_path(sibling_iter)
                move_down = False
                sibling_type = model[sibling_iter][MenuEditor.COL_TYPE]

                if sibling_type == MenuItemTypes.DIRECTORY:
                    if selected_type == MenuItemTypes.DIRECTORY:
                        move_down = False
                    elif treeview.row_expanded(
                        sibling_path
                    ) or not model.iter_has_child(sibling_iter):
                        move_down = True

                if move_down:
                    selected_iter = self._move_iter_down_level(
                        treeview, selected_iter, sibling_iter, relative_position
                    )
                else:
                    if relative_position < 0:
                        model.move_before(selected_iter, sibling_iter)
                    else:
                        model.move_after(selected_iter, sibling_iter)
            else:
                selected_iter = self._move_iter_up_level(
                    treeview, selected_iter, relative_position
                )

            model, parent = self.get_parent(model, selected_iter)
            if parent:
                new_categories = util.getRequiredCategories(
                    model[parent][MenuEditor.COL_FILENAME]
                )
            else:
                new_categories = util.getRequiredCategories(None)

            if categories != new_categories:
                editor_categories = ""
                if hasattr(self.parent, "get_editor_categories"):
                    editor_categories = self.parent.get_editor_categories()
                elif hasattr(self.parent, "get_value"):
                    editor_categories = self.parent.get_value("Categories") or ""

                split_categories = [c for c in editor_categories.split(";") if c]
                for category in categories:
                    if category in split_categories:
                        split_categories.remove(category)
                for category in new_categories:
                    if category not in split_categories:
                        split_categories.append(category)
                split_categories.sort()
                editor_categories = (
                    ";".join(split_categories) + ";" if split_categories else ""
                )
                if hasattr(self.parent, "set_editor_categories"):
                    self.parent.set_editor_categories(editor_categories)
                elif hasattr(self.parent, "set_value"):
                    self.parent.set_value("Categories", editor_categories)
                self.parent.update_launcher_categories(categories, new_categories)

        self.update_menus()
        self.scroll_to_selection()
        self.emit("cursor-changed", True)

    def _get_iter_by_data(self, row_data, model: Gtk.TreeModel, parent=None):
        """Search the TreeModel for a row matching row_data."""
        for n_child in range(model.iter_n_children(parent)):
            treeiter = model.iter_nth_child(parent, n_child)
            if treeiter is None:
                continue
            if model[treeiter][:] == row_data:
                return treeiter
            if model.iter_n_children(treeiter) != 0:
                value = self._get_iter_by_data(row_data, model, treeiter)
                if value is not None:
                    return value
        return None

    def _move_iter_up_level(self, treeview, treeiter, relative_position):
        """Move the specified iter up one level."""
        model = treeview.get_model()
        sibling = model.iter_parent(treeiter)
        if sibling is not None:
            parent = model.iter_parent(sibling)
            row_data = model[treeiter][:]
            if relative_position < 0:
                new_iter = model.insert_before(parent, sibling, row_data)
            else:
                new_iter = model.insert_after(parent, sibling, row_data)

            filename = row_data[MenuEditor.COL_FILENAME]
            self.xdg_menu_install(filename)
            self.xdg_menu_uninstall(model, treeiter, filename)

            model.remove(treeiter)
            path = model.get_path(new_iter)
            treeview.set_cursor(path)
            return new_iter

    def _move_iter_down_level(self, treeview, treeiter, parent_iter, relative_position):
        """Move the specified iter down one level."""
        model = treeview.get_model()
        item_id = model.get_value(treeiter, 0)  # COL_NAME
        if item_id == "Unregistered Apps":
            return

        row_data = model[treeiter][:]
        if model.iter_has_child(parent_iter):
            if relative_position < 0:
                n_children = model.iter_n_children(parent_iter)
                sibling = model.iter_nth_child(parent_iter, n_children - 1)
                new_iter = model.insert_after(parent_iter, sibling, row_data)
            else:
                sibling = model.iter_nth_child(parent_iter, 0)
                new_iter = model.insert_before(parent_iter, sibling, row_data)
        else:
            new_iter = model.insert(parent_iter, 0, row_data)

        filename = row_data[MenuEditor.COL_FILENAME]
        self.xdg_menu_install(filename, parent_iter)
        self.xdg_menu_uninstall(model, treeiter, filename)

        model.remove(treeiter)
        treeview.expand_row(model[parent_iter].path, False)
        path = model.get_path(new_iter)
        treeview.set_cursor(path)
        return new_iter

    def _sort_iter(self, widget):
        """Alphabetically sort items in the current directory."""
        model, sel_iter = self._get_selected_iter()
        if sel_iter is not None:
            item_id = model.get_value(sel_iter, 0)  # COL_NAME
            if item_id == "Unregistered Apps":
                return

            item_names = []
            _, parent_iter = self.get_parent(model, sel_iter)
            if parent_iter:
                for i in range(model.iter_n_children(parent_iter)):
                    child_iter = model.iter_nth_child(parent_iter, i)
                    if child_iter is not None:
                        item_names.append(model[child_iter][MenuEditor.COL_NAME])

                item_names = sorted(item_names, key=str.lower)

                for i in range(len(item_names)):
                    child_iter = model.iter_nth_child(parent_iter, i)
                    if child_iter is None:
                        continue

                    if item_names[i] != model[child_iter][MenuEditor.COL_NAME]:
                        search_iter = None

                        for r in range(i, len(item_names)):
                            search_iter = model.iter_nth_child(parent_iter, r)
                            if search_iter is None:
                                continue
                            if item_names[i] == model[search_iter][MenuEditor.COL_NAME]:
                                break

                        if search_iter is not None:
                            model.move_before(search_iter, child_iter)

                self.update_menus()

            self.scroll_to_selection()

    def scroll_to_selection(self):
        """Scroll the treeview to the currently selected item."""
        model, sel_iter = self._get_selected_iter()
        if sel_iter is None:
            return
        self._treeview.scroll_to_cell(model.get_path(sel_iter), None, False, 0.0, 0.0)

    def set_search_entry(self, entry):
        """Set the search entry widget for the treeview."""
        self._treeview.set_search_entry(entry)

    def reset_cursor(self):
        """Reset the treeview cursor position."""
        self._treeview.set_cursor(Gtk.TreePath.new_from_string("1"))
        self._treeview.set_cursor(Gtk.TreePath.new_from_string("0"))
