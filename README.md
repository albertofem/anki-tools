# anki-tools

Some tools to work with Anki. It includes:

- Ability to import saved words from Satori Reader
- Ability to import saved words in Takoboto dictionary

During the import, this tool will also download the following:

- A picture searching at Google Images
- TTS for the word
- TTS for the sentence (if any)

## Roadmap

- [x] Satori Reader import
- [x] Takotobo import
- [ ] Add missing pictures to notes
- [ ] Add missing sentence to notes, fetching from tatoeba
- [ ] Ability to pick a image from Google Search (via GUI)
- [ ] Ability to select TTS voice type
- [ ] Ability to add dictionary entries for notes from both bilingual and monolingual dictionaries
- [ ] Ability to clean up Yomichan entries (with messy Glossary entries)

## General requirements

You will need:

- Python3
- pip to install the dependencies (under `requirements.txt`)
- Google Cloud account, with a project and billing properly set
- Google TTS api enabled
- Google Search api enabled
- A Programmable Search Engine (https://programmablesearchengine.google.com/controlpanel/all)
- A Google Cloud API key with permissions to the Google Search API
- A Service Account and it's credentials (`.json` file), with access to the TTS api
- AnkiConnect plugin for Anki

And obviously:

- A Satori Reader account (no need to be subscriber)
- The Takoboto app and the ability to export to Anki (free in mobile versions)

## General configuration

A few environment variables are needed for this script to work. These are imported from a `.env` file. An example is provided in `.env.example`

- `GOOGLE_SEARCH_API_KEY`: corresponds to a Google Cloud API Key with access to the search API
- `GOOGLE_SEARCH_CSE`: correspond to a Google Programmable Search Engine ID
- `GOOGLE_APPLICATION_CREDENTIALS`: corresponds to a Google Cloud S2S JSON credentials file, with access to the TTS api
- `ANKI_CONNECT_URL`: your AnkiConnect URL. It's set by default to `http://localhost:8765`

## Note type / model

This program assumes that the following note type exists. It will create new cards following this model:

```
1: Word
2: Reading
3: Glossary
4: Sentence
5: Sentence-English
6: Picture
7: Audio
8: Sentence-Audio
9: Hint
10: DictionaryEntryBilingual
11: DictionaryEntryMonolingual
```

Fields `9`, `10` and `11` are not used for now, but will be used in the future for other tools.

## Satori Reader import

### Authentication

In order to authenticate in the Satori Reader service, you will need to provide the environment variable `SATORI_READER_SESSION`. This can be obtained by logging in into the website and then extract the Cookie `SessionToken={value}`. This value is the one you need to put into the environment variable.

### Importing cards

The command to import cards is:

```
python3 main.py sync-satori-reader
```

This command will trigger an export in your Satori Reader account and then download the .zip file, extract the .csv and import all of the cards into the target deck (default: `Mining`, use argument `--deck` to change).

An argument `--no-trigger` can be provided to not trigger an export and go directly to the existing ones.


## Takoboto import

In order to import cards from this dictionary, first export your list from the Android or iOS App (haven't tested on web since I'm not subscribed).

The tool will then take all of the cards imported into the `Takoboto` deck and import them into the target deck (default: `Mining`, use argument `--deck` to change)

The command to import cards is:

```
python3 main.py sync-satori-takoboto
```

## Filling Missing Audio

This function is used to fill in missing audio for notes in a deck. It does this by taking the following inputs:

* The name of the deck where the notes are located
* The name of the field with the sentence in Japanese
* The name of the field with the sentence audio

After you run the function, it will read every note in the specified deck and check if the field with the sentence audio is filled or not. If it is already filled, nothing will be done for that note. If it is not filled, the function will read the field with the sentence in Japanese, invoke Google TTS, and upload the audio into the sentence audio field.

This function is useful when you have a lot of notes in your deck that are missing sentence audio. It can save you time by automating the process of filling in the missing audio for you.

To run the function, use the following command:

```
python3 main.py fill-missing-audio --deck [name of the deck] --jp-field [name of the field with Japanese sentence] --audio-field [name of the field with audio]
```

For example, if you have a deck called "Vocabulary" with a field called "Sentence" for the Japanese sentence and a field called "Sentence-Audio" for the audio, you would run the following command:

```
python3 main.py fill-missing-audio --deck Vocabulary --jp-field Sentence --audio-field Sentence-Audio
```
