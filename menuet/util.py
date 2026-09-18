#!/usr/bin/python3
# SPDX-License-Identifier: GPL-3.0-only
#   Menu Editor & Launcher Recovery for Linux Mint Cinnamon
#   Copyright (C) 2012-2024 Sean Davis <sean@bluesabre.org>
#   Copyright (C) 2016-2018 OmegaPhil <OmegaPhil@startmail.com>
#   Copyright (C) 2026 schnee-and-tetra <308144300+schnee-tetra@users.noreply.github.com>
import getpass
import gettext
import logging
import os
import re
import shutil
import subprocess

_ = gettext.gettext

import gi
import psutil

gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, GLib, Gtk

logger = logging.getLogger("menuet")

old_psutil_format = isinstance(psutil.Process.username, property)


def enum(**enums):
    """Add enumerations to Python."""
    return type("Enum", (), enums)


MenuItemTypes = enum(SEPARATOR=-1, APPLICATION=0, LINK=1, DIRECTORY=2)


MenuItemKeys = (
    # Key, Type, Required, Types (MenuItemType)
    ("Version", str, False, (0, 1, 2)),
    ("Type", str, True, (0, 1, 2)),
    ("Name", str, True, (0, 1, 2)),
    ("GenericName", str, False, (0, 1, 2)),
    ("NoDisplay", bool, False, (0, 1, 2)),
    ("Comment", str, False, (0, 1, 2)),
    ("Icon", str, False, (0, 1, 2)),
    ("Hidden", bool, False, (0, 1, 2)),
    ("OnlyShowIn", list, False, (0, 1, 2)),
    ("NotShowIn", list, False, (0, 1, 2)),
    ("DBusActivatable", bool, False, (0,)),
    ("PrefersNonDefaultGPU", bool, False, (0,)),
    ("X-GNOME-UsesNotifications", bool, False, (0,)),
    ("TryExec", str, False, (0,)),
    ("Exec", str, True, (0,)),
    ("Path", str, False, (0,)),
    ("Terminal", bool, False, (0,)),
    ("Actions", str, False, (0,)),
    ("MimeType", list, False, (0,)),
    ("Categories", list, False, (0,)),
    ("Implements", list, False, (0,)),
    ("Keywords", list, False, (0,)),
    ("StartupNotify", bool, False, (0,)),
    ("StartupWMClass", str, False, (0,)),
    ("URL", str, True, (1,)),
)


def getRelatedKeys(menu_item_type, key_only=False):
    if isinstance(menu_item_type, str):
        if menu_item_type == "Application":
            menu_item_type = MenuItemTypes.APPLICATION
        elif menu_item_type == "Link":
            menu_item_type = MenuItemTypes.LINK
        elif menu_item_type == "Directory":
            menu_item_type = MenuItemTypes.DIRECTORY

    results = []
    for tup in MenuItemKeys:
        if menu_item_type in tup[3]:
            if key_only:
                results.append(tup[0])
            else:
                results.append((tup[0], tup[1], tup[2]))
    return results


def escapeText(text):
    if text is None:
        return ""
    return GLib.markup_escape_text(text)


def getProcessUsername(process):
    """Get the username of the process owner. Return None if fail."""
    username = None

    try:
        username = process.username if old_psutil_format else process.username()
    except:  # noqa
        pass

    return username


def getProcessName(process):
    """Get the process name. Return None if fail."""
    p_name = None

    try:
        p_name = process.name if old_psutil_format else process.name()
    except:  # noqa
        pass

    return p_name


def getProcessList():
    """Return a list of unique process names for the current user."""
    username = getpass.getuser()
    try:
        pids = psutil.get_pid_list()
    except AttributeError:
        pids = psutil.pids()
    processes = []
    for pid in pids:
        try:
            process = psutil.Process(pid)
            p_user = getProcessUsername(process)
            if p_user == username:
                p_name = getProcessName(process)
                if p_name is not None and p_name not in processes:
                    processes.append(p_name)
        except:  # noqa
            pass
    processes.sort()
    return processes


