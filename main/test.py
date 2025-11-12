import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from PIL import Image, ImageDraw, ImageFont
from pathlib import Path
import logging
import json
import textwrap

# --- Configuração de Logging ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Definição de Caminhos (Paths) ---
BASE_DIR = Path(__file__).parent.parent
FONT_DIR = BASE_DIR / "fonts"
PICTURE_DIR = BASE_DIR / "pictures"
OUTPUT_DIR = BASE_DIR / "output"
TEMPLATE_CONFIG_FILE = BASE_DIR / "templates.json"  # <-- NOVO

# Garante que o diretório de output existe
OUTPUT_DIR.mkdir(exist_ok=True)

# --- Carregar Configuração de Templates ---
try:
    with open(TEMPLATE_CONFIG_FILE, 'r', encoding='utf-8') as f:
        TEMPLATES_CONFIG = json.load(f)
    logger.info(f"Carregados {len(TEMPLATES_CONFIG)} templates de '{TEMPLATE_CONFIG_FILE}'")
except FileNotFoundError:
    logger.error(f"ERRO CRÍTICO: 'templates.json' não encontrado em {TEMPLATE_CONFIG_FILE}")
    TEMPLATES_CONFIG = {}
except json.JSONDecodeError:
    logger.error(f"ERRO CRÍTICO: 'templates.json' está mal formatado.")
    TEMPLATES_CONFIG = {}


# --- Inicialização da API ---
app = FastAPI(
    title="API de Customização de Imagens",
    description="Uma API para adicionar texto a imagens de template."
)

# --- Modelo de Dados (Payload da Requisição) ---
# MUITO MAIS SIMPLES!
# O chamador da API não precisa mais saber de design.
class PedidoRequest(BaseModel):
    order_id: str
    template_image: str   # Ex: "Robot-girl.jpg" (Esta é a nossa "chave")
    text_to_add: str      # Ex: "Cyberdeck v2.1"
    font_override: str | None = None  # Opcional: Permite sobrescrever a fonte do template

# --- Funções Helper de Desenho ---

GLOBAL_DEFAULT_FONT = "sao.ttf"

def get_font_line_height(font: ImageFont.FreeTypeFont) -> float:
    """Calcula a altura 'real' de uma linha para espaçamento."""
    try:
        # Bbox de texto comum
        bbox = font.getbbox("Aghy")
        return (bbox[3] - bbox[1]) * 1.25 # Adiciona 25% de espaçamento
    except AttributeError:
        # Fallback para versões do Pillow sem getbbox: usa getmetrics quando disponível
        try:
            ascent, descent = font.getmetrics()
            return (ascent + descent) * 1.25
        except Exception:
            # Último recurso: estimativa baseada no mask do texto
            return font.getmask("hg").size[1] * 1.25

def draw_templated_text(draw: ImageDraw.ImageDraw, config: dict, text_input: str, font_override: str | None = None):
    """
    Função "mestra" que usa a configuração do templates.json
    para desenhar o texto corretamente, com alinhamento e quebra de linha.
    
    Agora aceita um 'font_override' para sobrepor o template.
    """
    
    # --- Lógica da Fonte (Fonte X vs. Placeholder) ---
    
    # 1. O 'font_override' (Fonte X) tem a maior prioridade.
    # 2. Se não, usa a fonte do 'templates.json'.
    # 3. Se o template não tiver fonte, usa o GLOBAL_DEFAULT_FONT (Placeholder).
    
    font_name_to_use = GLOBAL_DEFAULT_FONT # Começa com o placeholder
    if config.get('font_name'):
        font_name_to_use = config['font_name'] # Prioriza o template
    if font_override:
        font_name_to_use = font_override # Prioridade máxima é o override
        
    font_path = FONT_DIR / font_name_to_use
    
    # Fallback final: se a fonte escolhida não existir, tenta o global default
    if not font_path.exists():
        logging.warning(f"Fonte '{font_name_to_use}' não encontrada. Usando fallback '{GLOBAL_DEFAULT_FONT}'.")
        font_path = FONT_DIR / GLOBAL_DEFAULT_FONT
        if not font_path.exists():
             # Se nem o fallback existir, falha
            raise FileNotFoundError(f"Fonte de fallback '{GLOBAL_DEFAULT_FONT}' não encontrada em {FONT_DIR}")

    # Carrega a fonte que foi decidida
    font_size = config.get('font_size', 50) # Adiciona um fallback de tamanho
    font = ImageFont.truetype(str(font_path), font_size)
    
    fill = config.get('color', '#000000') # Adiciona fallback de cor
    align = config.get('align', 'left')    
    fill = config['color']
    align = config.get('align', 'left')
    
    # --- 1. Lógica de Quebra de Linha (Wrapper) ---
    # Esta é uma lógica de quebra de linha baseada em *pixels* (max_width_pixels)
    # É mais precisa que a baseada em caracteres.
    
    max_pixel_width = config['max_width_pixels']
    lines = []
    
    # Quebra o texto de entrada em palavras
    words = text_input.split()
    current_line = ""

    for word in words:
        # Testa se a palavra cabe na linha atual
        test_line = f"{current_line} {word}".strip()
        try:
            line_bbox = draw.textbbox((0,0), test_line, font=font)
            line_width = line_bbox[2] - line_bbox[0]
        except AttributeError:
            line_width = font.getlength(test_line)

        if line_width <= max_pixel_width:
            # Palavra cabe, adiciona à linha
            current_line = test_line
        else:
            # Palavra não cabe, "fecha" a linha anterior
            lines.append(current_line)
            # A nova palavra começa uma nova linha
            current_line = word
            
    lines.append(current_line) # Adiciona a última linha
    
    # Limita o número de linhas (se definido no config)
    if 'max_lines' in config:
        lines = lines[:config['max_lines']]

    # --- 2. Lógica de Desenho e Alinhamento (Linha por Linha) ---
    current_y = config['pos_y']
    line_height = get_font_line_height(font)

    for line in lines:
        try:
            line_bbox = draw.textbbox((0, 0), line, font=font)
            line_width = line_bbox[2] - line_bbox[0]
            line_top_offset = line_bbox[1] # Offset vertical da própria fonte
        except AttributeError:
            line_bbox = font.getbbox(line)
            line_width = line_bbox[2] - line_bbox[0]
            line_top_offset = line_bbox[1]

        
        draw_x = config['pos_x']
        
        if align == "center":
            draw_x = config['pos_x'] + (max_pixel_width / 2) - (line_width / 2)
        elif align == "right":
            draw_x = config['pos_x'] + max_pixel_width - line_width
        
        # Desenha a linha atual
        draw.text(
            (draw_x, current_y - line_top_offset), 
            line, 
            font=font, 
            fill=fill
        )
        
        # Move o 'cursor' para a próxima linha
        current_y += line_height


