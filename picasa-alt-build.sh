#!/bin/bash

APP_NAME="Picasa"
VERSION="1.0"
ARCH="all"
INSTALL_DIR="/usr/local/bin"
DEB_DIR="${APP_NAME}_${VERSION}_${ARCH}"

# Очистка и подготовка структуры
rm -rf $DEB_DIR && mkdir -p $DEB_DIR/DEBIAN $DEB_DIR$INSTALL_DIR $DEB_DIR/usr/share/applications $DEB_DIR/usr/share/icons/hicolor/512x512/apps

# Создание control-файла
cat << EOF > $DEB_DIR/DEBIAN/control
Package: $APP_NAME
Version: $VERSION
Section: graphics
Priority: optional
Architecture: $ARCH
Depends: python3, python3-gi, gir1.2-gtk-3.0, gir1.2-gdkpixbuf-2.0
Maintainer: cds4r <querror.codeto@gmail.com>
Description: A simple photo viewer based on GTK
EOF

# Копирование файлов
cp Picasa.py $DEB_DIR$INSTALL_DIR/$APP_NAME
chmod +x $DEB_DIR$INSTALL_DIR/$APP_NAME

# .desktop файл
cat << EOF > $DEB_DIR/usr/share/applications/$APP_NAME.desktop
[Desktop Entry]
Name=Picasa
Exec=$INSTALL_DIR/$APP_NAME %f
Icon=Picasa.png
Terminal=false
Type=Application
MimeType=image/jpeg;image/png;image/gif;image/bmp;image/tiff;image/x-ms-bmp;image/x-icon;
Categories=Graphics;Viewer;
EOF

# Создание иконки (замени picasa-icon.png на свою иконку)
cp Picasa.png $DEB_DIR/usr/share/icons/hicolor/512x512/apps/$APP_NAME.png

# Создание .deb
dpkg-deb --build $DEB_DIR

echo "DEB package built: ${DEB_DIR}.deb"
