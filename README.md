# Picasa - Photo Viewer _**LINUX RE-IMPLEMENTATION**_

Picasa is a simple photo viewer application re-implemented for Linux using Python and GTK. It allows users to browse and view images from a folder, displaying thumbnails and offering fullscreen viewing with zoom and drag capabilities.

I do not claim ownership of the original application by Google. This is simply a convenient tool that I personally enjoy and wanted to port to Linux for convenience, to share with other users who are also looking for this useful tool.

If any developers would like to improve this project, I welcome contributions. Feel free to suggest ideas for improvements through issues, forks, and so on.

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

## Test

You can test it before installation:
```
wget https://raw.githubusercontent.com/0xcds4r/PicasaLinux/refs/heads/main/Picasa.py
```

```
python Picasa.py <image_name.png or path (if exists)>
```

## Installation
```
wget https://github.com/0xcds4r/PicasaLinux/releases/download/release/install.sh
```

```
chmod +x ./install.sh
```

```
./install.sh
```

## Photos
![image](https://github.com/user-attachments/assets/9193177b-afac-4b97-b83e-3fe0f2489bf7)
