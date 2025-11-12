import csv
import requests
import time
import logging
import gspread # (Usando Google Sheets, que é melhor que CSV)
import pandas as pd
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
import io
from pathlib import Path

# --- Configuração ---
API_URL = "http://127.0.0.1:8000/gerar-imagem/"
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- CONFIGURAÇÃO GOOGLE DRIVE ---
# Coloque o 'credentials.json' baixado do GCP na raiz do projeto
SERVICE_ACCOUNT_FILE = 'credentials.json' 
SCOPES = [
    'https://www.googleapis.com/auth/drive',
    'https://www.googleapis.com/auth/spreadsheets'
]

# IDs das suas pastas/arquivos no Drive (pegue da URL)
#quero que seja local mesmo
SHEET_ID = "1VlaC138lFNi3oPtIOdrLOy52uvNxbIcpxjZt2h0-W90"

DRIVE_IMAGE_FOLDER_ID = '1ZjGtJBxfa55_ujA8-SwZr-fKnUkFpor5'
DRIVE_FONTS_FOLDER_ID = '1ne5wOp1rlS3mNOxitWpmVcBFBXaZzuBa'

# Caminhos locais
BASE_DIR = Path(__file__).parent
PICTURE_DIR = BASE_DIR / "pictures"
FONT_DIR = BASE_DIR / "fonts"
PICTURE_DIR.mkdir(exist_ok=True)
FONT_DIR.mkdir(exist_ok=True)

# --- Funções de Autenticação e Download ---

def get_gdrive_service():
    """Autentica e retorna os 'services' para Drive e Sheets."""
    creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
    drive_service = build('drive', 'v3', credentials=creds)
    sheets_client = gspread.authorize(creds)
    return drive_service, sheets_client

def download_files_from_folder(service, folder_id, local_dest_path):
    """Baixa todos os arquivos de uma pasta do Drive para um destino local."""
    logging.info(f"Sincronizando pasta {folder_id} para {local_dest_path}...")
    
    query = f"'{folder_id}' in parents and trashed = false"
    results = service.files().list(q=query, fields="files(id, name)").execute()
    items = results.get('files', [])

    if not items:
        logging.warning(f"Nenhum arquivo encontrado na pasta do Drive: {folder_id}")
        return

    for item in items:
        file_id = item['id']
        file_name = item['name']
        local_file_path = local_dest_path / file_name
        
        # Simples verificação de cache: não baixa se o arquivo já existir
        if local_file_path.exists():
            # logging.info(f"Arquivo '{file_name}' já existe localmente. Pulando.")
            continue
            
        logging.info(f"Baixando '{file_name}'...")
        request = service.files().get_media(fileId=file_id)
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        
        done = False
        while done is False:
            status, done = downloader.next_chunk()
            # logging.info(f"Download {file_name}: {int(status.progress() * 100)}%")
        
        # Salva o arquivo em disco
        with open(local_file_path, 'wb') as f:
            f.write(fh.getbuffer())

def get_orders_from_sheet(client, sheet_id):
    """Lê a planilha de pedidos e retorna uma lista de dicionários."""
    logging.info(f"Buscando pedidos da Planilha Google: {sheet_id}")
    try:
        sheet = client.open_by_key(sheet_id).sheet1 # Pega a primeira aba
        # Converte para um DataFrame do Pandas e depois para dict
        data = pd.DataFrame(sheet.get_all_records())
        # Garante que as colunas tenham os nomes corretos
        data = data.rename(columns={
            'ID do Pedido': 'order_id',
            'Template': 'template_image',
            'Nome no Produto': 'text_to_add'
        })
        return data.to_dict('records') # Retorna lista de dicts
    except Exception as e:
        logging.error(f"Não foi possível ler a planilha: {e}")
        return []

def processar_lote_local(pedidos: list):
    """(Esta é a função antiga) Envia os requests para a API local."""
    
    total_pedidos = len(pedidos)
    sucesso_pedidos = 0
    
    for row in pedidos:
        order_id = row.get('order_id')
        template_image = row.get('template_image')
        text_to_add = row.get('text_to_add')

        if not all([order_id, template_image, text_to_add]):
            logging.warning(f"Pulando linha mal formatada: {row}")
            continue

        payload = {
            "order_id": str(order_id), # Garante que seja string
            "template_image": template_image,
            "text_to_add": text_to_add
        }
        
        logging.info(f"Enviando Pedido: {order_id} (Template: {template_image})...")
        
        try:
            response = requests.post(API_URL, json=payload, timeout=20) # Timeout maior
            
            if response.status_code == 200:
                logging.info(f"SUCESSO: Pedido {order_id} gerado.")
                sucesso_pedidos += 1
            else:
                logging.error(f"FALHA: Pedido {order_id}. API retornou {response.status_code}. Detalhe: {response.text}")
        
        except requests.exceptions.ConnectionError:
            logging.critical("FALHA DE CONEXÃO: A API (main/test.py) parece estar offline. Abortando.")
            return
        except requests.exceptions.Timeout:
            logging.error(f"FALHA: Pedido {order_id} sofreu Timeout.")
        
        time.sleep(0.05) # Pausa curta

    logging.info("--- Processamento em Lote Concluído ---")
    logging.info(f"Total de pedidos lidos: {total_pedidos}")
    logging.info(f"Pedidos gerados com sucesso: {sucesso_pedidos}")
    logging.info(f"Pedidos com falha: {total_pedidos - sucesso_pedidos}")


# --- Ponto de Entrada Principal ---
if __name__ == "__main__":
    try:
        # FASE 1: Sincronização
        logging.info("Iniciando autenticação com Google API...")
        drive_service, sheets_client = get_gdrive_service()
        
        download_files_from_folder(drive_service, DRIVE_IMAGE_FOLDER_ID, PICTURE_DIR)
        download_files_from_folder(drive_service, DRIVE_FONTS_FOLDER_ID, FONT_DIR)
        
        pedidos = get_orders_from_sheet(sheets_client, SHEET_ID)
        
        if not pedidos:
            logging.info("Nenhum pedido encontrado na planilha. Encerrando.")
        else:
            # FASE 2: Processamento
            logging.info(f"Encontrados {len(pedidos)} pedidos. Iniciando processamento local...")
            processar_lote_local(pedidos)
            
    except FileNotFoundError:
        logging.critical(f"ERRO: Arquivo de credenciais '{SERVICE_ACCOUNT_FILE}' não encontrado.")
        logging.critical("Faça o download da chave da Conta de Serviço no Google Cloud Platform e salve-a na raiz do projeto.")
    except Exception as e:
        logging.critical(f"Um erro inesperado ocorreu: {e}")