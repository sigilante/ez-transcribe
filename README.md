# EZ-Transcribe

A simple tool for transcribing documents into plaintext.

Released by the [Illinois Deseret Consortium](http://faculty.las.illinois.edu/rshosted/deseret.html) under the MIT License.

![](./img/hero.webp)

## Features

* Specify repositories to transcribe from
* TOML-based page annotation
* Auto-saved progress

![](./img/image.png)

## Usage

1. Install the required dependencies:

   ```bash
   cd src
   pip install -r requirements.txt
   ```

2. Run the application:

   ```bash
   uvicorn transcribe:app --reload
   ```

3. Open your web browser and navigate to `http://localhost:8000/select` to select a repository and start transcribing.

You will need to specify the repository directory if this is your first time running the application.  You will also want to populate the `documents.json` file with metadata about the documents you will be transcribing.  (This is presumptively configured for IDC corpus transcription work with the Deseret Alphabet.)

You will also need to manually sync your source repository with GitHub.

## Example

A transcription looks like this:

```txt
===HEADER===
Details about the document and its source.
===END HEADER===
+++
page = "1"
scan = 1
notes = "blank page"
<<<>>>
+++
page = "2"
scan = 2
+++
This is the text of the second page.
<<<>>>
```
