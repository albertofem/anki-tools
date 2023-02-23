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
import hashlib

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

unique_suffix = ''.join(random.choice(string.ascii_uppercase + string.digits) for _ in range(6))


@click.group()
def cli():
    pass


@cli.command()
@click.option('--no-trigger', is_flag=True, show_default=True, default=False,
              help='Do not trigger a Satori Reader export')
@click.option('--wait-time', type=int, default=60,
              help='Amount of time (in seconds) to wait for the Satori export to finish')
@click.argument('deck', default='Mining')
def sync_satori_reader(no_trigger, deck, wait_time):
    if no_trigger is False:
        click.echo("Triggering Anki export in Satori reader...")
        export_satori_reader()
        click.echo(f"Waiting {wait_time} seconds for export to finish...")
        time.sleep(wait_time)

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


def export_satori_reader():
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


@cli.command()
@click.argument('deck', default='Grammar')
@click.argument('sentence_field', default='Sentence')
@click.argument('sentence_audio_field', default='Sentence-Audio')
def fill_missing_audio(deck, sentence_field, sentence_audio_field):
    ankiConnectorUtils = AnkiConnectorUtils(
        os.environ['ANKI_CONNECT_URL'] if
        os.environ['ANKI_CONNECT_URL'] else "http://localhost:8765"
    )

    with suppressStream():
        notes = ankiConnectorUtils.makeRequest("findNotes", {
            "query": f"deck:{deck}"
        })

    with suppressStream():
        notesInfo = ankiConnectorUtils.makeRequest("notesInfo", {
            "notes": notes['result']
        })

    click.echo(f"Found {len(notesInfo['result'])} notes in {deck}, proceeding with checking audio...")

    for note in notesInfo['result']:
        sentence_audio = note['fields'][sentence_audio_field]['value']
        if sentence_audio:
            continue

        sentence_jp = note['fields'][sentence_field]['value']
        sentence_jp = BeautifulSoup(sentence_jp, 'html.parser').get_text()
        sentence_jp = sentence_jp.replace('\xa0', '').replace('\n', '').strip()

        click.echo(f"Generating audio for '{sentence_jp}'")
        sentence_audio = text_to_wav("ja-JP-Wavenet-D", sentence_jp)

        click.echo(f"Uploading audio to field '{sentence_audio_field}' with note id: '{note['noteId']}'")

        audio_filename = f"anki_tools_{hashlib.md5(sentence_jp.encode('utf-8')).hexdigest()}.wav"

        with suppressStream():
            ankiConnectorUtils.makeRequest("guiBrowse", {
                "query": "nid:1",
            })

            ankiConnectorUtils.makeRequest("updateNoteFields", {
                "note": {
                    "id": note['noteId'],
                    "fields": {
                        sentence_audio_field: ""
                    },
                    "audio": [
                        {
                            "data": base64.b64encode(sentence_audio).decode(),
                            "filename": audio_filename,
                            "fields": [
                                sentence_audio_field
                            ]
                        }
                    ]
                },
            })

            ankiConnectorUtils.makeRequest("guiBrowse", {
                "query": f"nid:{note['noteId']}",
            })

    click.echo("Done!")
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
                f"anki-tools-{tag}-{unique_suffix}"
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
            imageResized.convert('RGB').save(img_byte_arr, format='PNG', optimize=True)
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
