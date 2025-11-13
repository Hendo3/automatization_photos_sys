import requests
import time
import logging
import json  # Importa o módulo JSON
from pathlib import Path

# --- Configuração ---
API_URL = "http://127.0.0.1:8000/gerar-imagem/" 
JSON_FILE = Path(__file__).parent / "main" / "pedidos_lote.json" # <-- MUDANÇA AQUI
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def processar_lote_local_json():
    """Lê o JSON local e envia cada objeto como um request para a API."""
    
    try:
        with open(JSON_FILE, mode='r', encoding='utf-8') as f:
            pedidos_para_enviar = json.load(f) # <-- MUDANÇA AQUI
            
            total_pedidos = len(pedidos_para_enviar)
            sucesso_pedidos = 0
            
            if total_pedidos == 0:
                logging.warning(f"Arquivo '{JSON_FILE}' está vazio. Nenhum pedido para processar.")
                return

            logging.info(f"Encontrados {total_pedidos} pedidos em '{JSON_FILE}'. Iniciando processamento...")

            for i, row in enumerate(pedidos_para_enviar):
                
                # --- Mapeamento das chaves do JSON para a API ---
                order_id = row.get('ID')
                template_image = row.get('imagem')
                text_to_add = row.get('texto')
                font_override = row.get('fonte') # Pode ser None, "" ou um nome de fonte
                # --- Fim do Mapeamento ---

                if not all([order_id, template_image, text_to_add]):
                    logging.warning(f"Pulando pedido {i+1} (ID, imagem ou texto faltando): {row}")
                    continue

                # Monta o payload (JSON) para a API
                payload = {
                    "order_id": order_id,
                    "template_image": template_image,
                    "text_to_add": text_to_add
                }
                
                # Só adiciona o override se ele tiver um valor (não for None ou "")
                if font_override:
                    payload['font_override'] = font_override
                    logging.info(f"  -> (Usando font override: {font_override})")

                logging.info(f"Enviando Pedido {i+1}/{total_pedidos}: {order_id} (Template: {template_image})...")
                
                try:
                    # Dispara o request para a API local
                    response = requests.post(API_URL, json=payload, timeout=20)
                    
                    if response.status_code == 200:
                        logging.info(f"SUCESSO: Pedido {order_id} gerado.")
                        sucesso_pedidos += 1
                    else:
                        logging.error(f"FALHA: Pedido {order_id}. API retornou {response.status_code}. Detalhe: {response.text}")
                
                except requests.exceptions.ConnectionError:
                    logging.critical(f"FALHA DE CONEXÃO: A API (main/test.py) não está rodando em {API_URL}. Abortando.")
                    return
                except requests.exceptions.Timeout:
                    logging.error(f"FALHA: Pedido {order_id} sofreu Timeout.")
                
                time.sleep(0.05)

            logging.info("--- Processamento em Lote Concluído ---")
            logging.info(f"Total de pedidos lidos: {total_pedidos}")
            logging.info(f"Pedidos gerados com sucesso: {sucesso_pedidos}")
            logging.info(f"Pedidos com falha: {total_pedidos - sucesso_pedidos}")

    except FileNotFoundError:
        logging.critical(f"ERRO: Arquivo de lote '{JSON_FILE}' não encontrado.")
    except json.JSONDecodeError:
        logging.critical(f"ERRO: O arquivo '{JSON_FILE}' contém um JSON inválido (mal formatado).")
    except Exception as e:
        logging.critical(f"Um erro inesperado ocorreu: {e}")

if __name__ == "__main__":
    processar_lote_local_json()