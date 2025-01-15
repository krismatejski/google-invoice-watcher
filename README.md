# google-invoice-watcher
This application is able to observe multiple invoice documents on Google Drive and intelligently parse their contents to store it in single Google Sheets file.

## Setup GCP

1. Login to Google Cloud Console
2. Create new project or choose existing one
3. Enable Google Drive API
   - Go to API & Services -> Library
   - Search for Google Drive API
   - Enable it
4. Create Confirmation Screen
   - Add test users
5. Create authentication data
   - Go to API & Services -> Authentication
   - Click _Create authentication data_
   - Choose _OAuth 2.0_
   - Choose _Computer Application_
   - Download JSON file with authentication data and save it in the project folder as _credentials.json_

## Setup Locally

1. Make sure you have python installed:
```bash 
python --version
```
Application was tested with Python 3.11.4
2. Make sure you have pip installed:
```bash 
pip --version
```
3. Install modules required by application:
```bash 
pip install -r requirements.txt
```
4. Run application:
```bash 
python main.py
```