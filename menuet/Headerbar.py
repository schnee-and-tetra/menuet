#!/usr/bin/python3
# SPDX-License-Identifier: GPL-3.0-only
#   Menu Editor & Launcher Recovery for Linux Mint Cinnamon
#   Copyright (C) 2012-2024 Sean Davis <sean@bluesabre.org>
#   Copyright (C) 2026 schnee-and-tetra <308144300+schnee-tetra@users.noreply.github.com>
import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk


class Headerbar(Gtk.HeaderBar):
    def __init__(self):
        super().__init__()

        self.set_title("Menuet")
        self.set_custom_title(Gtk.Label.new())
        self.set_show_close_button(True)

    def add_menu_button(self, icon_name, label, menu):
        image = Gtk.Image.new_from_icon_name(icon_name, Gtk.IconSize.BUTTON)
        image.set_pixel_size(16)
        image.set_property("use-fallback", True)

        button = Gtk.MenuButton.new()
        button.set_menu_model(menu)
        button.set_use_popover(True)
        button.set_tooltip_text(label)
        button.add(image)

        self.add(button)

        return button

    def add_button(self, icon_name, label):
        item = Gtk.Button.new_from_icon_name(icon_name, Gtk.IconSize.BUTTON)
        item.set_tooltip_text(label)

        image = item.get_image()
        if image is not None:
            image.set_property("use-fallback", True)

        self.add(item)

        return item

    def add_menu_button_from_action(self, action, menu):
        """Build a menu-popup button from a Gtk.Action showing `menu` as its popover."""
        icon_name = action.get_icon_name() or action.get_stock_id()
        label = action.get_tooltip() or action.get_label()
        return self.add_menu_button(icon_name, label, menu)

    def add_button_from_action(self, action):
        """Build a single button from a Gtk.Action and wire it to activate the action on click."""
        icon_name = action.get_icon_name() or action.get_stock_id()
        label = action.get_tooltip() or action.get_label()
        button = self.add_button(icon_name, label)
        button.connect("clicked", lambda _widget, act=action: act.activate())
        return button

    def add_search(self, widget):
        # Need to insert on right side
        box = Gtk.Box.new(Gtk.Orientation.VERTICAL, 0)
        box.set_valign(Gtk.Align.CENTER)

        box.add(widget)
        self.pack_end(box)

        return box