def getRelativeName(filename: str):
    if filename.endswith(".desktop"):
        basename = filename.split("/applications/", 1)[1]
    elif filename.endswith(".directory"):
        basename = filename.split("/desktop-directories/", 1)[1]
    else:
        basename = ""
    return basename


def getBasename(filename: str):
    if filename.endswith(".desktop"):
        basename = filename.split("/applications/", 1)[1]
    elif filename.endswith(".directory"):
        basename = filename.split("/desktop-directories/", 1)[1]
        if basename.startswith(f"{getDefaultMenuName()}/"):
            basename = filename.split(f"{getDefaultMenuName()}/", 1)[1]
    else:
        basename = ""
    return basename


def getCurrentDesktop():
    current_desktop = os.environ.get("XDG_CURRENT_DESKTOP", "")
    current_desktop = current_desktop.lower()
    for desktop in ["budgie", "pantheon", "gnome"]:
        if desktop in current_desktop:
            return desktop
    if "kde" in current_desktop:
        kde_version = int(os.environ.get("KDE_SESSION_VERSION", "4"))
        if kde_version >= 5:
            return "plasma"
        return "kde"
    return current_desktop


def getDefaultMenuName():
    prefix = getDefaultMenuPrefix()
    if prefix.endswith("-"):
        return prefix[:-1]
    return prefix


def getDefaultMenuPrefix():
    """Return the default menu prefix."""
    prefix = os.environ.get("XDG_MENU_PREFIX", "")

    # Cinnamon and MATE don't set this variable
    if prefix == "":
        if "cinnamon" in os.environ.get("DESKTOP_SESSION", ""):
            prefix = "cinnamon-"
        elif "mate" in os.environ.get("DESKTOP_SESSION", ""):
            prefix = "mate-"
        # Somehow the XDG_MENU_PREFIX isn't exposed in Ubuntu Unity
        elif "unity" in os.environ.get("DESKTOP_SESSION", ""):
            prefix = "gnome-"

    if prefix == "":
        desktop = getCurrentDesktop()
        if desktop == "plasma":
            prefix = "kf5-"
        elif desktop == "kde":
            prefix = "kde4-"

    if prefix == "":
        processes = getProcessList()
        if "xfce4-panel" in processes:
            prefix = "xfce-"
        elif "mate-panel" in processes:
            prefix = "mate-"

    if len(prefix) == 0:
        logger.warning("No menu prefix found, Menuet will not function properly.")

    return prefix


def getMenuDiagnostics():
    diagnostics = {}
    keys = [
        "XDG_CURRENT_DESKTOP",
        "XDG_MENU_PREFIX",
        "DESKTOP_SESSION",
        "KDE_SESSION_VERSION",
    ]
    for k in keys:
        diagnostics[k] = os.environ.get(k, "None")

    menu_dirs = [getUserMenusDirectory()]
    for path in GLib.get_system_config_dirs():
        menu_dirs.append(os.path.join(path, "menus"))
    menus = []
    for menu_dir in menu_dirs:
        try:
            for filename in os.listdir(menu_dir):
                if filename.endswith(".menu"):
                    menus.append(os.path.join(menu_dir, filename))
        except FileNotFoundError:
            pass
    menus.sort()

    diagnostics["MENUS"] = ", ".join(menus)

    return diagnostics


def getItemSearchPaths():
    search_paths = []
    for path in GLib.get_system_data_dirs():
        search_paths.append(os.path.join(path, "applications"))
    return search_paths


def getItemPath(file_id):
    """Return the path to the system-installed .desktop file."""
    for path in getItemSearchPaths():
        file_path = os.path.join(path, file_id)
        if os.path.isfile(file_path):
            return file_path
    return None


