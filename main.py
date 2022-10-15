import base64
import codecs
import csv
import io
import os
import time
import zipfile
from contextlib import contextmanager, redirect_stdout
from io import BytesIO
from urllib.request import urlopen

import click
import google.cloud.texttospeech as tts
import requests
import resizeimage.resizeimage
from PIL import Image
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from google_images_search import GoogleImagesSearch
from src.org_to_anki.ankiConnectWrapper.AnkiConnectorUtils import AnkiConnectorUtils

load_dotenv()


@click.group()
def cli():
    pass


@cli.command()
def sync_satori_reader():
    export_satory_reader()

    time.sleep(30)  # give time for Satori to publish the export

    exportLink = find_satori_reader_exports()

    resp = urlopen(exportLink)

    with zipfile.ZipFile(BytesIO(resp.read())) as archive:
        with archive.open("exported.csv") as csvFile:
            content = []
            words = csv.reader(codecs.iterdecode(csvFile, 'utf-8'), delimiter=',', quotechar='|')
            headers = next(words)
            for word in words:
                row_data = {key: value for key, value in zip(headers, word)}
                content.append(row_data)

    for word in content:
        add_note(
            word['Expression'],
            word['Expression-ReadingsOnly'],
            word['English'],
            word['Context1-PerYourPreferences'],
            word['Context1-Translation']
        )


def export_satory_reader():
    url = 'https://www.satorireader.com/api/studylist/export'

    requests.post(url, headers={
        'Cookie': f"SessionToken={os.environ['SATORI_READER_SESSION']}"
    }, json={
        "format": "csv",
        "whenCreatedRangeStartLocal": "2000-01-01T00:00:00.000Z",
        "whenCreatedRangeEndLocal": "2099-01-01T00:00:00.000Z",
        "cardTypes": ["JE"],
        "furiganaNotationFormat": "Anki"
    })


def find_satori_reader_exports():
    url = 'https://www.satorireader.com/review/exports'
    reqs = requests.get(url, headers={
        'Cookie': f"SessionToken={os.environ['SATORI_READER_SESSION']}"
    })

    soup = BeautifulSoup(reqs.text, 'html.parser')

    for link in soup.find_all('a'):
        if "review-card-export" in link.get('href'):
            return link.get('href')  # first link correspond to latest export


@cli.command()
def sync_takoboto():
    ankiConnectorUtils = AnkiConnectorUtils("http://localhost:8765")

    with suppressStream():
        notes = ankiConnectorUtils.makeRequest("findNotes", {
            "query": "deck:Takotobo"
        })

    with suppressStream():
        notesInfo = ankiConnectorUtils.makeRequest("notesInfo", {
            "notes": notes['result']
        })

    for note in notesInfo['result']:
        print(f"Processing card: {note['fields']['Japanese']['value']}")

        word = note['fields']['Japanese']['value']
        reading = note['fields']['Reading']['value']
        glossary = note['fields']['Meaning']['value']
        sentence = note['fields']['Sentence']['value']
        sentenceEnglish = note['fields']['SentenceMeaning']['value']

        add_note(word, reading, glossary, sentence, sentenceEnglish)


def add_note(word, reading, glossary, sentence, sentenceEnglish):
    ankiConnectorUtils = AnkiConnectorUtils("http://localhost:8765")

    with suppressStream():
        existingNote = ankiConnectorUtils.makeRequest("findNotes", {
            "query": f"deck:MiningTest Word:{word}"
        })

    if len(existingNote['result']) > 0:
        print(f"Note exists: {word}, ignoring...")
        return

    picture = download_image_from_google(word)
    audio = text_to_wav("ja-JP-Wavenet-D", word)
    sentenceAudio = text_to_wav("ja-JP-Wavenet-D", sentence)

    with suppressStream():
        response = ankiConnectorUtils.makeRequest("addNote", {
            "note": {
                "deckName": "MiningTest",
                "modelName": "JapaneseCard",
                "fields": {
                    "Word": word,
                    "Reading": reading,
                    "Glossary": glossary,
                    "Sentence": sentence,
                    "Sentence-English": sentenceEnglish,
                },
                "audio": [
                    {
                        "data": base64.b64encode(audio).decode(),
                        "filename": f"anki_tools_{word}.wav",
                        "fields": [
                            "Audio"
                        ]
                    },
                    {
                        "data": base64.b64encode(sentenceAudio).decode(),
                        "filename": f"anki_tools_{word}_{sentence}.wav",
                        "fields": [
                            "Sentence-Audio"
                        ]
                    }
                ],
                "picture": [
                    {
                        "data": base64.b64encode(picture.getvalue()).decode(),
                        "filename": f"anki_tools_{word}.jpg",
                        "fields": [
                            "Picture"
                        ]
                    }
                ],
                "tags": [
                    "anki-tools-albertofem"
                ]
            }
        })

    if response["error"] is not None:
        print(f"Error creating note: {response['error']}")


def download_image_from_google(word):
    gis = GoogleImagesSearch(os.environ["GOOGLE_SEARCH_API_KEY"], os.environ["GOOGLE_SEARCH_CSE"])

    gis.search({'q': word, 'num': 1})

    for image in gis.results():
        imagePil = Image.open(BytesIO(image.get_raw_data()))

        imageResized = resizeimage.resizeimage.resize_height(imagePil, 300, False)

        img_byte_arr = io.BytesIO()
        imageResized.save(img_byte_arr, format='PNG')

        return img_byte_arr


def text_to_wav(voice_name: str, text: str):
    language_code = "-".join(voice_name.split("-")[:2])

    text_input = tts.SynthesisInput(text=text)

    voice_params = tts.VoiceSelectionParams(
        language_code=language_code,
        name=voice_name
    )
    audio_config = tts.AudioConfig(audio_encoding=tts.AudioEncoding.LINEAR16)

    client = tts.TextToSpeechClient()

    response = client.synthesize_speech(
        input=text_input, voice=voice_params, audio_config=audio_config
    )

    return response.audio_content


@contextmanager
def suppressStream():
    with open(os.devnull, "w") as null:
        with redirect_stdout(null):
            yield


if __name__ == '__main__':
    cli()