# --- O Endpoint da API (Atualizado) ---
@app.post("/gerar-imagem/")
async def gerar_imagem_customizada(pedido: PedidoRequest):
    """
    Recebe um pedido, encontra o template correspondente no JSON,
    e desenha o texto na imagem.
    """
    logger.info(f"Recebido pedido {pedido.order_id} para template {pedido.template_image}")

    # 1. Encontrar a configuração do template
    if pedido.template_image not in TEMPLATES_CONFIG:
        logger.error(f"Template '{pedido.template_image}' não encontrado em templates.json")
        raise HTTPException(status_code=404, detail=f"Configuração de template '{pedido.template_image}' não encontrada.")
    
    config = TEMPLATES_CONFIG[pedido.template_image]

    # 2. Montar e validar os caminhos dos arquivos
    image_path = PICTURE_DIR / pedido.template_image
    
    # O nome da fonte agora vem do 'config'
    font_path = FONT_DIR / config['font_name'] 
    
    # Se houver override de fonte no pedido, aplica
    pedido.font_override
    
    output_filename = f"{pedido.order_id}_{pedido.template_image}.png" # Força PNG
    output_path = OUTPUT_DIR / output_filename

    if not image_path.exists():
        logger.error(f"Arquivo de template não encontrado: {image_path}")
        raise HTTPException(status_code=404, detail=f"Imagem template '{pedido.template_image}' não encontrada.")
        
    if not font_path.exists():
        logger.error(f"Arquivo de fonte não encontrado: {font_path}")
        raise HTTPException(status_code=404, detail=f"Fonte '{config['font_name']}' (definida no template) não encontrada.")

    # 3. Processamento da Imagem (Pillow)
    try:
        with Image.open(image_path) as img:
            img = img.convert("RGBA")
            draw = ImageDraw.Draw(img)
            
            # 4. CHAMA A NOVA FUNÇÃO HELPER
            # A mágica acontece aqui. Passamos o 'draw',
            # o 'config' do template, e o texto do cliente.
            draw_templated_text(draw, config, pedido.text_to_add)
            
            # 5. Salva a imagem final
            img.save(output_path, "PNG", dpi=(300, 300)) 
            
            logger.info(f"Imagem gerada com sucesso: {output_path}")

    except FileNotFoundError as e:
        # Captura o erro de fonte não encontrada da função helper
        logger.error(f"Erro de arquivo: {e}")
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Erro ao processar imagem para pedido {pedido.order_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Erro interno no processamento de imagem: {e}")

    # 6. Retorna uma resposta de sucesso
    return {
        "message": "Imagem gerada com sucesso!",
        "order_id": pedido.order_id,
        "output_file": output_filename,
        "path_no_servidor": str(output_path)
    }

# --- Ponto de entrada para rodar o servidor (Uvicorn) ---
if __name__ == "__main__":
    uvicorn.run("main.test:app", host="127.0.0.1", port=8000, reload=True)