# Picasa - Photo Viewer _**LINUX RE-IMPLEMENTATION**_

Picasa is a simple photo viewer application built with Python and GTK. It allows users to browse and view images from a folder, displaying thumbnails and providing fullscreen viewing with zoom and drag capabilities.

## Features

- **Image Browser**: 
  - Select and open a folder containing image files (PNG, JPG, JPEG, GIF, BMP).
  - Displays thumbnails of all supported images in the selected folder.

- **Fullscreen Image Viewer**:
  - View images in fullscreen mode with support for zooming and panning.
  - Navigate images using the left/right arrow keys.
  - Exit fullscreen mode with the Escape key.

- **Thumbnail Viewer**:
  - Display clickable thumbnails of images.
  - Clicking a thumbnail opens the image in fullscreen.

- **File System Integration**:
  - Open a folder via the graphical interface to display all images.
  - Directly open a specific image from the command line.

## Requirements

- Python 3.x
- GTK 3.x
- cairo
- PyGObject (gi)

## Installation

1. Install the required dependencies:

   ```bash
   sudo apt-get install python3-gi python3-cairo gir1.2-gtk-3.0

2. Install deb

   ```bash
   sudo dpkg -i Picasa_1.0_all.deb



**screenshots:**

![image](https://github.com/user-attachments/assets/19c9b3b7-588c-4027-9897-4548aaea3f43)

![image](https://github.com/user-attachments/assets/72a98b32-8bdf-4473-bbb5-6aeb9bc9fda0)

![image](https://github.com/user-attachments/assets/e24df931-de55-41e4-bf93-9ffb13d49039)
