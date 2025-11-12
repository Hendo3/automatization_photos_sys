
import logging
import json
import textwrap
import time
import shutil
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import fitz # PyMuPDF

# --- Configuração de Logging ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Definição de Caminhos (Paths) ---
BASE_DIR = Path(__file__).parent
FONT_DIR = BASE_DIR / "fonts"
PICTURE_DIR = BASE_DIR / "pictures" # PDFs de entrada (input_pdf_base) devem estar aqui
OUTPUT_DIR = BASE_DIR / "output"
TEMP_DIR = BASE_DIR / "temp_pdf_extract" # Pasta temporária
TEMPLATE_CONFIG_FILE = BASE_DIR / "templates.json"
PEDIDOS_FILE = BASE_DIR / "pedidos_pdf_duas_paginas.json" # O JSON correto

# Garante que os diretórios existem
OUTPUT_DIR.mkdir(exist_ok=True)
TEMP_DIR.mkdir(exist_ok=True) # Cria a pasta temporária

# --- Carregar Configuração de Templates ---
try:
    with open(TEMPLATE_CONFIG_FILE, 'r', encoding='utf-8') as f:
        TEMPLATES_CONFIG = json.load(f)
    logger.info(f"Carregados {len(TEMPLATES_CONFIG)} templates de '{TEMPLATE_CONFIG_FILE}'")
except Exception as e:
    logger.critical(f"ERRO CRÍTICO ao carregar 'templates.json': {e}")
    TEMPLATES_CONFIG = {}

# --- Funções Helper de Desenho (Copiadas do script antigo) ---
GLOBAL_DEFAULT_FONT = "sao.ttf" # Mude para sua fonte padrão

def get_font_line_height(font: ImageFont.FreeTypeFont) -> float:
    try:
        bbox = font.getbbox("Aghy")
        return (bbox[3] - bbox[1]) * 1.25
    except AttributeError:
        # Fallback
        mask = font.getmask("hg")
        return mask.size[1] * 1.25

def draw_templated_text(draw: ImageDraw.ImageDraw, config: dict, text_input: str, font_override: str | None = None):
    font_name_to_use = GLOBAL_DEFAULT_FONT
    if config.get('font_name'):
        font_name_to_use = config['font_name']
    if font_override:
        font_name_to_use = font_override
        
    font_path = FONT_DIR / font_name_to_use
    
    if not font_path.exists():
        logger.warning(f"Fonte '{font_name_to_use}' não encontrada. Usando fallback '{GLOBAL_DEFAULT_FONT}'.")
        font_path = FONT_DIR / GLOBAL_DEFAULT_FONT
        if not font_path.exists():
            raise FileNotFoundError(f"Fonte de fallback '{GLOBAL_DEFAULT_FONT}' não encontrada em {FONT_DIR}")

    font_size = config.get('font_size', 50)
    font = ImageFont.truetype(str(font_path), font_size)
    
    fill = config.get('color', '#000000')
    align = config.get('align', 'left')
    
    max_pixel_width = config.get('max_width_pixels', 9999) 
    lines = []
    words = text_input.split()
    current_line = ""

    for word in words:
        test_line = f"{current_line} {word}".strip()
        try:
            line_bbox = draw.textbbox((0,0), test_line, font=font)
            line_width = line_bbox[2] - line_bbox[0]
        except AttributeError:
            line_width = font.getlength(test_line)

        if line_width <= max_pixel_width:
            current_line = test_line
        else:
            lines.append(current_line)
            current_line = word
            
    lines.append(current_line)
    
    if 'max_lines' in config:
        lines = lines[:config['max_lines']]

    current_y = config.get('pos_y', 10) 
    line_height = get_font_line_height(font)

    for line in lines:
        try:
            line_bbox = draw.textbbox((0, 0), line, font=font)
            line_width = line_bbox[2] - line_bbox[0]
            line_top_offset = line_bbox[1]
        except AttributeError:
            try:
                bbox = font.getbbox(line)
                line_width = bbox[2] - bbox[0]
                line_top_offset = bbox[1]
            except AttributeError:
                mask = font.getmask(line)
                line_width, _ = mask.size
                line_top_offset = 0
        
        draw_x = config.get('pos_x', 10) 
        
        if align == "center":
            draw_x = config.get('pos_x', 10) + (max_pixel_width / 2) - (line_width / 2)
        elif align == "right":
            draw_x = config.get('pos_x', 10) + max_pixel_width - line_width
        
        draw.text(
            (draw_x, current_y - line_top_offset), 
            line, 
            font=font, 
            fill=fill
        )
        current_y += line_height
        
