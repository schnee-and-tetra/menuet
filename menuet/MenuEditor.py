#!/usr/bin/python3
# SPDX-License-Identifier: GPL-3.0-only
#   Menu Editor & Launcher Recovery for Linux Mint Cinnamon
#   Copyright (C) 2012-2024 Sean Davis <sean@bluesabre.org>
#   Copyright (C) 2016-2018 OmegaPhil <OmegaPhil@startmail.com>
#   Copyright (C) 2026 schnee-and-tetra <308144300+schnee-tetra@users.noreply.github.com>
import configparser
import gettext
import locale
import logging
import os
import xml.dom.minidom
import xml.parsers.expat

_ = gettext.gettext

logger = logging.getLogger("menuet")

import gi

gi.require_version("CMenu", "3.0")
from gi.repository import CMenu as GMenu
from gi.repository import Gio, Gtk

from . import util
from .util import (
    MenuItemTypes,
    escapeText,
    mapDesktopEnvironmentDirectories,
    unmapDesktopEnvironmentDirectories,
)

locale.textdomain("menuet")

icon_theme = Gtk.IconTheme.get_default()


class DummyAppInfo:
    """A wrapper mimicking the Gio.DesktopAppInfo interface using configparser."""

    def __init__(self, parser, filepath):
        self.parser = parser
        self.filepath = filepath

    def _get(self, key, fallback=""):
        if self.parser.has_section("Desktop Entry"):
            return self.parser.get("Desktop Entry", key, fallback=fallback)
        return fallback

    def get_display_name(self):
        return self._get("Name")

    def get_generic_name(self):
        return self._get("GenericName")

    def get_description(self):
        return self._get("Comment")

    def get_keywords(self):
        kw_str = self._get("Keywords")
        return [k.strip() for k in kw_str.split(";") if k.strip()]

    def get_categories(self):
        return self._get("Categories")

    def get_executable(self):
        return self._get("Exec")


class DummyTreeEntry:
    """A dummy entry providing TreeEntry-compatible methods for the menu pipeline."""

    def __init__(self, filename, filepath, app_info):
        self._filename = filename
        self._filepath = filepath
        self._app_info = app_info

    def get_desktop_file_id(self):
        return self._filename

    def get_desktop_file_path(self):
        return self._filepath

    def get_app_info(self):
        return self._app_info


# Complete CMenu.Tree pseudo-override via delegation wrapper
class MenuetTreeWrapper:
    """Wrapper for CMenu.Tree that restores visibility of entries excluded
    due to session rejection (OnlyShowIn=Old;) by injecting them during
    getContents() calls."""

    @classmethod
    def new(cls, menu_file, flags=0):
        # Create and wrap the real CMenu.Tree instance
        real_tree = GMenu.Tree.new(menu_file, flags)
        wrapper = cls()
        wrapper._real_tree = real_tree
        logger.debug(f"MenuetTreeWrapper: Initialized ({menu_file})")
        return wrapper

    def getContents(self, item):
        """Override getContents to include entries hidden by CMenu."""
        # Get the actual contents list loaded by CMenu
        contents = []
        if hasattr(self._real_tree, "get_root_directory"):
            item_iter = item.iter()
            item_type = item_iter.next()
            while item_type != GMenu.TreeItemType.INVALID:
                if item_type == GMenu.TreeItemType.DIRECTORY:
                    contents.append(item_iter.get_directory())
                elif item_type == GMenu.TreeItemType.ENTRY:
                    contents.append(item_iter.get_entry())
                elif item_type == GMenu.TreeItemType.SEPARATOR:
                    contents.append(item_iter.get_separator())
                item_type = item_iter.next()

        # Scan user applications directory for entries excluded by CMenu
        # (those with OnlyShowIn=Old;) and restore them to the tree
        user_apps_dir = os.path.expanduser("~/.local/share/applications")
        if os.path.exists(user_apps_dir):
            for filename in os.listdir(user_apps_dir):
                if filename.endswith(".desktop"):
                    filepath = os.path.join(user_apps_dir, filename)
                    try:
                        with open(filepath, "r", encoding="utf-8") as f:
                            file_content = f.read()

                        # Check if the file contains the isolation flag
                        if (
                            "OnlyShowIn=Old" in file_content
                            or "OnlyShowIn=OLD" in file_content
                        ):
                            # Check for duplicates in contents list
                            exists = False
                            for child in contents:
                                if hasattr(child, "get_desktop_file_path"):
                                    path = child.get_desktop_file_path()
                                    if path and os.path.basename(path) == filename:
                                        exists = True
                                        break

                            # If excluded by CMenu, forcibly restore it
                            if not exists:
                                # Load the file directly and create AppInfo object
                                app_info = Gio.DesktopAppInfo.new_from_filename(
                                    filepath
                                )

                                # Fallback to configparser and DummyAppInfo if Gio validation fails
                                if not app_info:
                                    parser = configparser.ConfigParser(
                                        interpolation=None
                                    )
                                    parser.optionxform = str
                                    try:
                                        parser.read(filepath, encoding="utf-8")
                                        app_info = DummyAppInfo(parser, filepath)
                                    except Exception as cp_ex:
                                        logger.debug(
                                            f"configparser fallback failed for {filename}: {cp_ex}"
                                        )

                                if app_info:
                                    contents.append(
                                        DummyTreeEntry(filename, filepath, app_info)
                                    )

                    except Exception as e:
                        logger.warning("Parse error (continuing): " + str(e))

        return contents

    def __getattr__(self, name):
        """Delegate all other attributes and methods to the real CMenu.Tree."""
        return getattr(self._real_tree, name)


