# ytdownloader
A YouTube downloader working with an .html file frontend and a .py file backend.

English Instructions:

Requirements:

Python 3 must be installed.
Terminal/Command Prompt must be open.
1. Install yt-dlp:
pip install yt-dlp
2. Install ffmpeg (required for MP3 conversion):

macOS: brew install ffmpeg
Windows: Download from https://ffmpeg.org/download.html and add to PATH.
Linux: sudo apt install ffmpeg

3. Start the backend:
python ytdl_backend.py
Keep the terminal open, do not close it.
4. Open the HTML file:
Open ytdl_v1_frontend.html or ytdl_v2_frontend.html in your browser. Both do the same thing, they just look different.
5. Use:
Paste the YouTube link → Analyze → select format/quality → Download.
The files will be downloaded to the ~/Downloads folder.

The site will not work if the backend is closed. Python's ytdl_backend.py must be running with every use.

----------------------------------------------------------------------------------------------------------------------------------------------

Turkish Instructions:

Gereksinimler:

Python 3 kurulu olmalı
Terminal / Komut İstemi açık olmalı


1. yt-dlp kur:
pip install yt-dlp
2. ffmpeg kur (MP3 dönüştürme için şart):

macOS: brew install ffmpeg
Windows: https://ffmpeg.org/download.html adresinden indir, PATH'e ekle
Linux: sudo apt install ffmpeg

3. Backend'i başlat:
python ytdl_backend.py
Terminal açık kalsın, kapatma.
4. HTML dosyasını aç:
ytdl_v1_frontend.html ya da ytdl_v2_frontend.html dosyasını tarayıcıda aç. İkisi de aynı şeyi yapar, görünümleri farklı.
5. Kullan:
YouTube linkini yapıştır → Analyse → format/kalite seç → Download.
Dosyalar ~/Downloads klasörüne iner.

Backend kapalıysa site çalışmaz. Her kullanımda python ytdl_backend.py çalışıyor olmalı.
