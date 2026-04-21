#!/bin/bash
# Das Display für den Beamer festlegen
export DISPLAY=:0

# 1. Alte Browser und alte Quiz-Instanzen beenden
killall chromium-browser chromium 2>/dev/null
pkill -f "python app.py" 2>/dev/null
sleep 2

# 2. In das richtige Verzeichnis springen
cd /home/aleranzer/quizshark

# 3. Das Quiz-Backend aus der virtuellen Umgebung starten
# Das "&" am Ende ist wichtig, damit das Skript weiterläuft!
./venv/bin/python app.py &

# 4. 5 Sekunden warten, bis der Server bereit ist
sleep 5

# 5. Den Beamer als Hauptmonitor aktivieren
xrandr --output HDMI-A-1 --primary --auto

# 6. Chromium im Kiosk-Modus starten
chromium --kiosk \
         --start-fullscreen \
         --autoplay-policy=no-user-gesture-required \
         --noerrdialogs \
         --disable-infobars \
         --user-data-dir=/tmp/quiz-session \
         --no-sandbox \
         "http://192.168.8.203:8080/tv" &