def getUserApplicationsDirectory():
    """Return the path to the user applications directory."""
    item_dir = os.path.join(GLib.get_user_data_dir(), "applications")
    if not os.path.isdir(item_dir):
        os.makedirs(item_dir)
    return item_dir


def getUserItemPath(file_id):
    """Return the path to the system-installed .desktop file."""
    path = getUserApplicationsDirectory()
    file_path = os.path.join(path, file_id)
    if os.path.isfile(file_path):
        return file_path
    return None


def getDirectorySearchPaths():
    search_paths = []
    for path in GLib.get_system_data_dirs():
        search_paths.append(os.path.join(path, "desktop-directories"))
    return search_paths


def getDirectoryPath(file_id):
    """Return the path to the system-installed .directory file."""
    for path in getDirectorySearchPaths():
        file_path = os.path.join(path, file_id)
        if os.path.isfile(file_path):
            return file_path
    return None


def mapDesktopEnvironmentDirectories():
    """
    This feels wrong, but to make GMenu correctly handle desktop directories
    in subdirectories, we need to bring them up to the top level.
    """
    menu = getDefaultMenuName()
    if len(menu) == 0:
        return

    file_ids = []
    for path in getDirectorySearchPaths():
        if not os.path.exists(path):
            continue
        for filename in os.listdir(path):
            if filename.endswith(".desktop"):
                file_ids.append(filename)

    de_paths = {}
    for path in GLib.get_system_data_dirs():
        de_path = os.path.join(path, menu, "desktop-directories")
        if not os.path.exists(de_path):
            continue
        for filename in os.listdir(de_path):
            if filename not in file_ids:
                de_paths[filename] = de_path

    user_dir = getUserDirectoriesDirectory()
    for filename, basedir in de_paths.items():
        if filename in file_ids:
            continue

        target_dir = os.path.join(user_dir, menu)
        try:
            os.makedirs(target_dir)
        except BaseException:
            pass
        target = os.path.join(target_dir, filename)
        src = os.path.join(basedir, filename)
        if not os.path.exists(target):
            try:
                logger.debug(f"copy {src} to {target}")
                shutil.copy2(src, target)
            except BaseException:
                logger.warning(f"Failed to copy {src} to {target}")
                continue

        try:
            symlink = os.path.join(user_dir, filename)
            if os.path.exists(symlink):
                continue
            os.symlink(target, symlink)
        except BaseException:
            logger.warning(f"Failed to symlink {src} to {target}")


def unmapDesktopEnvironmentDirectories():
    """
    This feels wrong, but to make GMenu correctly handle desktop directories
    in subdirectories, we need to bring them up to the top level.
    """
    menu = getDefaultMenuName()
    if len(menu) == 0:
        return

    user_dir = getUserDirectoriesDirectory()

    de_dir = os.path.join(user_dir, menu)
    if not os.path.exists(de_dir):
        return

    for filename in os.listdir(user_dir):
        filename = os.path.join(user_dir, filename)

        if not filename.endswith(".directory"):
            continue
        if not os.path.islink(filename):
            continue

        realpath = os.path.realpath(filename)
        if not realpath.startswith(de_dir):
            continue

        try:
            os.remove(filename)
        except BaseException:
            logger.warning(f"Failed to remove symlink {filename}")


def getUserDirectoriesDirectory():
    """Return the path to the user desktop-directories directory."""
    menu_dir = os.path.join(GLib.get_user_data_dir(), "desktop-directories")
    if not os.path.isdir(menu_dir):
        os.makedirs(menu_dir)
    return menu_dir


def getUserDirectoryPath(file_id):
    """Return the path to the system-installed .directory file."""
    path = getUserDirectoriesDirectory()
    file_path = os.path.join(path, file_id)
    if os.path.isfile(file_path):
        return file_path
    return None