def get_icon_theme_name_from_settings():
    try:
        settings = Gtk.Settings.get_default()
        if settings is None:
            return None
        theme_name = settings.get_property("gtk-icon-theme-name")
        if theme_name is not None and len(theme_name) > 0:
            return theme_name
    except BaseException:
        pass
    return None


def get_icon_theme_name_from_icons():
    try:
        lookup = icon_theme.lookup_icon("folder", 16, 0)
        if lookup is None:
            return None
        filename = lookup.get_filename()
        if filename is None:
            return None
        filename = os.path.realpath(filename)
        path = filename.split("/")
        for i in range(len(path) - 1):
            index = os.path.join("/".join(path[0:-i]), "index.theme")
            if os.path.exists(index):
                return path[-i - 1]
    except BaseException:
        pass
    return None


def get_icon_theme_name():
    theme_name = get_icon_theme_name_from_settings()
    if theme_name is not None:
        return theme_name

    theme_name = get_icon_theme_name_from_icons()
    if theme_name is not None:
        return theme_name

    return "Adwaita"


icon_theme_name = get_icon_theme_name()


menu_name = ""


COL_NAME = 0
COL_DISPLAY_NAME = 1
COL_COMMENT = 2
COL_EXEC = 3
COL_CATEGORIES = 4
COL_TYPE = 5
COL_G_ICON = 6
COL_ICON_NAME = 7
COL_FILENAME = 8
COL_EXPAND = 9
COL_SHOW = 10


def get_default_menu():
    """Return the filename of the default application menu."""
    prefixes = [util.getDefaultMenuPrefix(), ""]
    user_basedir = util.getUserMenusDirectory()
    for prefix in prefixes:
        filename = "{}{}".format(prefix, "applications.menu")
        user_dir = os.path.join(user_basedir, filename)
        if os.path.exists(user_dir):
            return filename
        system_dir = util.getSystemMenuPath(filename)
        if system_dir:
            return filename
    return None


def menu_to_treestore(treestore, parent, menu_items):
    """Convert the Alacarte menu to a standard treestore."""
    for item in menu_items:
        item_type = item[0]
        if item_type == MenuItemTypes.SEPARATOR:
            executable = ""
            name = _("Separator")
            displayed_name = name
            # Translators: Separator menu item
            tooltip = _("Separator")
            categories = ""
            filename = None
            icon_name = "content-loading-symbolic"
            icon = Gio.ThemedIcon.new(icon_name)
            item_type = MenuItemTypes.SEPARATOR
            show = False
        else:
            executable = item[2]["executable"]
            name = item[2]["display_name"]
            displayed_name = escapeText(name)
            show = item[2]["show"]
            tooltip = item[2]["comment"]
            categories = item[2]["categories"]
            icon = item[2]["icon"]
            filename = item[2]["filename"]
            icon_name = item[2]["icon_name"]

        treeiter = treestore.append(
            parent,
            [
                name,
                displayed_name,
                tooltip,
                executable,
                categories,
                item_type,
                icon,
                icon_name,
                filename,
                False,
                show,
            ],
        )

        if item_type == MenuItemTypes.DIRECTORY:
            treestore = menu_to_treestore(treestore, treeiter, item[3])

    return treestore


