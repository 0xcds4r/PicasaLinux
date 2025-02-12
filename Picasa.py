#!/usr/bin/env python3
import shutil
import gi
import os
import sys
import cairo
import math
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
		self.rotation_angle = 0
		self.current_image_path = ""

		self.animation = None
		self.current_iter = None
		self.animation_timeout = None
		self.current_frame_delay = 0

		self.setup_browser()

		if image_path:
			if os.path.isfile(image_path):
				folder_path = os.path.dirname(os.path.abspath(image_path))
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

		about_btn = Gtk.ToolButton(icon_widget=Gtk.Image.new_from_icon_name("help-about", Gtk.IconSize.LARGE_TOOLBAR))
		about_btn.connect("clicked", self.show_about_dialog)
		toolbar.insert(about_btn, 1)

		self.grid.attach(toolbar, 0, 0, 1, 1)

		self.scrolled = Gtk.ScrolledWindow()
		self.flowbox = Gtk.FlowBox()
		self.flowbox.set_valign(Gtk.Align.START)
		self.flowbox.set_max_children_per_line(8)
		self.flowbox.set_selection_mode(Gtk.SelectionMode.SINGLE)
		self.flowbox.connect("child-activated", self.on_thumbnail_click)
		self.scrolled.set_size_request(800, 600)
		self.scrolled.add(self.flowbox)
		self.grid.attach(self.scrolled, 0, 1, 1, 1)

	def show_about_dialog(self, widget=None):
		about_dialog = Gtk.AboutDialog()
		about_dialog.set_program_name("Picasa for Linux")
		about_dialog.set_version("build 1.0.4")
		try:
			pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size("/usr/share/icons/hicolor/512x512/apps/Picasa.png", 128, 128)  # Resize if needed
			about_dialog.set_logo(pixbuf)
		except Exception as e:
			print(f"Error loading logo: {e}")
		about_dialog.set_website("https://github.com/0xcds4r/PicasaLinux")
		about_dialog.set_website_label("Project GitHub")
		about_dialog.set_copyright("by 0xcds4r")
		about_dialog.run()
		about_dialog.destroy()

	def select_folder(self, widget=None):
		dialog = Gtk.FileChooserDialog(title="Select Folder", parent=self, action=Gtk.FileChooserAction.SELECT_FOLDER)
		dialog.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, Gtk.STOCK_OPEN, Gtk.ResponseType.OK)

		if dialog.run() == Gtk.ResponseType.OK:
			self.load_folder(dialog.get_filename())
		dialog.destroy()

	def load_folder(self, folder_path):
		if not os.path.isdir(folder_path):
			print(f"Error: {folder_path} is not a directory.")
			return

		self.current_folder = folder_path
		self.image_files = [
			os.path.join(self.current_folder, f)
			for f in os.listdir(self.current_folder)
			if f.lower().endswith(('png', 'jpg', 'jpeg', 'bmp', 'heic')) #'gif'
		]
		self.update_thumbnails()

	def update_thumbnails(self):
		for child in self.flowbox.get_children():
			self.flowbox.remove(child)

		for path in self.image_files:
			thumbnail = self.create_thumbnail(path)
			if thumbnail:
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
		screen = self.fullscreen_window.get_screen()
		monitor = Gdk.Display.get_default().get_primary_monitor()
		geom = monitor.get_geometry()
	
		self.fullscreen_window.set_default_size(geom.width, geom.height)
		self.fullscreen_window.move(geom.x, geom.y)

		self.fullscreen_window.set_position(Gtk.WindowPosition.CENTER)
		self.fullscreen_window.set_transient_for(self)
		self.fullscreen_window.set_modal(False)  
		self.fullscreen_window.set_decorated(False)

		self.fullscreen_window.set_app_paintable(True)
		self.fullscreen_window.set_skip_taskbar_hint(True)

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
			self.animation = GdkPixbuf.PixbufAnimation.new_from_file(path)
			
			if self.animation.is_static_image():
				# Статичное изображение
				self.pixbuf = self.animation.get_static_image()
				self.animation = None
			else:
				# Анимация
				self.current_iter = self.animation.get_iter()
				self.pixbuf = self.current_iter.get_pixbuf()
				self.start_animation()

			# Общие настройки масштаба и положения
			self.current_image_path = path
			img_width = self.pixbuf.get_width()
			img_height = self.pixbuf.get_height()

			screen_width = geom.width
			screen_height = geom.height

			padding = min(screen_width, screen_height) * 0.05
			safe_width = screen_width - 2 * padding
			safe_height = screen_height - 2 * padding

			scale_w = safe_width / img_width if img_width > 0 else 1.0
			scale_h = safe_height / img_height if img_height > 0 else 1.0
			self.scale_factor = min(scale_w, scale_h, 1.0)

			if self.scale_factor < 0.1:
				self.scale_factor = 0.1

			self.offset = (0, 0)
			self.rotation_angle = 0
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


	def start_animation(self):
		if self.animation_timeout:
			GLib.source_remove(self.animation_timeout)
		self.update_animation()

	def update_animation(self):
		return False

	def on_draw(self, widget, cr):
		if not self.pixbuf:
			return

		cr.set_source_rgba(0.0, 0.0, 0.0, 0.3)
		cr.set_operator(cairo.OPERATOR_SOURCE)
		cr.paint()
		cr.set_operator(cairo.OPERATOR_OVER)

		alloc = widget.get_allocation()
		width = alloc.width
		height = alloc.height

		img_width = self.pixbuf.get_width()
		img_height = self.pixbuf.get_height()

		cr.save()
		cr.translate(width/2 + self.offset[0], height/2 + self.offset[1])
		cr.rotate(math.radians(self.rotation_angle))

		if self.rotation_angle % 180 == 90:
			cr.scale(self.scale_factor * img_height / img_width, self.scale_factor * img_width / img_height)
			cr.translate(-img_width/2, -img_height/2)
		else:
			cr.scale(self.scale_factor, self.scale_factor)
			cr.translate(-img_width/2, -img_height/2)

		Gdk.cairo_set_source_pixbuf(cr, self.pixbuf, 0, 0)
		cr.paint()
		cr.restore()

		self.draw_info_overlay(cr, img_width, img_height, width, height)

	def draw_info_overlay(self, cr, img_width, img_height, screen_width, screen_height):
		font_size = 10
		padding = 4
		margin = 2

		cr.set_font_size(font_size)
		cr.set_source_rgb(1, 1, 1)

		info = f"{os.path.basename(self.current_image_path)} ({img_width}x{img_height}) "
		info += f"Zoom: {int(self.scale_factor*100)}% Rot: {self.rotation_angle}°"

		extents = cr.text_extents(info)
		text_width = extents.width
		text_height = extents.height

		overlay_width = text_width + 2 * padding
		overlay_height = font_size + 2 * padding

		overlay_x = margin
		overlay_y = margin

		if overlay_x + overlay_width > screen_width:
			overlay_x = screen_width - overlay_width - margin
		if overlay_y + overlay_height > screen_height:
			overlay_y = screen_height - overlay_height - margin

		cr.set_source_rgba(0, 0, 0, 0.55)
		cr.rectangle(overlay_x, overlay_y, overlay_width, overlay_height)
		cr.fill()

		text_x = overlay_x + padding
		text_y = overlay_y + padding + font_size * 0.8

		cr.set_source_rgb(1, 1, 1)
		cr.move_to(text_x, text_y)
		cr.show_text(info)

	def on_button_press(self, widget, event):
		if event.button == 1:
			if event.type == Gdk.EventType._2BUTTON_PRESS:
				self.scale_factor = 1.0
				self.offset = (0, 0)
				self.rotation_angle = 0
				self.drawing_area.queue_draw()
			else:
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
		elif event.direction == Gdk.ScrollDirection.SMOOTH:
			delta_x, delta_y = event.get_scroll_deltas()
			if delta_y != 0:
				self.scale_factor *= 1.0 + delta_y * 0.1

		self.scale_factor = max(0.1, min(self.scale_factor, 10.0))
		self.drawing_area.queue_draw()

	def reset_animation(self):
		if self.animation_timeout:
			GLib.source_remove(self.animation_timeout)
			self.animation_timeout = None

	def on_fullscreen_key_press(self, widget, event):
		key = event.keyval
		if key == Gdk.KEY_Escape:
			self.fullscreen_window.destroy()
			if self.single_opened:
				Gtk.main_quit()
			self.reset_animation()
		elif key == Gdk.KEY_Left:
			self.reset_animation()
			self.current_index = max(0, self.current_index - 1)
			self.show_fullscreen(self.image_files[self.current_index])
		elif key == Gdk.KEY_Right:
			self.reset_animation()
			self.current_index = min(len(self.image_files)-1, self.current_index + 1)
			self.show_fullscreen(self.image_files[self.current_index])
		elif key == Gdk.KEY_Up:
			self.rotation_angle = (self.rotation_angle + 90) % 360
			self.drawing_area.queue_draw()
		elif key == Gdk.KEY_Down:
			self.rotation_angle = (self.rotation_angle - 90) % 360
			self.drawing_area.queue_draw()

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
			print(f"Error copying image: {e}")

	def copy_path(self, widget, image_path):
		clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
		clipboard.set_text(image_path, -1)

	def copy_folder_path(self, widget, image_path):
		clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
		clipboard.set_text(os.path.dirname(image_path), -1)

	def open_folder(self, widget, image_path):
		folder_path = os.path.dirname(image_path)
		try:
			if subprocess.call(['which', 'nautilus'], stdout=subprocess.PIPE) == 0:
				subprocess.Popen(['nautilus', '--select', image_path])
			elif subprocess.call(['which', 'nemo'], stdout=subprocess.PIPE) == 0:
				subprocess.Popen(['nemo', '--select', image_path])
			else:
				os.system(f'xdg-open "{folder_path}"')
		except Exception as e:
			print(f"Error opening folder: {e}")

if __name__ == "__main__":
	image_path = sys.argv[1] if len(sys.argv) > 1 else None
	win = PhotoViewer(image_path)
	win.connect("destroy", Gtk.main_quit)
	win.show_all()
	Gtk.main()