#!/usr/bin/python3
# SPDX-License-Identifier: GPL-3.0-only
#   Menu Editor & Launcher Recovery for Linux Mint Cinnamon
#   Copyright (C) 2012-2024 Sean Davis <sean@bluesabre.org>
#   Copyright (C) 2026 schnee-and-tetra <308144300+schnee-tetra@users.noreply.github.com>
import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk


class Toolbar(Gtk.Toolbar):
    def __init__(self):
        super().__init__()
        self.set_show_arrow(False)

        context = self.get_style_context()
        context.add_class("primary-toolbar")

    def add_menu_button(self, icon_name, label, menu):
        item = Gtk.ToolItem.new()

        image = Gtk.Image.new_from_icon_name(icon_name, Gtk.IconSize.LARGE_TOOLBAR)
        image.set_pixel_size(24)

        button = Gtk.MenuButton.new()
        button.set_menu_model(menu)
        button.set_use_popover(False)
        button.set_relief(Gtk.ReliefStyle.NONE)
        button.set_tooltip_text(label)
        button.add(image)

        context = button.get_style_context()
        context.add_class("toolbutton")

        item.add(button)
        self.add(item)

        return item

    def add_separator(self):
        separator = Gtk.SeparatorToolItem.new()
        self.add(separator)
        return separator

    def add_button(self, icon_name, label):
        image = Gtk.Image.new_from_icon_name(icon_name, Gtk.IconSize.LARGE_TOOLBAR)
        image.set_pixel_size(24)

        item = Gtk.ToolButton.new(image, label)
        item.set_tooltip_text(label)

        self.add(item)

        return item

    def add_search(self, widget):
        item = Gtk.ToolItem.new()

        item.add(widget)
        self.add(item)

        return item
