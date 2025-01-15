import time
import logging
import csv
import pdfplumber
import re
from os import path, remove, getenv
from datetime import datetime
from google.oauth2.credentials import Credentials
from google.oauth2.service_account import Credentials as SACredentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseDownload
from google_auth_oauthlib.flow import InstalledAppFlow

# Konfiguracja loggera
logging.basicConfig(level=logging.INFO)

# Ścieżki do plików
TOKEN_FILE = "auth/token.json"
CREDENTIALS_FILE = "auth/credentials.json"
KNOWN_FILES_FILE = "known_files.txt"
OUTPUT_CSV_FILE = "processed_files.csv"

# Zakresy dostępu dla Google Drive API
SCOPES = ['https://www.googleapis.com/auth/drive',
          ]

# ID folderu Google Drive do monitorowania (zmień na swoje ID)
INVOICE_FOLDER_ID = "1NfBtWj3_vDIVaUgIhLAGSyackntZ6JII"

def authenticate():
    """
    Uwierzytelnia użytkownika za pomocą OAuth 2.0 i zarządza tokenem.
    """
    if getenv("ENV") == "production":
        return SACredentials.from_service_account_file(
            "service_account_key.json", scopes=SCOPES
        )
    else:
        creds = None
        if path.exists(TOKEN_FILE):
            creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                except Exception as error:
                    logging.error(f"Nie udało się odświeżyć tokena. Ponowna autoryzacja wymagana:: {error}")
                    flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
                    creds = flow.run_local_server(port=0)
            else:
                flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
                creds = flow.run_local_server(port=0)

            # Zapisz odświeżony token lub nowy token do pliku
            with open(TOKEN_FILE, 'w') as token:
                token.write(creds.to_json())

        return creds


def load_known_files(file_path):
    """
    Ładuje znane ID plików z pliku tekstowego.
    """
    if path.exists(file_path):
        with open(file_path, 'r') as f:
            return set(line.strip() for line in f.readlines())
    return set()


def save_known_file(file_path, file_id):
    """
    Zapisuje nowe ID pliku do pliku tekstowego.
    """
    with open(file_path, 'a') as f:
        f.write(f"{file_id}\n")


def write_to_csv(file_path, file_data):
    """
    Zapisuje dane o pliku PDF do pliku CSV.
    """
    file_exists = path.exists(file_path)
    with open(file_path, 'a', newline='') as csvfile:
        writer = csv.writer(csvfile)
        # Jeśli plik CSV jeszcze nie istnieje, zapisz nagłówki
        if not file_exists:
            writer.writerow(["File Name", "File ID", "Processed Date"])
        # Zapisz dane pliku
        writer.writerow(file_data)


def list_new_pdfs(service, folder_id, known_files):
    """
    Pobiera listę nowych plików PDF w folderze Google Drive.
    """
    try:
        query = f"'{folder_id}' in parents and mimeType='application/pdf'"
        response = service.files().list(q=query, fields="files(id, name)").execute()

        new_files = []
        for file in response.get('files', []):
            if file['id'] not in known_files:
                new_files.append(file)
        return new_files
    except HttpError as error:
        logging.error(f"Błąd API: {error}")
        return []


def extract_invoice_data(pdf_path):
    """
    Ekstrakcja danych z pliku PDF (faktury).
    :param pdf_path: Ścieżka do lokalnego pliku PDF.
    :return: Słownik z wyekstrahowanymi danymi.
    """
    invoice_data = {
        "Amount To Pay": None,
    }

    try:
        # Otwieramy plik PDF
        with pdfplumber.open(pdf_path) as pdf:
            full_text = ""

            # Łączymy tekst ze wszystkich stron
            for page in pdf.pages:
                full_text += page.extract_text()

            # Szukamy danych za pomocą wyrażeń regularnych
            # Numer faktury (np. "FV-2023/1234")
            match = re.search(r"Pozostało do zapłaty[:\s]*\"([A-Z0-9-/,]+)\"", full_text, re.IGNORECASE)
            if match:
                invoice_data["Amount To Pay"] = match.group(1)

            # # Data faktury (np. "2024-01-01" lub "01.01.2024")
            # match = re.search(r"Data faktury[:\s]*([\d-]{10}|\d{2}\.\d{2}\.\d{4})", full_text, re.IGNORECASE)
            # if match:
            #     invoice_data["Invoice Date"] = match.group(1)
            #
            # # Kwota brutto (np. "Kwota brutto: 1234,56 zł")
            # match = re.search(r"Kwota brutto[:\s]*([\d,\.]+)\s*zł", full_text, re.IGNORECASE)
            # if match:
            #     invoice_data["Total Amount"] = match.group(1).replace(',', '.')
            #
            # # Nazwa kontrahenta (np. "Kontrahent: ABC Sp. z o.o.")
            # match = re.search(r"Kontrahent[:\s]*(.+)", full_text, re.IGNORECASE)
            # if match:
            #     invoice_data["Contractor Name"] = match.group(1).strip()

    except Exception as e:
        logging.error(f"Błąd podczas odczytu pliku PDF: {e}")

    return invoice_data


def download_file(service, file_id, destination):
    """
    Pobiera plik PDF z Google Drive i zapisuje go lokalnie.
    :param service: Google Drive API service.
    :param file_id: ID pliku na Google Drive.
    :param destination: Lokalna ścieżka do zapisu pliku.
    """
    try:
        request = service.files().get_media(fileId=file_id)
        with open(destination, 'wb') as f:
            downloader = MediaIoBaseDownload(f, request)
            done = False
            while not done:
                _, done = downloader.next_chunk()
    except HttpError as error:
        if error.resp.status == 403:
            logging.error(f"Brak dostępu do pliku: {file_id}. Upewnij się, że aplikacja ma odpowiednie uprawnienia.")
        else:
            logging.error(f"Błąd podczas pobierania pliku {file_id}: {error}")


def main():
    creds = authenticate()
    service = build('drive', 'v3', credentials=creds)

    # Załaduj znane pliki z pliku tekstowego
    known_files = load_known_files(KNOWN_FILES_FILE)

    logging.info("Rozpoczęto nasłuchiwanie folderu Google Drive...")
    try:
        while True:
            new_pdfs = list_new_pdfs(service, INVOICE_FOLDER_ID, known_files)
            for file in new_pdfs:
                file_name = file['name']
                file_id = file['id']
                processing_date = datetime.now().isoformat()
                logging.info(f"Wykryto nowy plik PDF: {file_name} (ID: {file_id})")

                # Pobierz plik PDF lokalnie
                local_path = f"./temp_{file_id}.pdf"
                download_file(service, file_id, local_path)

                # Wyciągnij dane z faktury
                invoice_data = extract_invoice_data(local_path)
                invoice_data["File Name"] = file_name
                invoice_data["File ID"] = file_id
                invoice_data["Processed Date"] = processing_date

                # Zapisz dane do pliku CSV
                write_to_csv(OUTPUT_CSV_FILE,invoice_data)

                # Dodaj plik do listy znanych plików
                known_files.add(file_id)
                save_known_file(KNOWN_FILES_FILE, file_id)

                # Usuń plik tymczasowy
                remove(local_path)

            # Odczekaj 30 sekund
            time.sleep(30)
    except KeyboardInterrupt:
        logging.info("Watcher zatrzymany.")


if __name__ == "__main__":
    main()