# --- Funções de Extração de PDF ---
def extrair_pagina_pdf_para_png(pdf_path: Path, page_number: int, output_png_path: Path, dpi: int = 300):
    """
    Extrai uma página específica de um PDF e a salva como PNG.
    page_number é 0-based (0 para a primeira página).
    """
    doc = None
    try:
        doc = fitz.open(pdf_path)
        if page_number >= len(doc):
            raise IndexError(f"PDF tem apenas {len(doc)} páginas. Não foi possível extrair a página {page_number + 1}.")
            
        page: fitz.Page = doc[page_number]
        
        # Define a matriz de renderização para DPI
        mat = fitz.Matrix(dpi / 72, dpi / 72)
        pix = page.get_pixmap(matrix=mat)
        
        pix.save(str(output_png_path))
        logger.debug(f"Página {page_number + 1} de '{pdf_path.name}' extraída para '{output_png_path.name}'")
        return output_png_path
    except Exception as e:
        logger.error(f"Erro ao extrair página {page_number + 1} de '{pdf_path.name}': {e}")
        return None
    finally:
        if doc:
            doc.close()

# --- Função Principal de Processamento ---
def processar_pedidos_pdf_duas_paginas():
    """
    Lê o 'pedidos_pdf_duas_paginas.json', extrai páginas de PDFs de entrada,
    modifica a frente e junta em novos PDFs.
    """
    
    try:
        with open(PEDIDOS_FILE, mode='r', encoding='utf-8') as f:
            pedidos_para_processar = json.load(f)
    except FileNotFoundError:
        logger.critical(f"ERRO: Arquivo de pedidos '{PEDIDOS_FILE}' não encontrado.")
        return
    except json.JSONDecodeError:
        logger.critical(f"ERRO: O arquivo '{PEDIDOS_FILE}' contém um JSON inválido (o // não é permitido).")
        return

    total_pedidos = len(pedidos_para_processar)
    sucesso_pedidos = 0
    logger.info(f"Encontrados {total_pedidos} pedidos em '{PEDIDOS_FILE}'. Iniciando processamento...")

    # Limpa a pasta temporária no início
    shutil.rmtree(TEMP_DIR, ignore_errors=True)
    TEMP_DIR.mkdir(exist_ok=True)
    logger.info(f"Pasta temporária '{TEMP_DIR.name}' limpa.")

    for i, pedido in enumerate(pedidos_para_processar):
        output_pdf_name = pedido.get('output_pdf')
        input_pdf_base_name = pedido.get('input_pdf_base')
        pagina_frente_config = pedido.get('pagina_frente')
        
        if not output_pdf_name or not input_pdf_base_name or not pagina_frente_config:
            logger.warning(f"Pulando pedido {i+1} (JSON mal formatado: 'output_pdf', 'input_pdf_base' ou 'pagina_frente' faltando).")
            continue
            
        logger.info(f"Processando Pedido {i+1}/{total_pedidos}: '{output_pdf_name}' (Base: {input_pdf_base_name})...")
        
        input_pdf_path = PICTURE_DIR / input_pdf_base_name
        if not input_pdf_path.exists():
            logger.error(f"  -> ERRO: PDF de entrada '{input_pdf_base_name}' não encontrado em '{PICTURE_DIR}'.")
            continue

        temp_front_png = TEMP_DIR / f"temp_{i}_front.png"
        temp_back_png = TEMP_DIR / f"temp_{i}_back.png"
        
        try:
            # 1. Extrair a primeira página (frente)
            extracted_front_path = extrair_pagina_pdf_para_png(input_pdf_path, 0, temp_front_png)
            if not extracted_front_path:
                raise Exception("Falha ao extrair página da frente.")

            # 2. Extrair a segunda página (traseira)
            extracted_back_path = extrair_pagina_pdf_para_png(input_pdf_path, 1, temp_back_png)
            if not extracted_back_path:
                raise Exception("Falha ao extrair página de trás.")
            
            # 3. Aplicar o texto à página da frente
            template_name = pagina_frente_config.get('template_imagem')
            texto_frente = pagina_frente_config.get('texto')
            fonte_override_frente = pagina_frente_config.get('fonte')

            if not template_name or texto_frente is None:
                logger.error(f"  -> ERRO: Configuração incompleta para a página da frente do PDF '{output_pdf_name}'.")
                raise Exception("Configuração de página da frente incompleta.")
            
            if template_name not in TEMPLATES_CONFIG:
                logger.error(f"  -> ERRO: Template '{template_name}' não encontrado em templates.json para a página da frente.")
                raise FileNotFoundError(f"Template '{template_name}' não definido.")
            
            config = TEMPLATES_CONFIG[template_name]
            
            img_frente = Image.open(extracted_front_path)
            img_frente = img_frente.convert("RGBA") # Converte para RGBA para desenhar
            draw = ImageDraw.Draw(img_frente)
            
            draw_templated_text(draw, config, texto_frente, fonte_override_frente)
            
            # Converte de volta para RGB para salvar em PDF
            img_frente_modificada = img_frente.convert("RGB")
            logger.info(f"  -> Página da frente de '{output_pdf_name}' modificada com texto.")

            # 4. Carregar a página traseira inalterada
            img_traseira = Image.open(extracted_back_path)
            img_traseira_rgb = img_traseira.convert("RGB") # Garante RGB
            logger.info(f"  -> Página traseira de '{output_pdf_name}' carregada (inalterada).")

            # 5. Juntar as duas imagens em um novo PDF
            output_pdf_path = OUTPUT_DIR / output_pdf_name
            
            img_frente_modificada.save(
                output_pdf_path,
                "PDF",
                resolution=300.0, # Mantém a resolução alta
                save_all=True,
                append_images=[img_traseira_rgb] # Anexa a página traseira
            )
            
            logger.info(f"SUCESSO: PDF '{output_pdf_name}' salvo em {output_pdf_path}")
            sucesso_pedidos += 1

        except Exception as e:
            logger.error(f"FALHA ao processar '{output_pdf_name}': {e}")
        finally:
            # Limpa os arquivos PNG temporários
            if temp_front_png.exists(): temp_front_png.unlink()
            if temp_back_png.exists(): temp_back_png.unlink()
            logger.debug(f"Arquivos temporários para '{output_pdf_name}' limpos.")

    # Limpa a pasta temporária no final
    shutil.rmtree(TEMP_DIR, ignore_errors=True)
    
    logging.info("--- Processamento em Lote Concluído ---")
    logging.info(f"Total de pedidos PDF processados: {total_pedidos}")
    logging.info(f"Gerados com sucesso: {sucesso_pedidos}")
    logging.info(f"Pedidos com falha: {total_pedidos - sucesso_pedidos}")

# --- Ponto de Entrada Principal ---
if __name__ == "__main__":
    start_time = time.time()
    processar_pedidos_pdf_duas_paginas()
    end_time = time.time()
    logger.info(f"Tempo total de execução: {end_time - start_time:.2f} segundos.")