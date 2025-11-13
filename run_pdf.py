import logging
import json
import textwrap
import time
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

# --- Configuração de Logging ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Definição de Caminhos (Paths) ---
BASE_DIR = Path(__file__).parent
FONT_DIR = BASE_DIR / "fonts"
PICTURE_DIR = BASE_DIR / "pictures"
OUTPUT_DIR = BASE_DIR / "output"
TEMPLATE_CONFIG_FILE = BASE_DIR / "templates.json"
PEDIDOS_FILE = BASE_DIR / "main" / "pedidos_lote.json" # <-- O NOVO ARQUIVO DE PEDIDOS

# Garante que o diretório de output existe
OUTPUT_DIR.mkdir(exist_ok=True)

# --- Carregar Configuração de Templates ---
try:
    with open(TEMPLATE_CONFIG_FILE, 'r', encoding='utf-8') as f:
        TEMPLATES_CONFIG = json.load(f)
    logger.info(f"Carregados {len(TEMPLATES_CONFIG)} templates de '{TEMPLATE_CONFIG_FILE}'")
except Exception as e:
    logger.critical(f"ERRO CRÍTICO ao carregar 'templates.json': {e}")
    TEMPLATES_CONFIG = {}

# --- Funções Helper de Desenho (Copiadas do 'main/test.py') ---
GLOBAL_DEFAULT_FONT = "sao.ttf" # Mude para sua fonte padrão (ex: Arial.ttf)

def get_font_line_height(font: ImageFont.FreeTypeFont) -> float:
    try:
        bbox = font.getbbox("Aghy")
        return (bbox[3] - bbox[1]) * 1.25
    except AttributeError:
        return font.getsize("hg")[1] * 1.25

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
    
    max_pixel_width = config.get('max_width_pixels', 9999) # Fallback para largura "infinita"
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

    current_y = config.get('pos_y', 10) # Fallback de posição Y
    line_height = get_font_line_height(font)

    for line in lines:
        try:
            line_bbox = draw.textbbox((0, 0), line, font=font)
            line_width = line_bbox[2] - line_bbox[0]
            line_top_offset = line_bbox[1]
        except AttributeError:
            line_bbox = (0, 0, font.getlength(line), font.getsize(line)[1])
            line_width = line_bbox[2]
            line_top_offset = 0
        
        draw_x = config.get('pos_x', 10) # Fallback de posição X
        
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
        
# --- Função Principal de Processamento de PDF ---

def processar_lote_pdf():
    """Lê o 'pedidos_para_pdf.json', gera e junta as imagens em PDFs."""
    
    try:
        with open(PEDIDOS_FILE, mode='r', encoding='utf-8') as f:
            pedidos_para_processar = json.load(f)
    except FileNotFoundError:
        logger.critical(f"ERRO: Arquivo de pedidos '{PEDIDOS_FILE}' não encontrado.")
        return
    except json.JSONDecodeError:
        logger.critical(f"ERRO: O arquivo '{PEDIDOS_FILE}' contém um JSON inválido.")
        return

    total_pedidos = len(pedidos_para_processar)
    sucesso_pedidos = 0
    logger.info(f"Encontrados {total_pedidos} pedidos em '{PEDIDOS_FILE}'. Iniciando processamento...")

    for i, pedido in enumerate(pedidos_para_processar):
        pdf_output_name = pedido.get('output_pdf')
        paginas_info = pedido.get('paginas')
        
        if not pdf_output_name or not paginas_info:
            logger.warning(f"Pulando pedido {i+1} (JSON mal formatado: 'output_pdf' or 'paginas' faltando).")
            continue
            
        output_path = OUTPUT_DIR / pdf_output_name
        imagens_em_memoria = [] # Lista para guardar as imagens prontas

        logger.info(f"Processando Pedido {i+1}/{total_pedidos}: '{pdf_output_name}'...")
        
        try:
            # --- Gera cada página em memória ---
            for j, pagina in enumerate(paginas_info):
                template_name = pagina.get('imagem')
                texto = pagina.get('texto')
                fonte_override = pagina.get('fonte')
                
                if not template_name or texto is None: # Permite texto ""
                    logger.warning(f"  -> Pulando Página {j+1} (imagem ou texto faltando).")
                    continue
                
                # Encontra a config do template
                if template_name not in TEMPLATES_CONFIG:
                    logger.error(f"  -> ERRO Página {j+1}: Template '{template_name}' não encontrado em templates.json.")
                    raise FileNotFoundError(f"Template '{template_name}' não definido.")
                
                config = TEMPLATES_CONFIG[template_name]
                
                # Abre a imagem base
                image_path = PICTURE_DIR / template_name
                if not image_path.exists():
                    logger.error(f"  -> ERRO Página {j+1}: Imagem base '{template_name}' não encontrada em /pictures.")
                    raise FileNotFoundError(f"Imagem base '{template_name}' não encontrada.")
                
                img = Image.open(image_path)
                img = img.convert("RGBA")
                draw = ImageDraw.Draw(img)
                
                # Desenha o texto
                draw_templated_text(draw, config, texto, fonte_override)
                
                # Converte para RGB (necessário para salvar em PDF)
                img = img.convert("RGB")
                imagens_em_memoria.append(img)
                logger.info(f"  -> Página {j+1} ('{template_name}') gerada.")

            # --- Salva o PDF ---
            if not imagens_em_memoria:
                logger.warning(f"Nenhuma página foi gerada para '{pdf_output_name}'. PDF não será salvo.")
                continue

            # Pega a primeira imagem
            img1 = imagens_em_memoria[0]
            # Pega o resto (se houver)
            outras_imgs = imagens_em_memoria[1:]
            
            img1.save(
                output_path,
                "PDF",
                resolution=100.0,
                save_all=True,
                append_images=outras_imgs
            )
            
            logger.info(f"SUCESSO: Pedido '{pdf_output_name}' salvo em {output_path}")
            sucesso_pedidos += 1

        except Exception as e:
            logger.error(f"FALHA ao processar '{pdf_output_name}': {e}")
        finally:
            # Limpa as imagens da memória
            for img in imagens_em_memoria:
                img.close()

    logging.info("--- Processamento em Lote Concluído ---")
    logging.info(f"Total de pedidos PDF: {total_pedidos}")
    logging.info(f"Gerados com sucesso: {sucesso_pedidos}")
    logging.info(f"Pedidos com falha: {total_pedidos - sucesso_pedidos}")

# --- Ponto de Entrada Principal ---
if __name__ == "__main__":
    start_time = time.time()
    processar_lote_pdf()
    end_time = time.time()
    logger.info(f"Tempo total de execução: {end_time - start_time:.2f} segundos.")