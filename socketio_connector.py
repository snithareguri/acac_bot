import logging
import uuid
import wave

from sanic import Blueprint, response
from sanic.request import Request
from socketio import AsyncServer
from typing import Optional, Text, Any, List, Dict, Iterable
import speech_recognition as sr

from rasa.core.channels.channel import InputChannel
from rasa.core.channels.channel import UserMessage, OutputChannel

import deepspeech
from deepspeech import Model
import scipy.io.wavfile as wav

import os
import sys
import io
import torch
import time
import numpy as np
from collections import OrderedDict
import urllib
from mapping import voice_ouput
import librosa

from TTS.models.tacotron import Tacotron
from TTS.layers import *
from TTS.utils.data import *
from TTS.utils.audio import AudioProcessor
from TTS.utils.generic_utils import load_config
from TTS.utils.text import text_to_sequence
from TTS.utils.synthesis import synthesis
from utils.text.symbols import symbols, phonemes
from TTS.utils.visual import visualize
from shutil import copyfile

logger = logging.getLogger(__name__)

class SocketBlueprint(Blueprint):
    def __init__(self, sio: AsyncServer, socketio_path, *args, **kwargs):
        self.sio = sio
        self.socketio_path = socketio_path
        super(SocketBlueprint, self).__init__(*args, **kwargs)

    def register(self, app, options):
        self.sio.attach(app, self.socketio_path)
        super(SocketBlueprint, self).register(app, options)


class SocketIOOutput(OutputChannel):

    @classmethod
    def name(cls):
        return "socketio"

    def __init__(self, sio, sid, bot_message_evt, message):
        self.sio = sio
        self.sid = sid
        self.bot_message_evt = bot_message_evt
        self.message = message


   # def tts(self,  text, OUT_FILE):
    #    from gtts import gTTS
     #   myobj = gTTS(text=text, lang='en', slow=False)
      #  myobj.save(OUT_FILE)

    def search_in_dict(self, text, OUT_FILE):
        for key, value in voice_ouput.items():
            if text == key:
                copyfile(value, OUT_FILE)

    async def _send_audio_message(self, socket_id, response,  **kwargs: Any):
        # type: (Text, Any) -> None
        """Sends a message to the recipient using the bot event."""
        ts = time.time()
        OUT_FILE = str(ts)+'.wav'
        link = "http://localhost:8888/"+OUT_FILE
        #self.tts(response['text'], OUT_FILE)
        self.search_in_dict(response['text'], OUT_FILE)
        await self.sio.emit(self.bot_message_evt, {'text':response['text'], "link":link}, room=socket_id)


    async def send_text_message(self, recipient_id: Text, message: Text, **kwargs: Any) -> None:
       """Send a message through this channel."""
       await self._send_audio_message(self.sid, {"text": message})

class SocketIOInput(InputChannel):
    """A socket.io input channel."""

    @classmethod
    def name(cls):
        return "socketio"

    @classmethod
    def from_credentials(cls, credentials):
        credentials = credentials or {}
        return cls(credentials.get("user_message_evt", "user_uttered"),
                   credentials.get("bot_message_evt", "bot_uttered"),
                   credentials.get("namespace"),
                   credentials.get("session_persistence", False),
                   credentials.get("socketio_path", "/socket.io"),
                   )

    def __init__(self,
                 user_message_evt: Text = "user_uttered",
                 bot_message_evt: Text = "bot_uttered",
                 namespace: Optional[Text] = None,
                 session_persistence: bool = False,
                 socketio_path: Optional[Text] = '/socket.io'
                 ):
        self.bot_message_evt = bot_message_evt
        self.session_persistence = session_persistence
        self.user_message_evt = user_message_evt
        self.namespace = namespace
        self.socketio_path = socketio_path


    def blueprint(self, on_new_message):
        sio = AsyncServer(async_mode="sanic", cors_allowed_origins="*")
        socketio_webhook = SocketBlueprint(
            sio, self.socketio_path, "socketio_webhook", __name__
        )

        @socketio_webhook.route("/", methods=['GET'])
        async def health(request):
            return response.json({"status": "ok"})

        @sio.on('connect', namespace=self.namespace)
        async def connect(sid, environ):
            logger.debug("User {} connected to socketIO endpoint.".format(sid))
            print('Connected!')

        def read_wav_file(self, fileName):
            with wave.open(fileName, 'rb') as w:
                rate = w.getframerate()
                frames = w.getnframes()
                buffer = w.readframes(frames)
                print(rate)
                print(frames)
            return buffer, rate

        @sio.on('disconnect', namespace=self.namespace)
        async def disconnect(sid):
            logger.debug("User {} disconnected from socketIO endpoint."
                         "".format(sid))

        @sio.on('session_request', namespace=self.namespace)
        async def session_request(sid, data):
            print('This is sessioin request')

            if data is None:
                data = {}
            if 'session_id' not in data or data['session_id'] is None:
                data['session_id'] = uuid.uuid4().hex
            await sio.emit("session_confirm", data['session_id'], room=sid)
            logger.debug("User {} connected to socketIO endpoint."
                         "".format(sid))

        def speech_to_text(WAVE_OUTPUT_FILENAME):
            r = sr.Recognizer()

            # open the file
            with sr.AudioFile(WAVE_OUTPUT_FILENAME) as source:
                # listen for the data (load audio to memory)
                audio_data = r.record(source)
                # recognize (convert from speech to text)
                text = r.recognize_google(audio_data)
                return text

        @sio.on('user_uttered', namespace=self.namespace)
        async def handle_message(sid, data):

            output_channel = SocketIOOutput(sio, sid, self.bot_message_evt, data['message'])
            if data['message'] == "/get_started":
                message = data['message']
            else:
                ##receive audio
                received_file = 'output_'+sid+'.wav'

                urllib.request.urlretrieve(data['message'], received_file)

                message = speech_to_text(received_file)
                await sio.emit(self.user_message_evt, {"text":message}, room=sid)


            message_rasa = UserMessage(message, output_channel, sid,
                                       input_channel=self.name())
            await on_new_message(message_rasa)

        return socketio_webhook
 