def get_treestore():
    """Get the TreeStore implementation of the current menu."""
    treestore = Gtk.TreeStore(
        str,  # Name
        str,  # Displayed Name
        str,  # Comment
        str,  # Executable
        str,  # Categories
        int,  # MenuItemType
        Gio.Icon,  # GIcon
        str,  # icon-name
        str,  # Filename
        bool,  # Expand
        bool,  # Show
    )
    menus = get_menus()
    if not menus:
        return None
    return menu_to_treestore(treestore, None, menus[0])


def get_extended_icons(icon_names, extended_names):
    results = []
    prefer_symbolic = icon_theme_name in ["Adwaita"] and "folder" in extended_names
    for name in icon_names:
        if icon_theme.has_icon(name):
            return results
    if prefer_symbolic:
        for name in extended_names:
            name = name + "-symbolic"
            if icon_theme.has_icon(name):
                results.append(name)
        if len(results) > 0:
            return results
    for name in extended_names:
        if icon_theme.has_icon(name):
            results.append(name)
    return results


def get_submenus(menu, tree_dir):
    """Get the submenus for a tree directory."""
    structure = []
    for child in menu.getContents(tree_dir):
        if isinstance(child, GMenu.TreeSeparator):
            structure.append([MenuItemTypes.SEPARATOR, child, None, None])
        else:
            if isinstance(child, (GMenu.TreeEntry, DummyTreeEntry)):
                item_type = MenuItemTypes.APPLICATION
                entry_id = child.get_desktop_file_id()
                app_info = child.get_app_info()
                icon = (
                    app_info.get_icon()
                    if hasattr(app_info, "get_icon")
                    else Gio.ThemedIcon.new("document-open-recent-symbolic")
                )
                icon_name = (
                    app_info.get_string("Icon")
                    if hasattr(app_info, "get_string")
                    else None
                )
                extended_icon_names = ["applications-other", "application-x-executable"]
                display_name = app_info.get_display_name()
                generic_name = app_info.get_generic_name()
                comment = app_info.get_description()
                keywords = app_info.get_keywords()
                categories = app_info.get_categories()
                executable = app_info.get_executable()
                filename = child.get_desktop_file_path()
                submenus = None

                is_hidden = (
                    app_info.get_is_hidden()
                    if hasattr(app_info, "get_is_hidden")
                    else False
                )
                no_display = (
                    app_info.get_nodisplay()
                    if hasattr(app_info, "get_nodisplay")
                    else False
                )
                show_in = (
                    app_info.get_show_in() if hasattr(app_info, "get_show_in") else True
                )
                hidden = is_hidden or no_display or not show_in

            elif isinstance(child, GMenu.TreeDirectory):
                item_type = MenuItemTypes.DIRECTORY
                entry_id = child.get_menu_id()
                icon = child.get_icon()
                icon_name = None
                extended_icon_names = ["folder"]
                display_name = child.get_name()
                generic_name = child.get_generic_name()
                comment = child.get_comment()
                keywords = []
                categories = ""
                executable = None
                filename = child.get_desktop_file_path()
                hidden = child.get_is_nodisplay()
                submenus = get_submenus(menu, child)

            else:
                continue

            icon_names = []
            if isinstance(icon, Gio.ThemedIcon):
                icon_names = icon.get_names()
            elif isinstance(icon, Gio.FileIcon):
                icon_names = [icon.get_file().get_path()]

            if icon_name is not None:
                icon_names = [icon_name] + icon_names

            for extended_icon_name in get_extended_icons(
                icon_names, extended_icon_names
            ):
                if isinstance(icon, Gio.ThemedIcon):
                    icon.append_name(extended_icon_name)
                icon_names.append(extended_icon_name)

            if icon_name is None:
                icon_name = icon_names[0]

            elif icon is None:
                icon = Gio.ThemedIcon.new(icon_name)

            if filename is not None:
                filename = os.path.realpath(filename)

            details = {
                "display_name": display_name,
                "generic_name": generic_name,
                "comment": comment,
                "keywords": keywords,
                "categories": categories,
                "executable": executable,
                "filename": filename,
                "icon": icon,
                "icon_name": icon_name,
                "show": not hidden,
            }
            entry = [item_type, entry_id, details, submenus]
            structure.append(entry)

    return structure


# Module-level variable for MenuetApplication.py
installing_filename = None


