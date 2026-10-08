Fonts for the Text & layout editor. All are Google Fonts under the SIL Open
Font License 1.1 (https://openfontlicense.org), which allows embedding them in
PDFs and serving them for web use. Static TTFs taken from the
@expo-google-fonts npm packages.

To add a font: put <Key>-Regular.ttf (and -Bold / -RegularItalic /
-BoldItalic if it has them) in this folder and add it to LAYOUT_FONTS in
server.py. The browser preview and the server both read from here.
