#!/bin/bash
rasa run --enable-api -p 5005 --debug &
rasa run actions --actions actions &
sudo docker run -p 8000:8000 rasa/duckling &
python3 -m http.server 8888 