def get_menus():
    """Get the menu structure, including unregistered entries with OnlyShowIn=Old;."""
    menu = MenuEditor()
    if not menu.loaded:
        return None
    structure = []
    toplevels = []
    global menu_name
    menu_name = menu.tree.get_root_directory().get_menu_id()

    for child in menu.getMenus(None):
        toplevels.append(child)

    for top in toplevels:
        # Pass the first element of the tuple (the directory) to get_submenus
        structure.append(get_submenus(menu, top[0]))
    menu.unmap()

    user_apps_dir = os.path.expanduser("~/.local/share/applications")

    unregistered_apps = []

    if os.path.exists(user_apps_dir):
        for filename in os.listdir(user_apps_dir):
            if filename.endswith(".desktop"):
                filepath = os.path.join(user_apps_dir, filename)
                try:
                    with open(filepath, "r", encoding="utf-8") as f:
                        file_content = f.read()

                    # Isolate only incomplete assets with the isolation flag
                    if (
                        "OnlyShowIn=Old" in file_content
                        or "OnlyShowIn=OLD" in file_content
                    ):
                        exists = False
                        for cat_list in structure:
                            if isinstance(cat_list, list):
                                for item in cat_list:
                                    if (
                                        isinstance(item, list)
                                        and len(item) > 1
                                        and item[1] == filename
                                    ):
                                        exists = True
                                        break

                        if not exists:
                            app_info = None
                            try:
                                app_info = Gio.DesktopAppInfo.new_from_filename(
                                    filepath
                                )
                            except TypeError:
                                # Catch the constructor returned NULL error and create DummyAppInfo right here
                                parser = configparser.ConfigParser(interpolation=None)
                                parser.optionxform = str
                                try:
                                    parser.read(filepath, encoding="utf-8")
                                    app_info = DummyAppInfo(parser, filepath)
                                except (configparser.Error, OSError) as cp_ex:
                                    logger.debug(
                                        f"configparser fallback failed for {filename}: {cp_ex}"
                                    )

                            if app_info:
                                display_name = app_info.get_display_name() or filename
                                generic_name = app_info.get_generic_name() or ""
                                comment = app_info.get_description() or ""
                                keywords = app_info.get_keywords() or []
                                categories = app_info.get_categories() or ""
                                executable = app_info.get_executable() or ""

                                icon_name = "document-open-recent-symbolic"
                                icon = Gio.ThemedIcon.new(icon_name)
                                details = {
                                    "display_name": display_name,
                                    "generic_name": generic_name,
                                    "comment": comment,
                                    "keywords": keywords,
                                    "categories": categories,
                                    "executable": executable,
                                    "filename": os.path.realpath(filepath),
                                    "icon": icon,
                                    "icon_name": icon_name,
                                    "show": True,
                                }
                                unregistered_entry = [
                                    MenuItemTypes.APPLICATION,
                                    filename,
                                    details,
                                    None,
                                ]
                                unregistered_apps.append(unregistered_entry)

                except Exception as ex:
                    logger.error(f"Unregistered App ID: {filename}: {ex}")

    # Create unregistered area node for Menuet
    real_directory_path = "/usr/share/desktop-directories/cinnamon-other.directory"

    category_details = {
        "display_name": _("Unregistered Apps"),
        "generic_name": "Unregistered Apps",
        "comment": "Unregistered items missing required fields or not registered with CMenu",
        "keywords": [],
        "categories": "",
        "executable": None,
        "filename": real_directory_path,
        "icon": Gio.ThemedIcon.new("folder-unvisited-symbolic"),
        "icon_name": "folder-unvisited-symbolic",
        "show": True,
    }

    # Define node with dedicated temporary area ID
    unregistered_apps_node = [
        MenuItemTypes.DIRECTORY,
        "unregistered_apps",
        category_details,
        unregistered_apps,
    ]

    # Place it at the top (index 0) of the data structure.
    if (
        len(structure) > 0
        and isinstance(structure, list)
        and isinstance(structure[0], list)
    ):
        structure[0].insert(0, unregistered_apps_node)
    else:
        structure.append([unregistered_apps_node])
    logger.info(
        f"Total applications rescued in unregistered_apps area: {len(unregistered_apps)}"
    )

    return structure


