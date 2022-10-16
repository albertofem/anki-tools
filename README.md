# anki-tools

Some tools to work with Anki. It includes:

- Ability to import saved words from Satori Reader
- Ability to import saved words in Takoboto dictionary

During the import, this tool will also download the following:

- A picture searching at Google Images
- TTS for the word
- TTS for the sentence (if any)

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