#!/usr/bin/env python3
import shutil
import gi
import os
import sys
import cairo
import subprocess

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GdkPixbuf, Gdk, GLib

class PhotoViewer(Gtk.Window):
	def __init__(self, image_path=None):
		super().__init__(title="Picasa")
		self.set_default_size(640, 448)
		self.set_position(Gtk.WindowPosition.CENTER)

		self.current_folder = None
		self.image_files = []
		self.current_index = 0
		self.thumbnail_size = 150
		self.single_opened = False

		self.fullscreen_window = None
		self.fullscreen_image = None
		self.pixbuf = None
		self.scale_factor = 1.0
		self.offset = (0, 0)
		self.drag_start = None

		self.setup_browser()

		if image_path:
			if os.path.isfile(image_path):
				folder_path = os.path.dirname(os.path.abspath(image_path))
				print(f"Directory of the file: {folder_path}")
				self.iconify()
				self.load_folder(folder_path)
				self.show_fullscreen(image_path)
				self.single_opened = True
			elif os.path.isdir(image_path):  
				self.load_folder(image_path)
			else:
				print(f"Error image path: {image_path}")
				sys.exit(1)

	def setup_browser(self):
		self.grid = Gtk.Grid()
		self.add(self.grid)

		toolbar = Gtk.Toolbar()
		open_btn = Gtk.ToolButton(icon_widget=Gtk.Image.new_from_icon_name("document-open", Gtk.IconSize.LARGE_TOOLBAR))
		open_btn.connect("clicked", self.select_folder)
		toolbar.insert(open_btn, 0)
		self.grid.attach(toolbar, 0, 0, 1, 1)

		self.scrolled = Gtk.ScrolledWindow()
		self.flowbox = Gtk.FlowBox()
		self.flowbox.set_valign(Gtk.Align.START)
		self.flowbox.set_max_children_per_line(0)
		self.flowbox.set_selection_mode(Gtk.SelectionMode.SINGLE)
		self.flowbox.connect("child-activated", self.on_thumbnail_click)
		self.scrolled.set_size_request(800, 600)
		self.scrolled.add(self.flowbox)
		self.grid.attach(self.scrolled, 0, 1, 1, 1)

	def select_folder(self, widget=None):
		dialog = Gtk.FileChooserDialog(title="Select Folder", parent=self, action=Gtk.FileChooserAction.SELECT_FOLDER)
		dialog.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, Gtk.STOCK_OPEN, Gtk.ResponseType.OK)

		if dialog.run() == Gtk.ResponseType.OK:
			self.load_folder(dialog.get_filename())

		dialog.destroy()

	def load_folder(self, folder_path):
		if not os.path.isdir(folder_path):
			print(f"Ошибка: {folder_path} не является каталогом.")
			return

		self.current_folder = folder_path
		self.image_files = [
			os.path.join(self.current_folder, f)
			for f in os.listdir(self.current_folder)
			if f.lower().endswith(('png', 'jpg', 'jpeg', 'gif', 'bmp'))
		]
		self.update_thumbnails()

	def update_thumbnails(self):
		for child in self.flowbox.get_children():
			self.flowbox.remove(child)

		for path in self.image_files:
			thumbnail = self.create_thumbnail(path)
			self.flowbox.add(thumbnail)

		self.flowbox.show_all()

	def create_thumbnail(self, path):
		try:
			pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(path, self.thumbnail_size, self.thumbnail_size, True)
			image = Gtk.Image.new_from_pixbuf(pixbuf)
			event_box = Gtk.EventBox()
			event_box.add(image)
			event_box.set_tooltip_text(os.path.basename(path))
			event_box.connect("button-press-event", lambda w, e: self.show_fullscreen(path))
			return event_box
		except Exception as e:
			print(f"Error loading {path}: {e}")
			return None

	def on_thumbnail_click(self, flowbox, child):
		self.current_index = child.get_index()
		self.show_fullscreen(self.image_files[self.current_index])

	def show_fullscreen(self, path):
		if self.fullscreen_window is not None:
			self.fullscreen_window.destroy()

		self.fullscreen_window = Gtk.Window(type=Gtk.WindowType.TOPLEVEL)
		self.fullscreen_window.fullscreen()
		self.fullscreen_window.set_app_paintable(True)
		screen = self.fullscreen_window.get_screen()
		visual = screen.get_rgba_visual()
		if visual and screen.is_composited():
			self.fullscreen_window.set_visual(visual)
		self.fullscreen_window.connect("key-press-event", self.on_fullscreen_key_press)
		self.fullscreen_window.connect("delete-event", lambda *args: self.fullscreen_window.destroy())
		self.fullscreen_window.connect("button-press-event", self.on_button_press)
		self.fullscreen_window.connect("motion-notify-event", self.on_mouse_move)
		self.fullscreen_window.connect("button-release-event", self.on_button_release)

		self.fullscreen_window.add_events(
			Gdk.EventMask.BUTTON_PRESS_MASK |
			Gdk.EventMask.POINTER_MOTION_MASK |
			Gdk.EventMask.BUTTON_RELEASE_MASK |
			Gdk.EventMask.SMOOTH_SCROLL_MASK
		)

		try:
			self.pixbuf = GdkPixbuf.Pixbuf.new_from_file(path)
			self.fullscreen_image = Gtk.Image.new_from_pixbuf(self.pixbuf)
			self.scale_factor = 1.0
			self.offset = (0, 0)
		except Exception as e:
			print(f"Error loading {path}: {e}")
			return

		self.drawing_area = Gtk.DrawingArea()
		self.drawing_area.connect("draw", self.on_draw)

		self.drawing_area.set_events(
			Gdk.EventMask.BUTTON_PRESS_MASK |
			Gdk.EventMask.BUTTON_RELEASE_MASK |
			Gdk.EventMask.POINTER_MOTION_MASK |
			Gdk.EventMask.SCROLL_MASK
		)
		self.drawing_area.connect("scroll-event", self.on_scroll)
		self.drawing_area.connect("button-press-event", self.show_context_menu, path)
		self.fullscreen_window.add(self.drawing_area)
		self.fullscreen_window.show_all()

	def on_draw(self, widget, cr):
		if not self.pixbuf:
			return

		scaled_w = self.pixbuf.get_width() * self.scale_factor
		scaled_h = self.pixbuf.get_height() * self.scale_factor
		scaled_pixbuf = self.pixbuf.scale_simple(
			int(scaled_w),
			int(scaled_h),
			GdkPixbuf.InterpType.HYPER
		)

		cr.set_source_rgba(0.0, 0.0, 0.0, 0.0)
		cr.set_operator(cairo.OPERATOR_SOURCE)
		cr.paint()
		cr.set_operator(cairo.OPERATOR_OVER)

		x = (widget.get_allocated_width() - scaled_w) / 2 + self.offset[0]
		y = (widget.get_allocated_height() - scaled_h) / 2 + self.offset[1]

		Gdk.cairo_set_source_pixbuf(cr, scaled_pixbuf, x, y)
		cr.paint()

	def on_button_press(self, widget, event):
		if event.button == 1:
			self.drag_start = (event.x, event.y)

	def on_mouse_move(self, widget, event):
		if self.drag_start:
			dx = event.x - self.drag_start[0]
			dy = event.y - self.drag_start[1]
			self.offset = (self.offset[0] + dx, self.offset[1] + dy)
			self.drag_start = (event.x, event.y)
			self.drawing_area.queue_draw()

	def on_button_release(self, widget, event):
		self.drag_start = None

	def on_scroll(self, widget, event):
		if event.direction == Gdk.ScrollDirection.UP:
			self.scale_factor *= 1.1
		elif event.direction == Gdk.ScrollDirection.DOWN:
			self.scale_factor /= 1.1
		self.drawing_area.queue_draw()

	def on_fullscreen_key_press(self, widget, event):
		key = event.keyval
		if key == Gdk.KEY_Escape:
			self.fullscreen_window.destroy()
			if self.single_opened:
				Gtk.main_quit()
		elif key == Gdk.KEY_Left:
			self.current_index = max(0, self.current_index - 1)
			self.show_fullscreen(self.image_files[self.current_index])
		elif key == Gdk.KEY_Right:
			self.current_index = min(len(self.image_files)-1, self.current_index + 1)
			self.show_fullscreen(self.image_files[self.current_index])

	def on_flowbox_query_tooltip(self, flowbox, x, y, keyboard_mode, tooltip):
		child = flowbox.get_child_at_pos(x, y)
		if child is not None:
			event_box = child.get_child()
			tooltip.set_markup(event_box.get_tooltip_text())
			return True
		return False

	def show_context_menu(self, widget, event, image_path):
		if event.button == 3:
			menu = Gtk.Menu()

			copy_image_item = Gtk.MenuItem(label="Copy image")
			copy_image_item.connect("activate", self.copy_image_to_clipboard, image_path)
			menu.append(copy_image_item)

			copy_path_item = Gtk.MenuItem(label="Copy path to image")
			copy_path_item.connect("activate", self.copy_path, image_path)
			menu.append(copy_path_item)

			copy_folder_item = Gtk.MenuItem(label="Copy path to image folder")
			copy_folder_item.connect("activate", self.copy_folder_path, image_path)
			menu.append(copy_folder_item)

			open_folder_item = Gtk.MenuItem(label="Open image folder")
			open_folder_item.connect("activate", self.open_folder, image_path)
			menu.append(open_folder_item)

			menu.show_all()
			menu.popup_at_pointer(event)

	def copy_image_to_clipboard(self, widget, image_path):
		try:
			pixbuf = GdkPixbuf.Pixbuf.new_from_file(image_path)
			clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
			clipboard.set_image(pixbuf)
		except Exception as e:
			print(f"Error when copying image to clipboard: {e}")

	def copy_path(self, widget, image_path):
		clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
		clipboard.set_text(image_path, -1)
		print(f"Image copied to clipboard: {image_path}")

	def copy_folder_path(self, widget, image_path):
		folder_path = os.path.dirname(image_path)
		clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
		clipboard.set_text(folder_path, -1)

	def open_folder(self, widget, image_path):
		folder_path = os.path.dirname(image_path)
		os.system(f'xdg-open "{folder_path}"')
		print(f"Open image folder: {folder_path}")
		if subprocess.call(['which', 'nautilus'], stdout=subprocess.PIPE, stderr=subprocess.PIPE) == 0:
			subprocess.Popen(['nautilus', '--select', image_path])
		elif subprocess.call(['which', 'nemo'], stdout=subprocess.PIPE, stderr=subprocess.PIPE) == 0:
			subprocess.Popen(['nemo', '--select', image_path])
		else:
			print("U need nautilus or nemo for file selection:P")


if __name__ == "__main__":
	image_path = sys.argv[1] if len(sys.argv) > 1 else None
	win = PhotoViewer(image_path)
	win.connect("destroy", Gtk.main_quit)
	win.show_all()
	Gtk.main()