def getUserMenusDirectory():
    """Return the path to the user menus directory."""
    menu_dir = os.path.join(GLib.get_user_config_dir(), "menus")
    if not os.path.isdir(menu_dir):
        os.makedirs(menu_dir)
    return menu_dir


def getUserLauncherPath(basename):
    """Return the user-installed path to a .desktop or .directory file."""
    if basename.endswith(".desktop"):
        return getUserItemPath(basename)
    else:
        return getUserDirectoryPath(basename)


def getSystemMenuPath(file_id):
    """Return the path to the system-installed menu file."""
    for path in GLib.get_system_config_dirs():
        file_path = os.path.join(path, "menus", file_id)
        if os.path.isfile(file_path):
            return file_path
    return None


def getSystemLauncherPath(basename):
    """Return the system-installed path to a .desktop or .directory file."""
    if basename.endswith(".desktop"):
        return getItemPath(basename)
    else:
        return getDirectoryPath(basename)


def getDirectoryName(directory_str):
    """Return the directory name to be used in the XML file."""

    # Note: When adding new logic here, please see if
    # getDirectoryNameFromCategory should also be updated

    # Get the menu prefix
    prefix = getDefaultMenuPrefix()
    has_prefix = False

    basename = getBasename(directory_str)
    name, ext = os.path.splitext(basename)

    # Handle directories like xfce-development
    if name.startswith(prefix):
        name = name[len(prefix) :]
        name = name.title()
        has_prefix = True

    # Handle X-GNOME, X-XFCE
    if name.startswith("X-"):
        # Handle X-GNOME, X-XFCE
        condensed = name.split("-", 2)[-1]
        non_camel = re.sub("(?!^)([A-Z]+)", r" \1", condensed)
        return non_camel

    # Cleanup ArcadeGames and others as per the norm.
    if name.endswith("Games") and name != "Games":
        condensed = name[:-5]
        non_camel = re.sub("(?!^)([A-Z]+)", r" \1", condensed)
        return non_camel

    # GNOME...
    if name == "AudioVideo" or name == "Audio-Video":
        return "Multimedia"

    if name == "Game":
        return "Games"

    if name == "Network" and prefix != "xfce-":
        return "Internet"

    if name == "Utility":
        return "Accessories"

    if name == "System-Tools":
        if prefix == "lxde-":
            return "Administration"
        else:
            return "System"

    if name == "Settings":
        if prefix == "lxde-":
            return "DesktopSettings"
        elif has_prefix and prefix == "xfce-":
            return name
        else:
            return "Preferences"

    if name == "Settings-System":
        return "Administration"

    if name == "GnomeScience":
        return "Science"

    if name == "Utility-Accessibility":
        return "Universal Access"

    # We tried, just return the name.
    return name


def getDirectoryNameFromCategory(name):
    """Guess at the directory name a category should cause its launcher to
    appear in. This is used to add launchers to or remove from the right
    directories after category addition without having to restart menuet."""

    # Note: When adding new logic here, please see if
    # getDirectoryName should also be updated

    # I don't want to overload the use of getDirectoryName, so have spun out
    # this similar function

    # Only interested in generic categories here, so no need to handle
    # categories named after desktop environments
    prefix = getDefaultMenuPrefix()

    # Cleanup ArcadeGames and others as per the norm.
    if name.endswith("Games") and name != "Games":
        condensed = name[:-5]
        non_camel = re.sub("(?!^)([A-Z]+)", r" \1", condensed)
        return non_camel

    # GNOME...
    if name == "AudioVideo" or name == "Audio-Video":
        return "Multimedia"

    if name == "Game":
        return "Games"

    if name == "Network":
        return "Internet"

    if name == "Utility":
        return "Accessories"

    if name == "System-Tools":
        if prefix == "lxde-":
            return "Administration"
        else:
            return "System"

    if name == "Settings":
        if prefix == "lxde-":
            return "DesktopSettings"
        elif prefix == "xfce-":
            return name
        else:
            return "Preferences"

    if name == "Settings-System":
        return "Administration"

    if name == "GnomeScience":
        return "Science"

    if name == "Utility-Accessibility":
        return "Universal Access"

    # We tried, just return the name.
    return name


