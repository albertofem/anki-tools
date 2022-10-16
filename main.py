import base64
import codecs
import csv
import io
import os
import random
import string
import time
import zipfile
from contextlib import contextmanager, redirect_stdout
from io import BytesIO
from urllib.request import urlopen

import PIL
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
@click.option('--no-trigger', is_flag=True, show_default=True, default=False,
              help='Do not trigger a Satori Reader export')
@click.argument('deck', default='Mining')
def sync_satori_reader(no_trigger, deck):
    if no_trigger is False:
        click.echo("Triggering Anki export in Satori reader...")
        export_satory_reader()
        click.echo("Waiting 30 seconds for export to finish...")
        time.sleep(30)  # give time for Satori to publish the export

    click.echo("Proceeding to download export...")

    exportLink = find_satori_reader_exports()

    resp = urlopen(exportLink)

    with zipfile.ZipFile(BytesIO(resp.read())) as archive:
        with archive.open("exported.csv") as csvFile:
            content = []
            words = csv.reader(codecs.iterdecode(csvFile, 'utf-8'), delimiter=',', quotechar='"')
            headers = next(words)
            for word in words:
                row_data = {key: value for key, value in zip(headers, word)}
                content.append(row_data)

    click.echo(f"Found {len(content)} words in Satori export, proceeding!")

    for word in content:
        add_note(
            word['Expression'],
            word['Expression-ReadingsOnly'],
            word['English'],
            word['Context1'],
            word['Context1-Translation'],
            "satori",
            deck
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
            click.echo(f"Found export link: {link.get('href')}")
            return link.get('href')  # first link correspond to latest export


@cli.command()
@click.argument('deck', default='Mining')
def sync_takoboto(deck):
    ankiConnectorUtils = AnkiConnectorUtils("http://localhost:8765")

    with suppressStream():
        notes = ankiConnectorUtils.makeRequest("findNotes", {
            "query": "deck:Takoboto"
        })

    with suppressStream():
        notesInfo = ankiConnectorUtils.makeRequest("notesInfo", {
            "notes": notes['result']
        })

    click.echo(f"Found {len(notesInfo['result'])} notes in Takotobo's deck, proceeding with importing...")

    for note in notesInfo['result']:
        word = note['fields']['Japanese']['value']
        reading = note['fields']['Reading']['value']
        glossary = note['fields']['Meaning']['value']
        sentence = note['fields']['Sentence']['value']
        sentenceEnglish = note['fields']['SentenceMeaning']['value']

        add_note(word, reading, glossary, sentence, sentenceEnglish, "takoboto", deck)


def add_note(word, reading, glossary, sentence, sentenceEnglish, tag, deck):
    ankiConnectorUtils = AnkiConnectorUtils(
        os.environ['ANKI_CONNECT_URL'] if
        os.environ['ANKI_CONNECT_URL'] else "http://localhost:8765"
    )

    with suppressStream():
        existingNote = ankiConnectorUtils.makeRequest("findNotes", {
            "query": f"deck:{deck} Word:{word}"
        })

    click.echo("----")

    if len(existingNote['result']) > 0:
        click.echo(f"{word}: Note exists, ignoring")
        return

    click.echo(f"{word}: downloading image from Google")
    picture = download_image_from_google(word)

    click.echo(f"{word}: downloading TTS for word")
    audio = text_to_wav("ja-JP-Wavenet-D", word)

    click.echo(f"{word}: downloading TTS for sentence: {sentence}")
    sentenceAudio = text_to_wav("ja-JP-Wavenet-D", sentence)

    notePayload = {
        "note": {
            "deckName": deck,
            "modelName": "JapaneseCard",
            "fields": {
                "Word": word,
                "Reading": reading,
                "Glossary": glossary,
                "Sentence": sentence,
                "Sentence-English": sentenceEnglish,
            },
            "options": {
                "allowDuplicate": True,
                "duplicateScope": "deck",
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
            "tags": [
                f"anki-tools-{tag}-{''.join(random.choice(string.ascii_uppercase + string.digits) for _ in range(6))}"
            ]
        }
    }

    if picture:
        notePayload['note']['picture'] = [{
            "data": base64.b64encode(picture.getvalue()).decode(),
            "filename": f"anki_tools_{word}.jpg",
            "fields": [
                "Picture"
            ]
        }]

    with suppressStream():
        response = ankiConnectorUtils.makeRequest("addNote", notePayload)

    if response["error"] is not None:
        click.echo(f"{word}: error creating note, Anki responded with: {response['error']}")
    else:
        click.echo(f"{word}: note created!")


def download_image_from_google(word):
    gis = GoogleImagesSearch(os.environ["GOOGLE_SEARCH_API_KEY"], os.environ["GOOGLE_SEARCH_CSE"])

    gis.search({'q': word, 'num': 3})

    foundImage = False
    img_byte_arr = None
    for image in gis.results():
        if foundImage:
            break

        try:
            imagePil = Image.open(BytesIO(image.get_raw_data()))

            imageResized = resizeimage.resizeimage.resize_height(imagePil, 300, False)

            img_byte_arr = io.BytesIO()
            imageResized.save(img_byte_arr, format='PNG')
        except PIL.UnidentifiedImageError:
            continue

        foundImage = True

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