def removeWhitespaceNodes(node):
    """Remove whitespace nodes from the xml dom."""
    remove_list = []
    for child in node.childNodes:
        if child.nodeType == xml.dom.minidom.Node.TEXT_NODE:
            child.data = child.data.strip()
            if not child.data.strip():
                remove_list.append(child)
        elif child.hasChildNodes():
            removeWhitespaceNodes(child)
    for node in remove_list:
        node.parentNode.removeChild(node)


def getUserMenuXml(tree):
    """Return the header portions of the menu xml file."""
    system_file = util.getSystemMenuPath(
        os.path.basename(tree.get_canonical_menu_path())
    )
    name = tree.get_root_directory().get_menu_id()
    menu_xml = (
        "<!DOCTYPE Menu PUBLIC '-//freedesktop//DTD Menu 1.0//EN'"
        " 'http://standards.freedesktop.org/menu-spec/menu-1.0.dtd'>\n"
    )
    menu_xml += "<Menu>\n  <Name>" + name + "</Name>\n  "
    if system_file is not None:
        menu_xml += '<MergeFile type="parent">' + system_file + "</MergeFile>\n"
    menu_xml += "</Menu>\n"
    return menu_xml


class MenuEditor:
    """MenuEditor class, adapted and minimized from Alacarte Menu Editor."""

    loaded = False

    def __init__(self, basename=None):
        """init"""

        # Remember to keep menuet-menu-validate's GMenu object creation
        # in-sync with this code
        basename = basename or get_default_menu()
        if basename is None:
            return

        # For systems where desktop directories are installed in subdirectories,
        # we need to first bring them to the toplevel for GMenu to see them
        # correctly.
        mapDesktopEnvironmentDirectories()

        self.tree = MenuetTreeWrapper.new(
            basename,
            GMenu.TreeFlags.SHOW_EMPTY
            | GMenu.TreeFlags.INCLUDE_EXCLUDED
            | GMenu.TreeFlags.INCLUDE_NODISPLAY
            | GMenu.TreeFlags.SHOW_ALL_SEPARATORS
            | GMenu.TreeFlags.SORT_DISPLAY_NAME,
        )
        self.load()

        self.path = os.path.join(
            util.getUserMenusDirectory(), self.tree.props.menu_basename
        )
        logger.debug(f"Using menu: {self.path}")
        self.loadDOM()

        self.loaded = self.hasContents()

    def loadDOM(self):
        """loadDOM"""
        try:
            self.dom = xml.dom.minidom.parse(self.path)
        except (OSError, xml.parsers.expat.ExpatError):
            self.dom = xml.dom.minidom.parseString(getUserMenuXml(self.tree))
        removeWhitespaceNodes(self.dom)

    def load(self):
        """load"""
        if not self.tree.load_sync():
            raise ValueError(
                f"can not load menu tree {self.tree.props.menu_basename!r}"
            )

    def unmap(self):
        unmapDesktopEnvironmentDirectories()

    def hasContents(self):
        for child in self.getMenus(None):
            submenus = self.getContents(child[0])
            if len(submenus) > 0:
                return True
        return False

    def getMenus(self, parent):
        """getMenus"""
        if parent is None:
            yield (self.tree.get_root_directory(), True)
            return

        item_iter = parent.iter()
        item_type = item_iter.next()
        while item_type != GMenu.TreeItemType.INVALID:
            if item_type == GMenu.TreeItemType.DIRECTORY:
                item = item_iter.get_directory()
                yield (item, True)
            item_type = item_iter.next()

    def getContents(self, item):
        """getContents"""
        contents = []
        item_iter = item.iter()
        item_type = item_iter.next()

        found_directories = []

        while item_type != GMenu.TreeItemType.INVALID:
            item = None
            if item_type == GMenu.TreeItemType.DIRECTORY:
                item = item_iter.get_directory()
                desktop = item.get_desktop_file_path()
                if desktop is not None:
                    desktop = os.path.realpath(desktop)
                if desktop is None or desktop in found_directories:
                    # Do not include directories without filenames.
                    # Do not include duplicate directories.
                    item = None
                else:
                    found_directories.append(desktop)
            elif item_type == GMenu.TreeItemType.ENTRY:
                item = item_iter.get_entry()
            elif item_type == GMenu.TreeItemType.HEADER:
                item = item_iter.get_header()
            elif item_type == GMenu.TreeItemType.ALIAS:
                item = item_iter.get_alias()
            elif item_type == GMenu.TreeItemType.SEPARATOR:
                item = item_iter.get_separator()
            if item:
                contents.append(item)
            item_type = item_iter.next()
        return contents