def getRequiredCategories(directory):
    """Return the list of required categories for a directory string."""
    prefix = getDefaultMenuPrefix()
    if directory is not None:
        basename = getBasename(directory)
        name, ext = os.path.splitext(basename)

        # Handle directories like xfce-development
        if name.startswith(prefix):
            name = name[len(prefix) :]
            name = name.title()

        if name == "Accessories":
            return ["Utility"]

        if name == "Games":
            return ["Game"]

        if name == "Multimedia":
            return ["AudioVideo"]

        else:
            return [name]
    else:
        # Get The Toplevel item if necessary...
        if prefix == "xfce-":
            return ["X-XFCE", "X-Xfce-Toplevel"]
    return []


def getSaveFilename(name, filename, item_type, force_update=False, parent_window=None):
    """Determime the filename to be used to store the launcher.

    Return the filename to be used."""
    # Check if the filename is writeable. If not, generate a new one.
    unique = filename is None or len(filename) == 0

    if unique or not os.access(filename, os.W_OK):
        # No filename, make one from the launcher name.
        if unique:
            BAD_CHARS = '/\\:*?"<>|/／￥：＊？”＜＞｜'
            trans_table = str.maketrans({c: "_" for c in BAD_CHARS})
            safe_name = name.translate(trans_table).lower().replace(" ", "-")
            if not safe_name:
                safe_name = "unnamed"
            basename = "menuet-" + safe_name

        # Use the current filename as a base.
        else:
            basename = getRelativeName(filename)

        # Split the basename into filename and extension.
        name, ext = os.path.splitext(basename)

        # Get the save location of the launcher base on type.
        if item_type == "Application":
            path = getUserApplicationsDirectory()
            ext = ".desktop"
        elif item_type == "Directory":
            path = getUserDirectoriesDirectory()
            ext = ".directory"
        else:
            path = ""

        basedir = os.path.dirname(os.path.join(path, basename))
        if not os.path.exists(basedir):
            os.makedirs(basedir)

        # Index for unique filenames.
        count = 1

        # Be sure to not overwrite system launchers if new.
        if unique:
            # Check for the system version of the launcher.
            if getSystemLauncherPath(f"{name}{ext}") is not None:
                # If found, check for any additional ones.
                while getSystemLauncherPath(f"{name}{count}{ext}") is not None:
                    count += 1

                # Now be sure to not overwrite locally installed ones.
                filename = os.path.join(path, name)
                filename = f"{filename}{count}{ext}"

                # Append numbers as necessary to make the filename unique.
                while os.path.exists(filename):
                    new_basename = f"{name}{count}{ext}"
                    filename = os.path.join(path, new_basename)
                    count += 1

            else:
                # Create the new base filename.
                filename = os.path.join(path, name)
                filename = f"{filename}{ext}"

                # Append numbers as necessary to make the filename unique.
                while os.path.exists(filename):
                    new_basename = f"{name}{count}{ext}"
                    filename = os.path.join(path, new_basename)
                    count += 1
        else:
            # Create the new base filename.
            filename = os.path.join(path, basename)

            if force_update:
                return filename

            # Append numbers as necessary to make the filename unique.
            while os.path.exists(filename):
                new_basename = f"{name}{count}{ext}"
                filename = os.path.join(path, new_basename)
                count += 1

    return filename


def check_keypress(event, keys):
    """Compare keypress events with desired keys and return True if matched."""
    state = event.get_state()

    if "Control" in keys and not bool(state & Gdk.ModifierType.CONTROL_MASK):
        return False
    if "Alt" in keys and not bool(state & Gdk.ModifierType.MOD1_MASK):
        return False
    if "Shift" in keys and not bool(state & Gdk.ModifierType.SHIFT_MASK):
        return False
    if "Super" in keys and not bool(state & Gdk.ModifierType.SUPER_MASK):
        return False

    if "Escape" in keys:
        keys[keys.index("Escape")] = "escape"

    keyval_name = Gdk.keyval_name(event.get_keyval()[1])
    if keyval_name is None:
        return False
    return keyval_name.lower() in keys


def determine_bad_desktop_files():
    """Run the gmenu-invalid-desktop-files script to get at the GMenu library's
    debug output, which lists files that failed to load, and return these as a
    sorted list."""

    # Run the helper script with normal binary lookup via the shell, capturing
    # stderr, sensitive to errors
    try:
        result = subprocess.run(
            ["menuet-menu-validate"], stderr=subprocess.PIPE, shell=True, check=True
        )
    except subprocess.CalledProcessError:
        return []

    # stderr is returned as bytes, so converting it to the line-buffered output
    # I actually want
    bad_desktop_files = []
    for line in result.stderr.decode("UTF-8").split("\n"):
        matches = re.match(r'^Failed to load "(.+\.desktop)"$', line)
        if matches:
            desktop_file = matches.groups()[0]
            if validate_desktop_file(desktop_file):
                bad_desktop_files.append(matches.groups()[0])

    # Alphabetical sort on bad desktop file paths
    bad_desktop_files.sort()

    return bad_desktop_files


def find_program(program):
    program = program.strip()
    if len(program) == 0:
        return None

    params = list(GLib.shell_parse_argv(program)[1])
    executable = params[0]

    if os.path.exists(executable):
        return executable

    path = GLib.find_program_in_path(executable)
    if path is not None:
        return path

    return None


def find_icon_path():
    appdir = os.environ.get("APPDIR")
    if appdir:
        appimage_icon = os.path.join(appdir, "menuet.png")
        if os.path.exists(appimage_icon):
            return appimage_icon

    current_dir = os.path.dirname(os.path.abspath(__file__))
    dev_icon = os.path.join(current_dir, "..", "menuet.png")
    if os.path.exists(dev_icon):
        return os.path.normpath(dev_icon)

    return None


def show_uri(parent, link):
    """Open a web browser to the specified link."""
    screen = parent.get_screen()
    Gtk.show_uri(screen, link, Gtk.get_current_event_time())


def validate_desktop_file(desktop_file):
    """Validate a desktop entry file using desktop-file-validate."""
    import os
    import subprocess

    if not desktop_file or not os.path.exists(desktop_file):
        return _("File does not exist.")

    try:
        res = subprocess.run(
            ["desktop-file-validate", desktop_file],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )

        if res.returncode == 0:
            return None

        err_msg = res.stderr.strip()

        if 'error: key "Type" is required' in err_msg:
            return _("%s key not found") % "Type"
        if 'is not a valid value for key "Type"' in err_msg:
            return _("%s value is invalid - currently '%s', should be '%s'") % (
                "Type",
                "Invalid",
                GLib.KEY_FILE_DESKTOP_TYPE_APPLICATION,
            )
        if (
            "not found in the PATH" in err_msg
            or "error: error: value" in err_msg
            and 'for key "Exec"' in err_msg
        ):
            return _("%s program has not been found in the PATH") % "Exec"

        if 'error: key "Exec" is required' in err_msg:
            return False
        if 'value "Service" for key "Type" is deprecated' in err_msg:
            return False

        if (
            "error: file contains lines that are not" in err_msg
            or "error: group" in err_msg
        ):
            return (
                _("Unable to load desktop file due to the following error: %s")
                % err_msg.splitlines()[0]
            )

        return err_msg

    except Exception as e:
        if os.path.exists(desktop_file) and os.path.getsize(desktop_file) > 0:
            return None
        return _("Unable to load desktop file due to the following error: %s") % e
